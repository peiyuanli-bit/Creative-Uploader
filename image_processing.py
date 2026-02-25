"""
Moloco Ads MCP Server — Image Processing Helpers

Functions for resizing, compressing, dimension detection, and pre-flight
validation of images before uploading to Moloco. Uses ffmpeg/ffprobe via
subprocess for all image manipulation.
"""

import os
import subprocess as sp
from typing import Dict, Optional

from constants import (
    VALID_IMAGE_SIZES,
    VALID_NATIVE_SIZES,
    is_valid_image_dimension,
    is_valid_native_dimension,
)


def _get_video_dimensions(file_path: str) -> tuple:
    """Get width and height using ffprobe. Returns (width, height) or (0, 0).

    Works on both video and image files. Used as a fallback when PIL is not
    available.
    """
    try:
        result = sp.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", file_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and "x" in result.stdout:
            w, h = result.stdout.strip().split("x")
            return int(w), int(h)
    except Exception:
        pass
    return 0, 0


def get_image_dimensions(image_path: str) -> tuple:
    """Get image width and height. Tries PIL first, falls back to ffprobe."""
    try:
        from PIL import Image
        img = Image.open(image_path)
        return img.size
    except Exception:
        pass
    return _get_video_dimensions(image_path)  # ffprobe works on images too


def resize_with_letterbox(source_path: str, target_w: int, target_h: int,
                          output_path: str = None) -> str:
    """Resize image to fit within target dimensions, adding black bars to preserve aspect ratio.

    Letterbox (horizontal bars) if source is wider than target.
    Pillarbox (vertical bars) if source is taller than target.
    """
    if not output_path:
        base = os.path.splitext(os.path.basename(source_path))[0]
        output_path = os.path.join(os.path.dirname(source_path),
                                    f"{base}_{target_w}x{target_h}.jpg")
    vf = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
          f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black")
    sp.run(["ffmpeg", "-y", "-i", source_path, "-vf", vf, "-q:v", "2", output_path],
           capture_output=True, timeout=30, check=True)
    return output_path


def compress_image(image_path: str, max_kb: int = 500) -> str:
    """Compress an image to be under max_kb. Iteratively reduces JPEG quality."""
    current_kb = os.path.getsize(image_path) / 1024
    if current_kb <= max_kb:
        return image_path

    base = os.path.splitext(image_path)[0]
    compressed_path = base + "_compressed.jpg"

    # Iterative JPEG quality reduction
    for quality in range(90, 40, -10):
        # ffmpeg -q:v scale: 2=best, 31=worst. Map quality 90->3, 50->20
        qv = max(2, int(31 - quality * 0.3))
        sp.run(["ffmpeg", "-y", "-i", image_path, "-q:v", str(qv), compressed_path],
               capture_output=True, timeout=30, check=True)
        if os.path.getsize(compressed_path) / 1024 <= max_kb:
            return compressed_path

    # Last resort: aggressive compression
    sp.run(["ffmpeg", "-y", "-i", image_path, "-q:v", "25", compressed_path],
           capture_output=True, timeout=30, check=True)
    return compressed_path


def detect_retina_size(w: int, h: int) -> Optional[Dict]:
    """Check if dimensions are a 2x or 3x multiple of a valid Moloco size.

    Returns the target size and scale factor if detected, None otherwise.
    E.g. 640x100 -> {"target_w": 320, "target_h": 50, "scale": 2, "label": "Mobile Banner"}
    """
    labels = {
        (300, 250): "Medium Rectangle", (320, 480): "Portrait Interstitial",
        (320, 50): "Mobile Banner", (728, 90): "Leaderboard",
        (480, 320): "Landscape Interstitial", (768, 1024): "Tablet Portrait",
        (1024, 768): "Tablet Landscape", (300, 50): "Mobile Banner Small",
        (468, 60): "Banner",
        # Native sizes
        (1200, 628): "Native Landscape", (1200, 600): "Native Landscape Alt",
        (720, 720): "Native Square", (720, 960): "Native Portrait 3:4",
        (720, 1280): "Native Portrait", (1200, 1600): "Native Portrait Large",
    }
    all_sizes = list(VALID_IMAGE_SIZES) + list(VALID_NATIVE_SIZES)

    for scale in [2, 3, 4]:
        for tw, th in all_sizes:
            # Allow ±5 pixel tolerance for compression/rounding artifacts
            if abs(w - tw * scale) <= 5 and abs(h - th * scale) <= 5:
                creative_type = "IMAGE" if (tw, th) in VALID_IMAGE_SIZES else "NATIVE"
                return {
                    "target_w": tw, "target_h": th, "scale": scale,
                    "label": labels.get((tw, th), f"{tw}x{th}"),
                    "creative_type": creative_type,
                }
    return None


