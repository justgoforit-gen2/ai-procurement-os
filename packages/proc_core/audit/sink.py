"""Audit sink — writes redacted audit events to stdout or a log file.

Policy:
- Only redacted (metadata-only) payloads are written.
- Request/response bodies are NEVER written here or anywhere else.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from proc_core.audit.events import AuditEvent
from proc_core.audit.redact import redact


def emit(event: AuditEvent, *, dest: TextIO | Path | None = None) -> None:
    """Emit a redacted audit event as a JSON line.

    Args:
        event: The AuditEvent to emit.
        dest:  None → stdout | Path → append to file | TextIO → write to stream.
    """
    payload = json.dumps(redact(event), ensure_ascii=False)

    if dest is None:
        print(payload, file=sys.stdout, flush=True)
    elif isinstance(dest, Path):
        with dest.open("a", encoding="utf-8") as f:
            f.write(payload + "\n")
    else:
        print(payload, file=dest, flush=True)
