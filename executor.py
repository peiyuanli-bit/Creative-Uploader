import asyncio
import mimetypes
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Tuple

from moloco_client import MolocoAPIClient
from image_processing import (
    prepare_image_for_upload,
    resize_with_letterbox,
    compress_image,
    get_image_dimensions,
)
from video_processing import (
    extract_endcard_from_video,
    get_video_dimensions,
    _upload_file_to_gcs,
)

# 你已有的默认 target 列表（9个）
from constants import IMAGE_RESIZE_TARGETS


# --- Moloco supported image sizes (来自你贴的 Create Creative 文档) ---
SUPPORTED_IMAGE_SIZES = {
    (120, 600), (160, 600), (200, 200), (250, 250), (300, 250), (300, 600),
    (320, 50), (320, 100), (320, 480), (336, 280), (375, 667), (468, 60),
    (480, 320), (600, 600), (640, 100), (640, 200), (667, 375), (728, 90),
    (768, 1024), (800, 417), (800, 418), (1024, 768), (1200, 627),
    (1200, 628), (1200, 667),
}


@dataclass
class ZipWorkspace:
    root_dir: Path  # extracted root


def safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    """Prevent ZipSlip: ensure extraction stays within target_dir."""
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            dest = (target_dir / member.filename).resolve()
            if not str(dest).startswith(str(target_dir.resolve())):
                raise RuntimeError(f"Unsafe zip path detected: {member.filename}")
        z.extractall(target_dir)


def create_workspace_from_zip(zip_bytes: bytes) -> ZipWorkspace:
    """Create a temp workspace and extract zip there."""
    tmp_root = Path(tempfile.mkdtemp(prefix="moloco_zip_"))
    zip_path = tmp_root / "upload.zip"
    zip_path.write_bytes(zip_bytes)

    extract_dir = tmp_root / "unzipped"
    extract_dir.mkdir(parents=True, exist_ok=True)

    safe_extract_zip(zip_path, extract_dir)
    return ZipWorkspace(root_dir=extract_dir)


def cleanup_workspace(ws: ZipWorkspace) -> None:
    """Delete temp workspace."""
    try:
        shutil.rmtree(ws.root_dir.parent, ignore_errors=True)
    except Exception:
        pass


def find_sidecar_endcard(video_abs: Path) -> Optional[Path]:
    stem = video_abs.stem
    for ext in (".png", ".jpg", ".jpeg", ".gif"):
        p = video_abs.with_name(f"{stem}_endcard{ext}")
        if p.exists() and p.is_file():
            return p
    return None