def prepare_image_for_upload(file_path: str) -> Dict:
    """Pre-flight check and fix for an image before uploading to Moloco.

    Detects and handles:
    1. Retina/oversized images (2x, 3x of valid sizes) -> auto-resize down
    2. Files over 500KB -> auto-compress
    3. Invalid dimensions -> warn
    Returns dict with corrected path, dimensions, warnings.
    """
    w, h = get_image_dimensions(file_path)
    file_size_kb = os.path.getsize(file_path) / 1024
    warnings = []
    corrected_path = file_path
    corrected_w, corrected_h = w, h

    # Check for retina/oversized
    retina = detect_retina_size(w, h)
    if retina:
        target_w, target_h = retina["target_w"], retina["target_h"]
        warnings.append(
            f"Detected {retina['scale']}x retina image ({w}x{h}) — "
            f"resizing to {target_w}x{target_h} ({retina['label']})"
        )
        base = os.path.splitext(file_path)[0]
        corrected_path = f"{base}_{target_w}x{target_h}.jpg"
        # Direct downscale (no letterbox needed — exact aspect ratio match)
        sp.run(["ffmpeg", "-y", "-i", file_path,
                "-vf", f"scale={target_w}:{target_h}",
                "-q:v", "2", corrected_path],
               capture_output=True, timeout=30, check=True)
        corrected_w, corrected_h = target_w, target_h
        file_size_kb = os.path.getsize(corrected_path) / 1024

    # Validate dimensions and classify
    is_valid_img = is_valid_image_dimension(corrected_w, corrected_h)
    is_valid_nat = is_valid_native_dimension(corrected_w, corrected_h)
    is_source = corrected_w >= 640 and corrected_h >= 640  # Large enough to resize down

    if not is_valid_img and not is_valid_nat:
        if is_source:
            warnings.append(
                f"Dimensions {corrected_w}x{corrected_h} are not a standard Moloco size, "
                f"but large enough to use as source material — will letterbox-resize to all 9 IMAGE sizes."
            )
        else:
            warnings.append(
                f"Dimensions {corrected_w}x{corrected_h} are not a standard Moloco size and too small for source. "
                f"Valid IMAGE sizes: {sorted(VALID_IMAGE_SIZES)}."
            )

    # Auto-compress if over 500KB (only for standard sizes; sources get resized later)
    if file_size_kb > 500 and (is_valid_img or is_valid_nat):
        warnings.append(f"File is {file_size_kb:.0f}KB (max 500KB) — compressing")
        corrected_path = compress_image(corrected_path, max_kb=500)
        file_size_kb = os.path.getsize(corrected_path) / 1024
        if file_size_kb > 500:
            warnings.append(f"WARNING: Still {file_size_kb:.0f}KB after compression — upload may be rejected")

    if is_valid_img:
        creative_type = "IMAGE"
    elif is_valid_nat:
        creative_type = "NATIVE"
    elif is_source:
        creative_type = "IMAGE_SOURCE"
    else:
        creative_type = "UNKNOWN"

    return {
        "original_path": file_path,
        "corrected_path": corrected_path,
        "original_dimensions": f"{w}x{h}",
        "corrected_dimensions": f"{corrected_w}x{corrected_h}",
        "size_kb": round(file_size_kb, 1),
        "creative_type": creative_type,
        "was_retina": retina is not None,
        "was_compressed": corrected_path != file_path or file_size_kb != os.path.getsize(file_path) / 1024,
        "warnings": warnings,
        "upload_ready": file_size_kb <= 500,
    }
