"""Audit event builder — metadata only, no sensitive content."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    module: str
    action: str
    status: str          # "ok" | "error" | "rejected"
    doc_hash: str | None = None   # SHA-256 of uploaded bytes — never the content
    file_count: int | None = None
    item_count: int | None = None
    version: str = "1.0"
    error_code: str | None = None

    # -----------------------------------------------------------------------
    # POLICY: supplier names, prices, line items, PDF text MUST NOT appear here.
    # -----------------------------------------------------------------------


def build_event(
    module: str,
    action: str,
    status: str,
    *,
    file_bytes: bytes | None = None,
    file_count: int | None = None,
    item_count: int | None = None,
    error_code: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """Build an AuditEvent from call-site metadata.

    Args:
        module:      Module name (spend / rfx / ocr / ap).
        action:      Action performed (upload / parse / classify / …).
        status:      "ok" | "error" | "rejected".
        file_bytes:  Raw file bytes — only the SHA-256 hash is stored.
        file_count:  Number of files processed.
        item_count:  Number of line items detected (count, not content).
        error_code:  Machine-readable error code.
        request_id:  Caller-supplied ID; auto-generated if None.
    """
    doc_hash = (
        hashlib.sha256(file_bytes).hexdigest() if file_bytes is not None else None
    )
    kwargs: dict[str, Any] = dict(
        module=module,
        action=action,
        status=status,
        doc_hash=doc_hash,
        file_count=file_count,
        item_count=item_count,
        error_code=error_code,
    )
    if request_id:
        kwargs["request_id"] = request_id
    return AuditEvent(**kwargs)
