#!/usr/bin/env python3
"""Compose background and text layers into final image.

Usage:
    python3 compose.py --background bg.png --text text.png --width 1920 --height 1080 --output final.png
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from utils import validate_image


def make_transparent(img: Image.Image, sat_threshold: float = 0.08, val_min: int = 200) -> Image.Image:
    """Convert low-saturation bright pixels to transparent.

    The API sometimes returns 'transparent background' as uniform light gray
    (RGB ~230) instead of real alpha. This detects background pixels by their
    low color saturation and high brightness, then sets their alpha to 0.
    """
    rgba = img.convert("RGBA")
    data = np.array(rgba, dtype=np.float32)
    r, g, b = data[:, :, 0], data[:, :, 1], data[:, :, 2]

    # Compute saturation: 1 - min(rgb) / max(rgb)
    max_rgb = np.maximum(np.maximum(r, g), b)
    min_rgb = np.minimum(np.minimum(r, g), b)
    sat = np.where(max_rgb > 0, 1.0 - min_rgb / max_rgb, 0.0)

    # Background = low saturation + bright
    bg_mask = (sat < sat_threshold) & (max_rgb > val_min)

    result = np.array(rgba)
    result[bg_mask, 3] = 0
    return Image.fromarray(result)


def compose(background_path: str, text_path: str, width: int, height: int, output_path: str) -> Path:
    """Compose background and text layers into final image at target dimensions."""
    bg = Image.open(background_path).convert("RGBA")
    text_layer = Image.open(text_path)

    # If text layer lacks real alpha, synthesize transparency from white pixels
    if text_layer.mode != "RGBA" or text_layer.split()[3].getextrema() == (255, 255):
        text_layer = make_transparent(text_layer)
    else:
        text_layer = text_layer.convert("RGBA")

    # Resize both layers to target dimensions
    bg = bg.resize((width, height), Image.LANCZOS)
    text_layer = text_layer.resize((width, height), Image.LANCZOS)

    # Composite text layer on top of background
    final = Image.alpha_composite(bg, text_layer)

    # Convert to RGB (flatten alpha) — final deliverable has no transparency
    final = final.convert("RGB")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    final.save(str(output))
    return output


def main():
    parser = argparse.ArgumentParser(description="Compose background + text layers")
    parser.add_argument("--background", required=True, help="Background layer image path")
    parser.add_argument("--text", required=True, help="Text layer image path (transparent bg)")
    parser.add_argument("--width", type=int, required=True, help="Target width in pixels")
    parser.add_argument("--height", type=int, required=True, help="Target height in pixels")
    parser.add_argument("--output", required=True, help="Output file path")
    args = parser.parse_args()

    for path, label in [(args.background, "Background"), (args.text, "Text")]:
        if not Path(path).exists():
            print(f"Error: {label} image not found: {path}")
            sys.exit(1)
        if not validate_image(path):
            print(f"Error: {label} image is invalid: {path}")
            sys.exit(1)

    print(f"Composing {args.width}x{args.height} image...")
    print(f"  Background: {args.background}")
    print(f"  Text layer: {args.text}")

    output = compose(args.background, args.text, args.width, args.height, args.output)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