def scan_assets(root_dir: Path) -> List[Dict[str, Any]]:
    """Scan all files under root_dir; return basic metadata."""
    out: List[Dict[str, Any]] = []
    for p in sorted(root_dir.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            mime, _ = mimetypes.guess_type(str(p))
            meta = {
                "name": p.name,
                "rel_path": str(p.relative_to(root_dir)),
                "mime_type": mime or "",
                "size_bytes": p.stat().st_size,
            }
            if (meta["mime_type"] or "").startswith("video/"):
                meta["has_sidecar_endcard"] = bool(find_sidecar_endcard(p))
            else:
                meta["has_sidecar_endcard"] = ""
            out.append(meta)
    return out


# ----------------------------
# Plan validation + defaults
# ----------------------------
def _default_image_targets() -> List[Dict[str, int]]:
    return [{"w": t["w"], "h": t["h"]} for t in IMAGE_RESIZE_TARGETS]


def validate_and_normalize_plan(plan: Dict[str, Any], tracking_link_id_fallback: str) -> Dict[str, Any]:
    """
    Normalize plan and apply defaults:
    Plan DSL:
    {
      "groups":[{"name":"all","tracking_link_id":"..."}],
      "outputs":[
         {"source_rel_path":"...","kind":"IMAGE","target_sizes":[{"w":768,"h":1024}],
          "transforms":["LETTERBOX","COMPRESS_500KB"],"group":"all","title":"...","notes":"..."},
         {"source_rel_path":"...","kind":"VIDEO",
          "endcard":{"mode":"SIDECAR_OR_EXTRACT","target_size":{"w":768,"h":1024}},
          "group":"all","title":"...","notes":"..."}
      ]
    }
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")

    groups = plan.get("groups", [])
    outputs = plan.get("outputs", [])

    if not isinstance(groups, list) or not groups:
        # If LLM forgot groups, create a default single group.
        groups = [{"name": "all", "tracking_link_id": tracking_link_id_fallback}]

    # Ensure unique group names
    seen = set()
    norm_groups = []
    for g in groups:
        name = (g.get("name") or "").strip()
        if not name:
            raise ValueError("group.name is required")
        if name in seen:
            raise ValueError(f"duplicate group name: {name}")
        seen.add(name)
        tlid = (g.get("tracking_link_id") or "").strip() or tracking_link_id_fallback
        norm_groups.append({"name": name, "tracking_link_id": tlid})

    group_names = {g["name"] for g in norm_groups}

    if not isinstance(outputs, list) or not outputs:
        raise ValueError("outputs must be a non-empty list")

    # Default targets if omitted
    default_targets = _default_image_targets()

    norm_outputs = []
    for o in outputs:
        src = (o.get("source_rel_path") or "").strip()
        kind = (o.get("kind") or "").strip().upper()
        group = (o.get("group") or "").strip()
        title = (o.get("title") or "").strip() or None
        notes = (o.get("notes") or "").strip()

        if not src:
            raise ValueError("outputs[].source_rel_path is required")
        if kind not in ("IMAGE", "VIDEO"):
            raise ValueError(f"outputs[].kind must be IMAGE or VIDEO, got: {kind}")
        if group not in group_names:
            raise ValueError(f"outputs[].group must be one of {sorted(group_names)}, got: {group}")

        transforms = o.get("transforms", [])
        if transforms is None:
            transforms = []
        if not isinstance(transforms, list):
            raise ValueError("outputs[].transforms must be a list")

        # Normalize IMAGE target sizes
        if kind == "IMAGE":
            target_sizes = o.get("target_sizes") or default_targets[:1]
            if not isinstance(target_sizes, list) or not target_sizes:
                raise ValueError("IMAGE outputs must have non-empty target_sizes")
            norm_ts = []
            for t in target_sizes:
                w, h = int(t["w"]), int(t["h"])
                if (w, h) not in SUPPORTED_IMAGE_SIZES:
                    raise ValueError(f"Unsupported image target size: {w}x{h}")
                norm_ts.append({"w": w, "h": h})

            # If LETTERBOX not specified, implicitly apply it when size mismatch happens
            # (we’ll still execute letterbox to guarantee the output size)
            norm_outputs.append(
                {
                    "source_rel_path": src,
                    "kind": "IMAGE",
                    "target_sizes": norm_ts,
                    "transforms": [x.upper() for x in transforms],
                    "group": group,
                    "title": title,
                    "notes": notes,
                }
            )
        else:
            # VIDEO requires endcard config (mode + optional target size)
            endcard = o.get("endcard") or {}
            mode = (endcard.get("mode") or "SIDECAR_OR_EXTRACT").strip().upper()
            if mode not in ("SIDECAR_ONLY", "EXTRACT_ONLY", "SIDECAR_OR_EXTRACT"):
                raise ValueError(f"VIDEO endcard.mode invalid: {mode}")

            ts = endcard.get("target_size") or default_targets[0]
            tw, th = int(ts["w"]), int(ts["h"])
            if (tw, th) not in SUPPORTED_IMAGE_SIZES:
                raise ValueError(f"Unsupported endcard target size: {tw}x{th}")

            norm_outputs.append(
                {
                    "source_rel_path": src,
                    "kind": "VIDEO",
                    "endcard": {"mode": mode, "target_size": {"w": tw, "h": th}},
                    "transforms": [x.upper() for x in transforms],  # reserved for future
                    "group": group,
                    "title": title,
                    "notes": notes,
                }
            )

    return {"groups": norm_groups, "outputs": norm_outputs}


# ----------------------------
# Execution helpers
# ----------------------------
async def _create_image_creative(
    client: MolocoAPIClient,
    ad_account_id: str,
    product_id: str,
    image_path: Path,
    title: Optional[str] = None,
) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    mime_type = mime_type or "image/jpeg"
    asset_url = await _upload_file_to_gcs(client, ad_account_id, str(image_path), mime_type)

    w, h = get_image_dimensions(str(image_path))
    size_in_bytes = image_path.stat().st_size

    body = {
        "title": (title or f"CR_{image_path.stem}")[:80],
        "type": "IMAGE",
        "original_filename": image_path.name,
        "size_in_bytes": size_in_bytes,
        "image": {
            "image_url": asset_url,
            "filename": image_path.name,
            "width": w,
            "height": h,
            "size_in_bytes": size_in_bytes,
        },
    }
    resp = await client.create_creative(ad_account_id, body, product_id=product_id)
    creative = resp.get("creative", resp)
    return creative["id"]


async def _create_video_creative(
    client: MolocoAPIClient,
    ad_account_id: str,
    product_id: str,
    video_path: Path,
    endcard_path: Path,
    title: Optional[str] = None,
) -> str:
    video_mime, _ = mimetypes.guess_type(str(video_path))
    video_mime = video_mime or "video/mp4"
    video_asset_url = await _upload_file_to_gcs(client, ad_account_id, str(video_path), video_mime)

    ec_mime, _ = mimetypes.guess_type(str(endcard_path))
    ec_mime = ec_mime or "image/jpeg"
    ec_asset_url = await _upload_file_to_gcs(client, ad_account_id, str(endcard_path), ec_mime)

    vw, vh = get_video_dimensions(str(video_path))
    ew, eh = get_image_dimensions(str(endcard_path))
    v_size = video_path.stat().st_size
    ec_size = endcard_path.stat().st_size

    # IMPORTANT: companion_images is inside video object (matches your internal schema templates)
    body = {
        "title": (title or f"CR_{video_path.stem}")[:80],
        "type": "VIDEO",
        "original_filename": video_path.name,
        "size_in_bytes": v_size,
        "video": {
            "video_url": video_asset_url,
            "filename": video_path.name,
            "width": vw,
            "height": vh,
            "size_in_bytes": v_size,
            "companion_images": [
                {
                    "image_url": ec_asset_url,
                    "filename": endcard_path.name,
                    "width": ew,
                    "height": eh,
                    "size_in_bytes": ec_size,
                }
            ],
        },
    }

    resp = await client.create_creative(ad_account_id, body, product_id=product_id)
    creative = resp.get("creative", resp)
    return creative["id"]


def _apply_image_transforms(source_path: Path, target_w: int, target_h: int, transforms: List[str]) -> Path:
    """
    Always ensure final output is EXACTLY target_w x target_h (letterbox).
    If COMPRESS_500KB is included, compress afterwards.
    """
    # We always letterbox to guarantee supported size.
    out_path = Path(resize_with_letterbox(str(source_path), target_w, target_h))

    if "COMPRESS_500KB" in transforms:
        out_path = Path(compress_image(str(out_path), max_kb=500))

    return out_path


def _prepare_image_source(abs_path: Path) -> Path:
    """
    Use your existing prepare_image_for_upload to correct retina etc.
    Return corrected path.
    """
    info = prepare_image_for_upload(str(abs_path))
    return Path(info["corrected_path"])


def _prepare_endcard_image(endcard_path: Path, target_w: int, target_h: int) -> Path:
    """
    Ensure endcard is supported size via letterbox; compress to <=500KB.
    """
    # Use same transform primitives.
    out = Path(resize_with_letterbox(str(endcard_path), target_w, target_h))
    out = Path(compress_image(str(out), max_kb=500))
    return out


# ----------------------------
# Main execute
# ----------------------------
async def execute_plan(
    plan: Dict[str, Any],
    *,
    moloco_api_key: str,
    root_dir: Path,
    ad_account_id: str,
    product_id: str,
    default_tracking_link_id: str,
    log: Callable[[str], None],
) -> Dict[str, Any]:
    """
    Execute the normalized plan:
    - Create creatives
    - Bucket creative_ids by group
    - Create creative groups per plan.groups
    """
    norm = validate_and_normalize_plan(plan, tracking_link_id_fallback=default_tracking_link_id)
    groups = norm["groups"]
    outputs = norm["outputs"]

    # bucket: group_name -> [creative_id]
    buckets: Dict[str, List[str]] = {g["name"]: [] for g in groups}

    client = MolocoAPIClient(api_key=moloco_api_key)
    try:
        for o in outputs:
            src_rel = o["source_rel_path"]
            abs_path = (root_dir / src_rel).resolve()
            if not abs_path.exists():
                log(f"[skip] missing file: {src_rel}")
                continue

            kind = o["kind"]
            group = o["group"]
            title = o.get("title")
            notes = o.get("notes", "")

            mime, _ = mimetypes.guess_type(str(abs_path))
            mime = mime or ""

            if kind == "IMAGE":
                if not mime.startswith("image/"):
                    log(f"[skip] not an image: {src_rel} mime={mime}")
                    continue

                corrected = _prepare_image_source(abs_path)
                transforms = o.get("transforms", [])
                created_any = False

                for t in o["target_sizes"]:
                    tw, th = int(t["w"]), int(t["h"])
                    out_path = _apply_image_transforms(corrected, tw, th, transforms)

                    cid = await _create_image_creative(
                        client, ad_account_id, product_id, out_path, title=title or f"CR_{corrected.stem}_{tw}x{th}"
                    )
                    buckets[group].append(cid)
                    created_any = True
                    log(f"[ok] IMAGE {cid} {tw}x{th} group={group}  {notes}")

                if not created_any:
                    log(f"[skip] no image outputs created: {src_rel}")

            else:  # VIDEO
                if not mime.startswith("video/"):
                    log(f"[skip] not a video: {src_rel} mime={mime}")
                    continue

                endcard_cfg = o["endcard"]
                mode = endcard_cfg["mode"]
                ts = endcard_cfg["target_size"]
                tw, th = int(ts["w"]), int(ts["h"])

                endcard = find_sidecar_endcard(abs_path)

                if mode == "SIDECAR_ONLY" and endcard is None:
                    log(f"[skip] video missing sidecar endcard: {src_rel}")
                    continue

                if mode in ("EXTRACT_ONLY", "SIDECAR_OR_EXTRACT") and endcard is None:
                    extracted = extract_endcard_from_video(str(abs_path))
                    if extracted:
                        endcard = Path(extracted)

                if endcard is None or not endcard.exists():
                    log(f"[skip] video endcard not available (mode={mode}): {src_rel}")
                    continue

                # Ensure endcard is a supported size
                endcard_prepared = _prepare_endcard_image(endcard, tw, th)

                cid = await _create_video_creative(
                    client, ad_account_id, product_id, abs_path, endcard_prepared, title=title or f"CR_{abs_path.stem}"
                )
                buckets[group].append(cid)
                log(f"[ok] VIDEO {cid} endcard={tw}x{th} group={group}  {notes}")

        # Create creative groups per plan groups
        result = {"creative_groups": [], "buckets": buckets}

        for g in groups:
            name = g["name"]
            tlid = g["tracking_link_id"]
            ids = buckets.get(name, [])
            if not ids:
                log(f"[skip] group empty: {name}")
                continue

            cg_body = {
                "ad_account_id": ad_account_id,
                "product_id": product_id,
                "title": f"{name}_{len(ids)}",
                "description": "Created via Streamlit LLM plan",
                "enabling_state": "ENABLED",
                "tracking_link_id": tlid,
                "creative_ids": ids,
            }
            cg_resp = await client.create_creative_group(ad_account_id, product_id, cg_body)
            cg = cg_resp.get("creative_group", cg_resp)
            result["creative_groups"].append({"name": name, "id": cg["id"], "creative_count": len(ids)})
            log(f"[ok] CreativeGroup {cg['id']} name={name} creatives={len(ids)}")

        return result

    finally:
        await client.close()