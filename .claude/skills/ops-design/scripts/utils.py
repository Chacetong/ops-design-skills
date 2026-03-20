"""Utility functions for ops-design skill."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image

OUTPUT_ROOT = Path("output")


def create_task_dir() -> Path:
    """Create a task directory under output/ with naming convention YYMMDD-NN.

    Scans existing directories to determine the next sequence number for today.
    Returns the created task directory path (e.g. output/260319-01/).
    Also creates a drafts/ subdirectory for intermediate files.
    """
    date_prefix = datetime.now().strftime("%y%m%d")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    # Find next sequence number for today
    existing = sorted(OUTPUT_ROOT.glob(f"{date_prefix}-*"))
    if existing:
        last_seq = int(existing[-1].name.split("-")[-1])
        seq = last_seq + 1
    else:
        seq = 1

    task_dir = OUTPUT_ROOT / f"{date_prefix}-{seq:02d}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "drafts").mkdir(exist_ok=True)
    return task_dir


def decode_and_save(b64_data: str, output_path: str) -> Path:
    """Decode base64 image data and save to file."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(b64_data))
    return output


def resize_to_target(image_path: str, width: int, height: int, output_path: Optional[str] = None) -> Path:
    """Resize image to target dimensions using high-quality resampling."""
    img = Image.open(image_path)
    resized = img.resize((width, height), Image.LANCZOS)
    out = Path(output_path) if output_path else Path(image_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    resized.save(str(out))
    return out


def validate_image(image_path: str) -> bool:
    """Check if a file is a valid image."""
    try:
        with Image.open(image_path) as img:
            img.verify()
        return True
    except Exception:
        return False
