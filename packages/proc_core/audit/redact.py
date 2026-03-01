"""Safety redaction — strips any accidental content fields before emitting."""
from __future__ import annotations

from proc_core.audit.events import AuditEvent

# Exhaustive allowlist of fields permitted in an audit record.
_SAFE_FIELDS = {
    "request_id",
    "timestamp",
    "module",
    "action",
    "status",
    "doc_hash",
    "file_count",
    "item_count",
    "version",
    "error_code",
}


def redact(event: AuditEvent) -> dict:
    """Return a dict containing only safe metadata fields.

    Any field not in _SAFE_FIELDS is silently dropped, providing a
    defence-in-depth layer against accidental content leakage.
    """
    raw = event.model_dump()
    return {k: v for k, v in raw.items() if k in _SAFE_FIELDS}
