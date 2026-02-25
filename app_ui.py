import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import streamlit as st
from openai import OpenAI

import executor


MIN_LLM_INTERVAL_SEC = 1.5
DEFAULT_MODEL = "gpt-4.1-mini"


I18N = {
    "en": {
        "app_title": "Moloco Creative Agent",
        "sidebar_config": "Config",
        "sidebar_language": "Language",
        "lang_left": "EN",
        "lang_right": "中文",
        "ad_account_id": "ad_account_id",
        "product_id": "product_id",
        "tracking_link_id": "tracking_link_id",
        "upload_scan": "Upload & Scan",
        "upload_zip": "Upload ZIP",
        "scan_done": "Scan completed",
        "upload_hint": "Please upload a ZIP",
        "request_preview": "Request & Preview",
        "request": "Request",
        "generate": "Generate preview",
        "preview_ready": "Preview ready",
        "preview_failed": "Failed to generate preview",
        "execute": "Execute",
        "start": "Start",
        "done": "Done",
        "failed": "Failed",
        "rate_limited": "Too many requests. Please wait a moment.",
        "missing_secret": "Missing secret: {name}",
        "groups": "Groups",
        "outputs": "Outputs",
        "image": "Image",
        "video": "Video",
        "unknown": "Unknown",
        "arrow": "→",
        "note_prefix": "-",
        "endcard": "endcard",
        "endcard_sidecar_only": "use sidecar _endcard only",
        "endcard_extract_only": "extract frame endcard",
        "endcard_sidecar_or_extract": "prefer sidecar _endcard, else extract",
        "skip": "Skipped: {msg}",
        "created_image": "Created image: {size} → {group}",
        "created_video": "Created video: endcard {size} → {group}",
        "created_group": "Created group: {name} ({count})",
        "default_request": "Split images and videos into two groups; generate one best-fit size for images; for videos, prefer sidecar _endcard, otherwise extract endcard from video.",
        "count_line": "{name}: {count}",
    },
    "zh": {
        "app_title": "Moloco Creative Agent",
        "sidebar_config": "配置",
        "sidebar_language": "语言",
        "lang_left": "EN",
        "lang_right": "中文",
        "ad_account_id": "ad_account_id",
        "product_id": "product_id",
        "tracking_link_id": "tracking_link_id",
        "upload_scan": "上传与扫描",
        "upload_zip": "上传ZIP",
        "scan_done": "扫描完成",
        "upload_hint": "请上传ZIP",
        "request_preview": "需求与方案预览",
        "request": "需求描述",
        "generate": "生成方案",
        "preview_ready": "方案生成完成",
        "preview_failed": "方案生成失败",
        "execute": "执行",
        "start": "开始执行",
        "done": "执行完成",
        "failed": "执行失败",
        "rate_limited": "请求太频繁，请稍等再试。",
        "missing_secret": "缺少 secret：{name}",
        "groups": "素材组",
        "outputs": "素材生成",
        "image": "图片",
        "video": "视频",
        "unknown": "未知类型",
        "arrow": "→",
        "note_prefix": "-",
        "endcard": "endcard",
        "endcard_sidecar_only": "使用同名_endcard",
        "endcard_extract_only": "抽帧生成endcard",
        "endcard_sidecar_or_extract": "优先同名_endcard，否则抽帧",
        "skip": "跳过：{msg}",
        "created_image": "已创建图片：{size} → {group}",
        "created_video": "已创建视频：endcard {size} → {group}",
        "created_group": "已创建素材组：{name}（{count}）",
        "default_request": "图片和视频分开两个组；图片只生成一个最合适尺寸；视频优先同名_endcard，否则抽帧生成endcard。",
        "count_line": "{name}：{count}",
    },
}


def t(key: str) -> str:
    lang = st.session_state.get("lang", "en")
    return I18N[lang][key]


def rate_limit(key: str, min_interval: float) -> None:
    now = time.time()
    last = st.session_state.get(key, 0.0)
    if now - last < min_interval:
        st.warning(t("rate_limited"))
        st.stop()
    st.session_state[key] = now


def get_secret(name: str) -> str:
    if name in st.secrets:
        return st.secrets[name]
    v = os.getenv(name)
    if v:
        return v
    st.error(t("missing_secret").format(name=name))
    st.stop()


def get_openai_client() -> OpenAI:
    return OpenAI(api_key=get_secret("OPENAI_API_KEY"))


