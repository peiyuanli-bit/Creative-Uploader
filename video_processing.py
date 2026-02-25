"""
Video processing helpers for the Moloco Ads MCP Server.

Functions for extracting endcard frames, reading video dimensions,
and uploading media files to GCS via the Moloco API.
"""

import asyncio
import os
import subprocess
import sys
import tempfile
from typing import Optional

from moloco_client import MolocoAPIClient


def extract_endcard_from_video(video_path: str) -> Optional[str]:
    """Extract the last frame from a video using ffmpeg as an endcard image.

    Returns the path to the extracted JPEG, or None if ffmpeg fails.
    Extracts the last frame (most video ads end with a CTA/endcard frame).
    """
    output_path = tempfile.mktemp(suffix=".jpg", prefix="endcard_")
    try:
        # Get video duration first
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=10
        )
        duration = float(probe.stdout.strip()) if probe.returncode == 0 else 0

        if duration > 1:
            # Extract frame 1 second before the end (avoids black frames)
            timestamp = max(0, duration - 1.0)
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
                 "-frames:v", "1", "-q:v", "2", output_path],
                capture_output=True, timeout=30, check=True
            )
        else:
            # Very short video — just grab the first frame
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path,
                 "-frames:v", "1", "-q:v", "2", output_path],
                capture_output=True, timeout=30, check=True
            )

        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception as e:
        print(f"ffmpeg endcard extraction failed: {e}", file=sys.stderr)
    return None


def get_video_dimensions(video_path: str) -> tuple:
    """Get video width and height using ffprobe. Returns (width, height) or (0, 0)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and "x" in result.stdout:
            w, h = result.stdout.strip().split("x")
            return int(w), int(h)
    except Exception:
        pass
    return 0, 0


def get_native_video_size(vid_w: int, vid_h: int) -> Optional[tuple]:
    """Map standard video dimensions to native video equivalents.

    Returns (native_w, native_h) or None if dimensions are unrecognised.
    - landscape (w > h) → (1280, 720)
    - portrait  (h > w) → (720, 1280)
    - square    (w == h) → (720, 720)
    """
    if vid_w > vid_h:
        return (1280, 720)
    elif vid_h > vid_w:
        return (720, 1280)
    elif vid_w == vid_h and vid_w > 0:
        return (720, 720)
    return None


def transcode_video_to_native(video_path: str, target_w: int, target_h: int,
                               max_size_mb: int = 10) -> Optional[str]:
    """Transcode a video to native dimensions with letterbox (scale+pad).

    Uses progressive CRF (23 → 28 → 33 → 38) to stay under *max_size_mb*.
    Returns the path to the transcoded file, or None on failure.
    """
    output_path = tempfile.mktemp(suffix=".mp4", prefix="native_vid_")
    max_bytes = max_size_mb * 1024 * 1024

    for crf in (23, 28, 33, 38):
        try:
            vf = (
                f"scale={target_w}:{target_h}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
            )
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vf", vf,
                "-c:v", "libx264", "-crf", str(crf),
                "-preset", "medium", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)

            if os.path.isfile(output_path) and os.path.getsize(output_path) <= max_bytes:
                return output_path

            # File too large — try higher CRF
            if crf < 38:
                print(f"[transcode] CRF {crf} → {os.path.getsize(output_path) / 1024 / 1024:.1f}MB "
                      f"(>{max_size_mb}MB), retrying…", file=sys.stderr)
        except Exception as e:
            print(f"[transcode] CRF {crf} failed: {e}", file=sys.stderr)
            break  # ffmpeg error — don't retry with higher CRF

    # All CRF attempts failed or exceeded size limit
    if os.path.isfile(output_path):
        try:
            os.unlink(output_path)
        except Exception:
            pass
    return None


async def _upload_file_to_gcs(client: MolocoAPIClient, ad_account_id: str,
                               file_path: str, mime_type: str,
                               retries: int = 3) -> str:
    """Upload a local file to GCS via Moloco and return the asset_url.

    Retries up to ``retries`` times on transient errors (502, 503, timeout)
    with exponential backoff (1s, 2s, 4s).
    """
    for attempt in range(retries):
        try:
            session = await client.create_asset_upload_session(
                ad_account_id, asset_kind="CREATIVE", mime_type=mime_type)
            asset_url = session.get("asset_url")
            upload_url = session.get("content_upload_url")
            if not asset_url or not upload_url:
                raise Exception(f"Upload session failed: {session}")
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            await client.upload_asset_to_gcs(upload_url, file_bytes, mime_type)
            return asset_url
        except Exception as e:
            err_str = str(e).lower()
            is_transient = any(tok in err_str for tok in ("502", "503", "timeout", "timed out"))
            if attempt < retries - 1 and is_transient:
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"[gcs-upload] Attempt {attempt + 1} failed ({e}), retrying in {wait}s…",
                      file=sys.stderr)
                await asyncio.sleep(wait)
                continue
            raise
