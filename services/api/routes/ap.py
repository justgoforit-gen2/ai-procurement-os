"""Accounts Payable routes — stub."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, UploadFile

router = APIRouter()


async def _read_limited_upload(request: Request, file: UploadFile) -> bytes:
    sec = getattr(request.app.state, "security", {}) or {}
    upload = sec.get("upload", {}) or {}

    allowed = upload.get("allowed_mime_types") or []
    if allowed and file.content_type not in allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported MIME type: {file.content_type}")

    max_mb = upload.get("max_file_size_mb")
    if max_mb is None:
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
def ap_health() -> dict:
    return {"module": "ap", "status": "ok"}


@router.post("/invoice")
async def process_invoice(request: Request, file: UploadFile) -> dict:
    """Stub: process an invoice and return metadata."""
    # Enforce upload safety limits (size/MIME)
    await _read_limited_upload(request, file)
    # TODO: call proc_core.ap.process_invoice(await file.read(), filename=file.filename)
    return {"status": "stub"}
