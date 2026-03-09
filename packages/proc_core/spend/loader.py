"""
loader.py -- Load procurement data (SQLite first, CSV fallback).

Primary source: data/procurement.db (populated by scripts/load_csv_to_sqlite.py)
Fallback      : direct CSV read via column_map/default.yaml

Usage:
    from proc_core.spend.loader import load_all
    df_po, df_items, df_suppliers = load_all("data/samples/", mapping="default")
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

# procurement.db のデフォルトパス (packages/proc_core/spend/ から3階層上 = プロジェクトルート)
_PROCUREMENT_DB = Path(__file__).parents[3] / "data" / "procurement.db"


# ---------------------------------------------------------------------------
# SQLite読込
# ---------------------------------------------------------------------------
def _load_from_sqlite(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    """procurement.db からDataFrameを返す。DBまたはテーブルがなければ None を返す。"""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table'", conn
        )["name"].tolist()

        if "po_transactions" not in tables:
            conn.close()
            return None

        df_po = pd.read_sql_query("SELECT * FROM po_transactions", conn)
        df_po["posting_date"] = pd.to_datetime(df_po["posting_date"], errors="coerce")
        df_po["net_amount"]   = pd.to_numeric(df_po.get("net_amount",   pd.Series(dtype=float)), errors="coerce")
        df_po["unit_price"]   = pd.to_numeric(df_po.get("unit_price",   pd.Series(dtype=float)), errors="coerce")
        df_po["quantity"]     = pd.to_numeric(df_po.get("quantity",     pd.Series(dtype=float)), errors="coerce")

        df_items = pd.read_sql_query("SELECT * FROM items_master", conn) \
            if "items_master" in tables else pd.DataFrame()

        df_suppliers = pd.read_sql_query("SELECT * FROM suppliers_master", conn) \
            if "suppliers_master" in tables else pd.DataFrame()

        conn.close()
        return df_po, df_items, df_suppliers
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CSV読込（フォールバック）
# ---------------------------------------------------------------------------
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
    return sorted(matches)[-1]


def _apply_mapping(df: pd.DataFrame, canonical_columns: dict) -> pd.DataFrame:
    rename = {v: k for k, v in canonical_columns.items() if v in df.columns}
    return df.rename(columns=rename)


def _load_from_csv(
    data_dir: Path,
    config_root: Path,
    mapping: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cfg = _load_mapping(config_root, mapping)

    po_file = _find_file(data_dir, cfg["po_transactions"]["file_pattern"])
    if po_file is None:
        raise FileNotFoundError(f"No PO CSV in {data_dir}")
    df_po = pd.read_csv(po_file, encoding="utf-8-sig", parse_dates=["posting_date"])
    df_po = _apply_mapping(df_po, cfg["po_transactions"]["canonical_columns"])
    df_po["posting_date"] = pd.to_datetime(df_po["posting_date"], errors="coerce")
    df_po["net_amount"]   = pd.to_numeric(df_po["net_amount"],   errors="coerce")
    df_po["unit_price"]   = pd.to_numeric(df_po.get("unit_price",   pd.Series(dtype=float)), errors="coerce")
    df_po["quantity"]     = pd.to_numeric(df_po.get("quantity",     pd.Series(dtype=float)), errors="coerce")

    items_file = _find_file(data_dir, cfg["items_master"]["file_pattern"])
    df_items = pd.DataFrame()
    if items_file:
        df_items = pd.read_csv(items_file, encoding="utf-8-sig")
        df_items = _apply_mapping(df_items, cfg["items_master"]["canonical_columns"])

    sup_file = _find_file(data_dir, cfg["suppliers_master"]["file_pattern"])
    df_suppliers = pd.DataFrame()
    if sup_file:
        df_suppliers = pd.read_csv(sup_file, encoding="utf-8-sig")
        df_suppliers = _apply_mapping(df_suppliers, cfg["suppliers_master"]["canonical_columns"])

    return df_po, df_items, df_suppliers


# ---------------------------------------------------------------------------
# 公開API
# ---------------------------------------------------------------------------
def load_all(
    data_dir: str | Path,
    mapping: str = "default",
    config_root: str | Path | None = None,
    db_path: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    調達データを読み込む。
    1. procurement.db が存在すればSQLiteから読込（高速）
    2. なければCSVから読込（初回・フォールバック）

    Returns:
        (df_po, df_items, df_suppliers) -- 正規カラム名を使用
    """
    data_dir    = Path(data_dir)
    config_root = Path(config_root) if config_root else Path(__file__).parents[3]
    _db_path    = Path(db_path) if db_path else _PROCUREMENT_DB

    # SQLite 優先
    sqlite_result = _load_from_sqlite(_db_path)
    if sqlite_result is not None:
        return sqlite_result

    # フォールバック: CSV
    return _load_from_csv(data_dir, config_root, mapping)


def load_employees(
    data_dir: str | Path | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """
    従業員マスターを読み込む。
    SQLite（employee_master テーブル）→ CSVフォールバック。
    """
    _db_path = Path(db_path) if db_path else _PROCUREMENT_DB

    if _db_path.exists():
        try:
            conn = sqlite3.connect(str(_db_path))
            tables = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table'", conn
            )["name"].tolist()
            if "employee_master" in tables:
                df = pd.read_sql_query("SELECT * FROM employee_master", conn)
                conn.close()
                return df
            conn.close()
        except Exception:
            pass

    # CSV フォールバック
    if data_dir is None:
        data_dir = Path(__file__).parents[3] / "data" / "samples"
    data_dir = Path(data_dir)
    matches = sorted(data_dir.glob("employee_master*.csv"))
    if matches:
        return pd.read_csv(matches[-1], encoding="utf-8-sig")
    return pd.DataFrame()
