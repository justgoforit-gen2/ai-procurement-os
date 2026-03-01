"""OCR module — reads runtime config from config/ocr/default.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


def _load_ocr_config() -> dict:
    config_path = Path(__file__).parents[3] / "config" / "ocr" / "default.yaml"
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_document(file_bytes: bytes, *, filename: str = "") -> dict:
    """Parse a document and return structured metadata (no content).

    Policy: extracted text, line items, and supplier data are NEVER returned.
    Only counts and structural metadata are safe to surface.
    """
    cfg = _load_ocr_config()
    # TODO: implement real OCR using cfg["engine"]
    return {
        "engine": cfg.get("engine", "stub"),
        "filename": filename,
        "page_count": 1,    # stub
        "item_count": 0,    # stub — count only, no content
        "char_count": 0,    # stub
        "status": "stub",
    }