def build_human_preview(plan: Dict[str, Any]) -> str:
    groups = plan.get("groups", [])
    outputs = plan.get("outputs", [])

    group_names = [g.get("name", "") for g in groups if g.get("name")]
    if not group_names:
        group_names = ["all"]

    per_src: Dict[str, List[Dict[str, Any]]] = {}
    for o in outputs:
        src = o.get("source_rel_path", "")
        per_src.setdefault(src, []).append(o)

    lines: List[str] = []
    lines.append(t("groups"))
    for n in group_names:
        lines.append(f"- {n}")

    lines.append("")
    lines.append(t("outputs"))

    for src, items in per_src.items():
        lines.append(f"\n- {src}")
        for o in items:
            kind = (o.get("kind") or "").upper()
            grp = o.get("group") or ""
            notes = (o.get("notes") or "").strip()

            if kind == "IMAGE":
                ts = o.get("target_sizes", [])
                sizes = [f"{tt['w']}x{tt['h']}" for tt in ts if isinstance(tt, dict) and "w" in tt and "h" in tt]
                if not sizes:
                    sizes = ["?"]
                lines.append(f"  - {t('image')}: {', '.join(sizes)} {t('arrow')} {grp or '—'}")

            elif kind == "VIDEO":
                ec = o.get("endcard", {}) or {}
                mode = (ec.get("mode") or "").upper()
                ts = ec.get("target_size") or {}
                tsize = f"{ts.get('w','?')}x{ts.get('h','?')}"

                if mode == "SIDECAR_ONLY":
                    mode_text = t("endcard_sidecar_only")
                elif mode == "EXTRACT_ONLY":
                    mode_text = t("endcard_extract_only")
                else:
                    mode_text = t("endcard_sidecar_or_extract")

                lines.append(f"  - {t('video')}: {t('endcard')} {mode_text}, {tsize} {t('arrow')} {grp or '—'}")
            else:
                lines.append(f"  - {t('unknown')}: {kind} {t('arrow')} {grp or '—'}")

            if notes:
                lines.append(f"    {t('note_prefix')} {notes}")

    return "\n".join(lines)


def log_to_human(line: str) -> Optional[str]:
    s = line.strip()
    if not s or s.startswith("[start]") or s.startswith("[done]"):
        return None

    m = re.search(r"IMAGE\s+([A-Za-z0-9_-]+)\s+(\d+x\d+)\s+group=([^\s]+)", s)
    if m:
        return t("created_image").format(size=m.group(2), group=m.group(3))

    m = re.search(r"VIDEO\s+([A-Za-z0-9_-]+)\s+endcard=(\d+x\d+)\s+group=([^\s]+)", s)
    if m:
        return t("created_video").format(size=m.group(2), group=m.group(3))

    m = re.search(r"CreativeGroup\s+([A-Za-z0-9_-]+)\s+name=([^\s]+)\s+creatives=(\d+)", s)
    if m:
        return t("created_group").format(name=m.group(2), count=m.group(3))

    if s.startswith("[skip]"):
        msg = s.replace("[skip]", "").strip()
        msg = re.sub(r"\s+mime=.*$", "", msg)
        return t("skip").format(msg=msg)

    return None


# ---------------- UI ----------------
st.set_page_config(page_title="Moloco Creative Agent", layout="wide")

# default language = English
if "lang" not in st.session_state:
    st.session_state["lang"] = "en"

# sidebar: icon + language toggle + config
with st.sidebar:
    # icon at the top
    icon_path = "Logo.webp"
    if os.path.exists(icon_path):
        st.image(icon_path, use_column_width=True)

    st.header(t("sidebar_language"))
    # toggle: False -> EN, True -> 中文
    zh_on = st.toggle(
        label="",
        value=(st.session_state["lang"] == "zh"),
        help=None,
    )
    st.session_state["lang"] = "zh" if zh_on else "en"

st.title(t("app_title"))

openai_client = get_openai_client()

with st.sidebar:
    st.header(t("sidebar_config"))
    ad_account_id = st.text_input(t("ad_account_id"), value="SCqNJ4UHyMY0Xls7")
    product_id = st.text_input(t("product_id"), value="qK2LyJb6j28jWbgU")
    tracking_link_id = st.text_input(t("tracking_link_id"), value="rlu1Dquo0n6LM9sT")

# state
if "workspace" not in st.session_state:
    st.session_state["workspace"] = None
if "files" not in st.session_state:
    st.session_state["files"] = []
if "plan" not in st.session_state:
    st.session_state["plan"] = None
if "preview" not in st.session_state:
    st.session_state["preview"] = ""
