"""
loader.py -- Load procurement CSVs and apply column mapping.

Usage:
    from proc_core.spend.loader import load_all
    df_po, df_items, df_suppliers = load_all("data/samples/", mapping="default")
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import yaml


def _load_mapping(config_root: Path, mapping: str) -> dict:
    path = config_root / "config" / "data" / "column_map" / f"{mapping}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Column mapping not found: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_file(data_dir: Path, pattern: str) -> Optional[Path]:
    matches = list(data_dir.glob(pattern))
    if not matches:
        return None
    return sorted(matches)[-1]  # latest file if multiple


def _apply_mapping(df: pd.DataFrame, canonical_columns: dict) -> pd.DataFrame:
    """Rename actual CSV columns to canonical names."""
    rename = {v: k for k, v in canonical_columns.items() if v in df.columns}
    df = df.rename(columns=rename)
    return df


def load_all(
    data_dir: str | Path,
    mapping: str = "default",
    config_root: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load all three procurement CSVs with column mapping applied.

    Returns:
        (df_po, df_items, df_suppliers) -- all using canonical column names
    """
    data_dir = Path(data_dir)
    config_root = Path(config_root) if config_root else Path(__file__).parents[3]

    cfg = _load_mapping(config_root, mapping)

    # --- PO transactions ---
    po_pattern = cfg["po_transactions"]["file_pattern"]
    po_file = _find_file(data_dir, po_pattern)
    if po_file is None:
        raise FileNotFoundError(f"No file matching '{po_pattern}' in {data_dir}")
    df_po = pd.read_csv(po_file, encoding="utf-8-sig", parse_dates=["posting_date"])
    df_po = _apply_mapping(df_po, cfg["po_transactions"]["canonical_columns"])
    df_po["posting_date"] = pd.to_datetime(df_po["posting_date"], errors="coerce")
    df_po["net_amount"] = pd.to_numeric(df_po["net_amount"], errors="coerce")
    df_po["unit_price"] = pd.to_numeric(df_po.get("unit_price", pd.Series(dtype=float)), errors="coerce")
    df_po["quantity"] = pd.to_numeric(df_po.get("quantity", pd.Series(dtype=float)), errors="coerce")

    # --- Items master ---
    items_pattern = cfg["items_master"]["file_pattern"]
    items_file = _find_file(data_dir, items_pattern)
    df_items = pd.DataFrame()
    if items_file:
        df_items = pd.read_csv(items_file, encoding="utf-8-sig")
        df_items = _apply_mapping(df_items, cfg["items_master"]["canonical_columns"])

    # --- Suppliers master ---
    sup_pattern = cfg["suppliers_master"]["file_pattern"]
    sup_file = _find_file(data_dir, sup_pattern)
    df_suppliers = pd.DataFrame()
    if sup_file:
        df_suppliers = pd.read_csv(sup_file, encoding="utf-8-sig")
        df_suppliers = _apply_mapping(df_suppliers, cfg["suppliers_master"]["canonical_columns"])

    return df_po, df_items, df_suppliers
