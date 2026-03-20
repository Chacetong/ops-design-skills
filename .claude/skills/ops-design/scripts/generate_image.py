#!/usr/bin/env python3
"""Generate Banner images via API proxy.

Unified pipeline: get base image → expand to 2:1 → add title text.
Base image is either user-provided (--reference) or AI-generated (OpenAI).

  Without --reference:
    1. Generate 4:3 base image via OpenAI (gpt-image-1.5)
    2. Expand to 2:1 via Gemini (no text)
    3. Add title text via Gemini

  With --reference:
    1. Expand reference to 2:1 via Gemini (no text)
    2. Add title text via Gemini

Usage:
    # No reference (generate base + expand + text)
    python3 generate_image.py --prompt "<base_prompt>" \
        --expand-prompt "..." --text-prompt "..." \
        --output output/drafts/with_text.png \
        --save-base output/drafts/base.png \
        --save-intermediate output/drafts/expanded.png

    # With reference (expand + text)
    python3 generate_image.py --prompt "<fallback>" \
        --expand-prompt "..." --text-prompt "..." \
        --output output/drafts/with_text.png \
        --reference img.png \
        --save-intermediate output/drafts/expanded.png

Env vars:
    OPENAI_BASE_URL  - API proxy base URL (e.g. https://llm-proxy.learnings.ai)
    OPENAI_API_KEY   - API key for the proxy
    IMAGE_MODEL      - Default model (default: gpt-image-1.5)
    GEMINI_MODEL     - Gemini model for expand + text generation
                       (default: gemini-3.1-flash-image-preview)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List

from openai import OpenAI

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from utils import decode_and_save, validate_image

DEFAULT_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1.5")
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-image-preview")


def _get_gemini_client():
    """Create a Google GenAI client via LiteLLM Vertex AI passthrough."""
    from google import genai
    from google.auth.credentials import Credentials

    api_key = os.environ.get("OPENAI_API_KEY", "")
    proxy_base = os.environ.get("OPENAI_BASE_URL", "https://llm-proxy.learnings.ai")
    proxy_base = proxy_base.removesuffix("/v1")

    class _ProxyCredentials(Credentials):
        def refresh(self, request):
            self.token = "unused"

        @property
        def valid(self):
            return True

    return genai.Client(
        vertexai=True,
        project="arsenal-learnings",
        location="global",
        credentials=_ProxyCredentials(),
        http_options={
            "base_url": f"{proxy_base}/vertex_ai",
            "headers": {"x-litellm-api-key": f"Bearer {api_key}"},
        },
    )


def _gemini_generate(prompt: str, reference_images: List[str], model: str) -> bytes:
    """Call Gemini multimodal with reference images + prompt. Returns raw image bytes."""
    from google.genai import types

    client = _get_gemini_client()

    contents = []
    for img_path in reference_images:
        img_bytes = Path(img_path).read_bytes()
        ext = Path(img_path).suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/png")
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

    contents.append(prompt)

    response = client.models.generate_content(
        model=model,
        contents=contents,
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    raise RuntimeError("Gemini returned no image in response")


def generate_with_reference(
    expand_prompt: str,
    text_prompt: str,
    reference_images: List[str],
    model: str = "",
    intermediate_path: str = "",
) -> bytes:
    """Two-step generation: expand image, then add text.

    Step 1: Expand reference image to wide 2:1 composition (scene only, no text)
    Step 2: Add title text to the expanded image

    Returns raw image bytes of the final result.
    """
    gemini_model = model or DEFAULT_GEMINI_MODEL

    # Step 1: Expand
    print(f"  Step 1/2: Expanding image ({gemini_model})...")
    expanded_bytes = _gemini_generate(expand_prompt, reference_images, gemini_model)

    # Save intermediate if path provided
    if intermediate_path:
        Path(intermediate_path).parent.mkdir(parents=True, exist_ok=True)
        Path(intermediate_path).write_bytes(expanded_bytes)
        print(f"  Intermediate saved: {intermediate_path}")
        expanded_ref = intermediate_path
    else:
        # Save to temp file for step 2
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(expanded_bytes)
        tmp.close()
        expanded_ref = tmp.name

    # Step 2: Add text
    print(f"  Step 2/2: Adding text ({gemini_model})...")
    final_bytes = _gemini_generate(text_prompt, [expanded_ref], gemini_model)

    # Clean up temp file
    if not intermediate_path:
        os.unlink(expanded_ref)

    return final_bytes


def generate_full(client: OpenAI, prompt: str, size: str, model: str) -> str:
    """Generate image via OpenAI images.generate. Returns base64 data."""
    result = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
    )
    return result.data[0].b64_json


def main():
    parser = argparse.ArgumentParser(description="Generate images via API proxy")
    parser.add_argument("--prompt", required=True, help="Base image prompt (full_generate) or fallback")
    parser.add_argument("--expand-prompt", help="Prompt for scene expansion to 2:1")
    parser.add_argument("--text-prompt", help="Prompt for adding title text")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--reference", nargs="*", help="Reference image paths (skips base generation)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model (default: {DEFAULT_MODEL})")
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL,
                        help=f"Gemini model (default: {DEFAULT_GEMINI_MODEL})")
    parser.add_argument("--base-size", default="1536x1024", help="Base image size (default: 1536x1024). Supported: 1024x1024, 1024x1536, 1536x1024")
    parser.add_argument("--save-base", help="Save base image to this path (full_generate)")
    parser.add_argument("--save-intermediate", help="Save expanded image to this path")
    parser.add_argument("--request", help="Original user request text, saved to drafts/request.txt")
    args = parser.parse_args()

    # Save original user request
    if args.request:
        request_path = Path(args.output).parent / "request.txt"
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(args.request, encoding="utf-8")
        print(f"  Request saved: {request_path}")

    # Validate reference images
    if args.reference:
        for ref in args.reference:
            if not Path(ref).exists():
                print(f"Error: Reference image not found: {ref}")
                sys.exit(1)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    if args.reference:
        # Copy reference images into drafts folder for traceability
        drafts_dir = Path(args.output).parent
        for i, ref in enumerate(args.reference):
            ext = Path(ref).suffix
            dest_name = f"reference{ext}" if len(args.reference) == 1 else f"reference_{i + 1}{ext}"
            dest = drafts_dir / dest_name
            shutil.copy2(ref, dest)
            print(f"  Reference copied: {dest}")

        # Two-step Gemini: expand + text
        expand_prompt = args.expand_prompt or args.prompt
        text_prompt = args.text_prompt or args.prompt
        print(f"Generating with reference (two-step, gemini_model={args.gemini_model})...")
        raw_bytes = generate_with_reference(
            expand_prompt, text_prompt, args.reference,
            args.gemini_model, args.save_intermediate or "",
        )
        Path(args.output).write_bytes(raw_bytes)
        output_path = Path(args.output)
    else:
        # No reference: generate 4:3 base via OpenAI, then expand + text via Gemini
        print(f"Generating base image ({args.model}, {args.base_size})...")
        client = OpenAI()
        b64_data = generate_full(client, args.prompt, args.base_size, args.model)
        base_path = args.save_base or str(Path(args.output).parent / "base.png")
        decode_and_save(b64_data, base_path)
        print(f"  Base image saved: {base_path}")

        expand_prompt = args.expand_prompt or args.prompt
        text_prompt = args.text_prompt or args.prompt
        print(f"Expanding and adding text (gemini_model={args.gemini_model})...")
        raw_bytes = generate_with_reference(
            expand_prompt, text_prompt, [base_path],
            args.gemini_model, args.save_intermediate or "",
        )
        Path(args.output).write_bytes(raw_bytes)
        output_path = Path(args.output)

    if validate_image(str(output_path)):
        print(f"Saved: {output_path}")
    else:
        print("Error: Generated image is invalid")
        sys.exit(1)


if __name__ == "__main__":
    main()