if "human_logs" not in st.session_state:
    st.session_state["human_logs"] = []

# ---- Upload & scan ----
st.header(t("upload_scan"))
zip_file = st.file_uploader(t("upload_zip"), type=["zip"])

if zip_file is not None:
    if st.session_state["workspace"] is not None:
        executor.cleanup_workspace(st.session_state["workspace"])
        st.session_state["workspace"] = None

    ws = executor.create_workspace_from_zip(zip_file.getbuffer().tobytes())
    st.session_state["workspace"] = ws
    st.session_state["files"] = executor.scan_assets(ws.root_dir)
    st.session_state["plan"] = None
    st.session_state["preview"] = ""
    st.session_state["human_logs"] = []
    st.success(t("scan_done"))

files: List[Dict[str, Any]] = st.session_state.get("files", [])
ws = st.session_state.get("workspace")

if files:
    st.dataframe(files, use_container_width=True)
else:
    st.info(t("upload_hint"))

# ---- Request & preview ----
st.header(t("request_preview"))
user_request = st.text_area(
    t("request"),
    value=t("default_request"),
    height=90,
)

generate_btn = st.button(t("generate"), disabled=not bool(files))
if generate_btn:
    rate_limit("_llm_ts", MIN_LLM_INTERVAL_SEC)

    schema = {
        "groups": [{"name": "string", "tracking_link_id": "string"}],
        "outputs": [
            {
                "source_rel_path": "string",
                "kind": "IMAGE|VIDEO",
                "group": "string",
                "title": "string",
                "notes": "string",
                "target_sizes": [{"w": 768, "h": 1024}],
                "transforms": ["LETTERBOX", "COMPRESS_500KB"],
                "endcard": {"mode": "SIDECAR_OR_EXTRACT", "target_size": {"w": 768, "h": 1024}},
            }
        ],
    }

    payload = {
        "request": user_request,
        "files": files,
        "supported_image_sizes": sorted([f"{w}x{h}" for (w, h) in executor.SUPPORTED_IMAGE_SIZES]),
        "schema": schema,
        "default_tracking_link_id": tracking_link_id,
    }

    system_rules = (
        "Return STRICT JSON only. "
        "Use only source_rel_path that exists in files[].rel_path. "
        "All IMAGE target_sizes and VIDEO endcard.target_size must be from supported_image_sizes. "
        "If an input image is not a supported size, plan to letterbox to the target size and compress <=500KB. "
        "VIDEO must include an endcard plan: prefer sidecar *_endcard if present; otherwise extract a frame; "
        "endcard must be letterboxed to a supported size."
    )

    resp = openai_client.responses.create(
        model=DEFAULT_MODEL,
        input=[
            {"role": "system", "content": system_rules},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )

    raw = resp.output_text
    try:
        plan = json.loads(raw)
        _ = executor.validate_and_normalize_plan(plan, tracking_link_id_fallback=tracking_link_id)
        st.session_state["plan"] = plan
        st.session_state["preview"] = build_human_preview(plan)
        st.success(t("preview_ready"))
    except Exception as e:
        st.error(f"{t('preview_failed')}: {e}")
        st.code(raw)

if st.session_state.get("preview"):
    st.text(st.session_state["preview"])

# ---- Execute ----
st.header(t("execute"))
log_box = st.empty()


def add_human_log(msg: str):
    st.session_state["human_logs"].append(msg)
    log_box.write("\n".join(f"- {x}" for x in st.session_state["human_logs"][-60:]))


can_execute = bool(ws) and bool(st.session_state.get("plan"))
exec_btn = st.button(t("start"), disabled=not can_execute)

if exec_btn:
    plan = st.session_state["plan"]
    moloco_api_key = get_secret("MOLOCO_API_KEY")

    st.session_state["human_logs"] = []
    add_human_log(t("start"))

    def log_cb(line: str):
        msg = log_to_human(line)
        if msg:
            add_human_log(msg)

    try:
        result = executor.execute_plan_sync(
            plan,
            moloco_api_key=moloco_api_key,
            root_dir=ws.root_dir,
            ad_account_id=ad_account_id,
            product_id=product_id,
            default_tracking_link_id=tracking_link_id,
            log=log_cb,
        )

        groups = result.get("creative_groups", [])
        add_human_log(t("done"))
        for g in groups:
            add_human_log(t("count_line").format(name=g["name"], count=g["creative_count"]))
    except Exception:
        add_human_log(t("failed"))
        raise