"""OCR Document Reader — Streamlit UI.

Entry point is intentionally thin:
  - File upload + "解析" button only.
  - All business logic is delegated to proc_core.ocr.
  - Audit logging via proc_core.audit (metadata only).
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make proc_core importable when running from project root via
#   streamlit run apps/OCR-doc-reader/app.py
_ROOT = Path(__file__).parents[2]
_PACKAGES = _ROOT / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from proc_core.audit.events import build_event   # noqa: E402
from proc_core.audit.sink import emit             # noqa: E402
from proc_core.ocr import parse_document          # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="OCR Document Reader", layout="centered")
st.title("OCR Document Reader")
st.caption("PDFまたは画像をアップロードして構造メタデータを抽出します。")

# ---------------------------------------------------------------------------
# Upload widget
# ---------------------------------------------------------------------------
uploaded = st.file_uploader(
    "ファイルを選択",
    type=["pdf", "png", "jpg", "jpeg", "tiff"],
    accept_multiple_files=False,
    help="対応形式: PDF / PNG / JPEG / TIFF（最大 20 MB）",
)

if uploaded:
    st.info(f"**{uploaded.name}** — {uploaded.size:,} bytes")

    _MAX_BYTES = 20 * 1024 * 1024
    if uploaded.size > _MAX_BYTES:
        st.error("ファイルサイズが上限（20 MB）を超えています")
        st.stop()

    if st.button("解析", type="primary"):
        file_bytes = uploaded.read()

        with st.spinner("解析中..."):
            try:
                result = parse_document(file_bytes, filename=uploaded.name)

                event = build_event(
                    module="ocr",
                    action="parse",
                    status="ok",
                    file_bytes=file_bytes,
                    file_count=1,
                    item_count=result.get("item_count"),
                )
                emit(event)

                st.success("解析完了")
                # Display metadata only — never raw extracted text
                st.json({
                    "doc_hash": event.doc_hash,
                    "page_count": result.get("page_count"),
                    "item_count": result.get("item_count"),
                    "engine": result.get("engine"),
                    "status": result.get("status"),
                })

            except Exception as exc:
                event = build_event(
                    module="ocr",
                    action="parse",
                    status="error",
                    file_bytes=file_bytes,
                    file_count=1,
                    error_code=type(exc).__name__,
                )
                emit(event)
                st.error(f"エラー: {type(exc).__name__}")
