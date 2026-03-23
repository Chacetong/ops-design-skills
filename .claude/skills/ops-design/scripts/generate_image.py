#!/usr/bin/env python3
"""Generate Banner images via API proxy.

Unified pipeline: get base image → expand to 2:1 → add title text.
Base image is either user-provided (--reference) or AI-generated (Gemini).

  Without --reference:
    1. Generate base image via Gemini (text-to-image)
    2. Expand to 2:1 via Gemini (no text)
    3. Add title text via Gemini

  With --reference (portrait, aspect < SQUARE_THRESHOLD):
    0. Squarify portrait reference to 1:1 via Gemini (preserves subject)
    1. Expand 1:1 square to 2:1 via Gemini (no text)
    2. Add title text via Gemini

  With --reference (already wide, aspect >= SQUARE_THRESHOLD):
    1. Expand reference to 2:1 via Gemini (no text)
    2. Add title text via Gemini

  Text-only (auto-detected when --save-intermediate path already exists):
    1. Add title text via Gemini (reuses existing expanded image)

  Expand-only (auto-detected when --text-prompt is omitted):
    1. Expand reference/base to 2:1 via Gemini, save to --output
    (Use when regenerating expanded without re-running the text step)

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

    # Text-only iteration (auto-detected: expanded.png already exists)
    python3 generate_image.py --prompt "<fallback>" \
        --text-prompt "..." \
        --output output/drafts/with_text_v2.png \
        --reference img.png \
        --save-intermediate output/drafts/expanded.png

    # Expand-only iteration (auto-detected: no --text-prompt provided)
    python3 generate_image.py --prompt "<fallback>" \
        --expand-prompt "..." \
        --output output/drafts/expanded_v2.png \
        --reference output/drafts/square.png

    # Custom squarify prompt (override default portrait-to-square reframing)
    python3 generate_image.py --prompt "<base_prompt>" \
        --expand-prompt "..." --text-prompt "..." \
        --output output/drafts/with_text.png \
        --reference portrait.png \
        --square-prompt "Redraw as 1:1 square, keep subject centered..."

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

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from utils import validate_image

DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-image-preview")

# Reference images with aspect ratio (w/h) below this threshold are portrait and
# will be squarified to 1:1 before expansion to reduce distortion.
SQUARE_THRESHOLD = 0.85


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


def squarify_portrait_reference(
    reference_path: str,
    square_prompt: str,
    model: str = "",
    save_path: str = "",
) -> str:
    """Reframe a portrait reference image to 1:1 square via Gemini generation.

    Requires a square_prompt (generated by ops-prompt). Checks the aspect ratio
    of reference_path — if w/h < SQUARE_THRESHOLD (portrait), calls Gemini to
    generate a square version. Returns the path to the square image.
    If the image is already wide enough, returns reference_path unchanged.
    """
    from PIL import Image

    img = Image.open(reference_path)
    w, h = img.size
    aspect = w / h

    if aspect >= SQUARE_THRESHOLD:
        print(f"  Step 0: Skipped squarify (aspect={aspect:.2f} >= {SQUARE_THRESHOLD})")
        return reference_path

    gemini_model = model or DEFAULT_GEMINI_MODEL
    print(f"  Step 0/3: Squarifying portrait reference (aspect={aspect:.2f} → 1:1, {gemini_model})...")

    square_bytes = _gemini_generate(square_prompt, [reference_path], gemini_model)

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_bytes(square_bytes)
        print(f"  Square intermediate saved: {save_path}")
        return save_path
    else:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(square_bytes)
        tmp.close()
        return tmp.name


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

    # Expand to 2:1
    print(f"  Expanding image to 2:1 ({gemini_model})...")
    expanded_bytes = _gemini_generate(expand_prompt, reference_images, gemini_model)

    # Save intermediate if path provided
    if intermediate_path:
        Path(intermediate_path).parent.mkdir(parents=True, exist_ok=True)
        Path(intermediate_path).write_bytes(expanded_bytes)
        print(f"  Intermediate saved: {intermediate_path}")
        expanded_ref = intermediate_path
    else:
        # Save to temp file for text step
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(expanded_bytes)
        tmp.close()
        expanded_ref = tmp.name

    # Add title text
    print(f"  Adding title text ({gemini_model})...")
    final_bytes = _gemini_generate(text_prompt, [expanded_ref], gemini_model)

    # Clean up temp file
    if not intermediate_path:
        os.unlink(expanded_ref)

    return final_bytes


def add_text_only(
    text_prompt: str,
    expanded_image: str,
    model: str = "",
) -> bytes:
    """Text-only step: add title text to an already-expanded image.

    Used for iterating on typography without re-running the expand step.
    Returns raw image bytes of the final result.
    """
    gemini_model = model or DEFAULT_GEMINI_MODEL
    print(f"  Adding title text (text-only mode, {gemini_model})...")
    return _gemini_generate(text_prompt, [expanded_image], gemini_model)


def main():
    parser = argparse.ArgumentParser(description="Generate images via API proxy")
    parser.add_argument("--prompt", required=True, help="Base image prompt (full_generate) or fallback")
    parser.add_argument("--expand-prompt", help="Prompt for scene expansion to 2:1")
    parser.add_argument("--text-prompt", help="Prompt for adding title text")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--reference", nargs="*", help="Reference image paths (skips base generation)")
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL,
                        help=f"Gemini model (default: {DEFAULT_GEMINI_MODEL})")
    parser.add_argument("--save-base", help="Save base image to this path (no-reference mode)")
    parser.add_argument("--square-prompt", help="Custom prompt for squarifying portrait references to 1:1")
    parser.add_argument("--save-square", help="Save squarified portrait intermediate to this path")
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
        drafts_dir = Path(args.output).parent
        expand_prompt = args.expand_prompt or args.prompt
        text_prompt = args.text_prompt or args.prompt

        # Auto-detect text-only: if expanded intermediate already exists, skip squarify + expand
        intermediate_path = args.save_intermediate or ""
        if intermediate_path and Path(intermediate_path).exists():
            print(f"Expanded image found, skipping squarify and expand...")
            raw_bytes = add_text_only(text_prompt, intermediate_path, args.gemini_model)
            Path(args.output).write_bytes(raw_bytes)
            output_path = Path(args.output)
            if validate_image(str(output_path)):
                print(f"Saved: {output_path}")
            else:
                print("Error: Generated image is invalid")
                sys.exit(1)
            return

        # Copy reference images into drafts folder for traceability.
        # Skip if the reference is already inside the drafts directory.
        for i, ref in enumerate(args.reference):
            ext = Path(ref).suffix
            dest_name = f"reference{ext}" if len(args.reference) == 1 else f"reference_{i + 1}{ext}"
            dest = drafts_dir / dest_name
            ref_resolved = Path(ref).resolve()
            already_in_drafts = ref_resolved.parent == drafts_dir.resolve()
            if not already_in_drafts and ref_resolved != dest.resolve():
                shutil.copy2(ref, dest)
                print(f"  Reference copied: {dest}")

        # Step 0 (conditional): squarify portrait reference before expansion
        # Only runs when --square-prompt is provided (generated by ops-prompt)
        references_for_expand = list(args.reference)
        square_temp = None
        if len(references_for_expand) == 1 and args.square_prompt:
            save_square = args.save_square or str(drafts_dir / "square.png")
            squarified = squarify_portrait_reference(
                references_for_expand[0],
                square_prompt=args.square_prompt,
                model=args.gemini_model,
                save_path=save_square,
            )
            if squarified != references_for_expand[0]:
                references_for_expand = [squarified]
                if squarified != save_square:
                    square_temp = squarified  # temp file to clean up later

        # Auto-detect expand-only: no --text-prompt provided
        if not args.text_prompt:
            print(f"No text-prompt provided, running expand-only (gemini_model={args.gemini_model})...")
            expanded_bytes = _gemini_generate(
                expand_prompt, references_for_expand, args.gemini_model
            )
            Path(args.output).write_bytes(expanded_bytes)
            output_path = Path(args.output)
            if square_temp:
                os.unlink(square_temp)
            if validate_image(str(output_path)):
                print(f"Saved: {output_path}")
            else:
                print("Error: Generated image is invalid")
                sys.exit(1)
            return

        print(f"Generating banner (gemini_model={args.gemini_model})...")
        raw_bytes = generate_with_reference(
            expand_prompt, text_prompt, references_for_expand,
            args.gemini_model, args.save_intermediate or "",
        )
        Path(args.output).write_bytes(raw_bytes)
        output_path = Path(args.output)

        if square_temp:
            os.unlink(square_temp)
    else:
        # No reference: generate base image via Gemini, then expand + text via Gemini
        base_path = args.save_base or str(Path(args.output).parent / "base.png")
        print(f"Generating base image ({args.gemini_model})...")
        base_bytes = _gemini_generate(args.prompt, [], args.gemini_model)
        Path(base_path).parent.mkdir(parents=True, exist_ok=True)
        Path(base_path).write_bytes(base_bytes)
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
