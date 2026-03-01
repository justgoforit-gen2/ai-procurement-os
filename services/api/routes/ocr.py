"""OCR routes — stub.

Policy:
- Response contains metadata only (page_count, item_count, doc_hash).
- Extracted text is NEVER returned in the response or logged.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, UploadFile

from proc_core.audit.events import build_event
from proc_core.audit.sink import emit
from proc_core.ocr import parse_document

router = APIRouter()


async def _read_limited_upload(request: Request, file: UploadFile) -> bytes:
    sec = getattr(request.app.state, "security", {}) or {}
    upload = sec.get("upload", {}) or {}

    allowed = upload.get("allowed_mime_types") or []
    if allowed and file.content_type not in allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported MIME type: {file.content_type}")

    max_mb = upload.get("max_file_size_mb")
    if max_mb is None:
        # Default: no limit in config (dev only)
        return await file.read()

    try:
        max_bytes = int(max_mb) * 1024 * 1024
    except Exception:
        return await file.read()

    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large (max {max_mb} MB)")
    return data


@router.get("/health")
def ocr_health() -> dict:
    return {"module": "ocr", "status": "ok"}


@router.post("/parse")
async def parse(request: Request, file: UploadFile) -> dict:
    """Accept a file upload and return structural metadata (no content)."""
    file_bytes = await _read_limited_upload(request, file)
    result = parse_document(file_bytes, filename=file.filename or "")

    event = build_event(
        module="ocr",
        action="parse",
        status="ok",
        file_bytes=file_bytes,
        file_count=1,
        item_count=result.get("item_count"),
    )
    emit(event)

    # Return only metadata — never raw text or line-item content
    return {
        "doc_hash": event.doc_hash,
        "page_count": result.get("page_count"),
        "item_count": result.get("item_count"),
        "engine": result.get("engine"),
        "status": result.get("status"),
    }
