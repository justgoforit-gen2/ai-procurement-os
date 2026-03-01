"""RFx routes — stub."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def rfx_health() -> dict:
    return {"module": "rfx", "status": "ok"}


@router.post("/create")
def create_rfx(payload: dict) -> dict:
    """Stub: create an RFx document."""
    # TODO: call proc_core.rfx.create_rfx(payload)
    return {"status": "stub"}
