"""
db_utils.py -- SQLite connection utilities for procurement.db

Separate from apps/rfq/db.py (which manages rfq.db / RFQ workflow).
This module manages procurement.db: PO transactions + master data.

Usage:
    from scripts.db_utils import get_procurement_conn, query_df, DB_PATH
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd

# data/procurement.db (PO・マスターデータ専用)
DB_PATH = Path(__file__).parents[1] / "data" / "procurement.db"


@contextmanager
def get_procurement_conn(db_path: Path | str | None = None):
    """procurement.db への接続コンテキストマネージャ"""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_df(sql: str, params: tuple = (), db_path: Path | str | None = None) -> pd.DataFrame:
    """SQLを発行してDataFrameで返す"""
    with get_procurement_conn(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def execute(sql: str, params: tuple = (), db_path: Path | str | None = None) -> None:
    """単一SQL実行（INSERT/UPDATE/DELETE用）"""
    with get_procurement_conn(db_path) as conn:
        conn.execute(sql, params)


def table_exists(table_name: str, db_path: Path | str | None = None) -> bool:
    """テーブルが存在するか確認"""
    with get_procurement_conn(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    return row is not None


def row_count(table_name: str, db_path: Path | str | None = None) -> int:
    """テーブルのレコード数を返す"""
    if not table_exists(table_name, db_path):
        return 0
    with get_procurement_conn(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]


def list_tables(db_path: Path | str | None = None) -> list[str]:
    """全テーブル名を返す"""
    with get_procurement_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


def drop_table(table_name: str, db_path: Path | str | None = None) -> None:
    """テーブルを削除（初期ロード時の再作成用）"""
    with get_procurement_conn(db_path) as conn:
        conn.execute(f"DROP TABLE IF EXISTS [{table_name}]")


# ---------------------------------------------------------------------------
# サンプルSQLクエリ集
# ---------------------------------------------------------------------------

SAMPLE_QUERIES: dict[str, str] = {
    "supplier_spend": """
        -- サプライヤー別発注額（上位20社）
        SELECT
            po.supplier_id,
            po.supplier_name,
            COUNT(DISTINCT po.po_number) AS po_count,
            SUM(po.net_amount)           AS total_amount
        FROM po_transactions po
        GROUP BY po.supplier_id, po.supplier_name
        ORDER BY total_amount DESC
        LIMIT 20
    """,
    "category_spend": """
        -- カテゴリ別Spend（大分類）
        SELECT
            po.cat_large_name,
            COUNT(DISTINCT po.po_number) AS po_count,
            SUM(po.net_amount)           AS total_spend
        FROM po_transactions po
        GROUP BY po.cat_large_name
        ORDER BY total_spend DESC
    """,
    "department_spend": """
        -- 部門別発注額
        SELECT
            po.department_name,
            COUNT(DISTINCT po.po_number) AS po_count,
            SUM(po.net_amount)           AS total_spend
        FROM po_transactions po
        GROUP BY po.department_name
        ORDER BY total_spend DESC
    """,
    "monthly_trend": """
        -- 月次発注推移
        SELECT
            strftime('%Y-%m', po.posting_date) AS ym,
            COUNT(DISTINCT po.po_number)       AS po_count,
            SUM(po.net_amount)                 AS total_spend
        FROM po_transactions po
        GROUP BY ym
        ORDER BY ym
    """,
    "supplier_with_employee": """
        -- バイヤー別発注件数・金額
        SELECT
            po.buyer,
            COUNT(DISTINCT po.po_number) AS po_count,
            SUM(po.net_amount)           AS total_amount
        FROM po_transactions po
        GROUP BY po.buyer
        ORDER BY total_amount DESC
    """,
    "supplier_master_join": """
        -- サプライヤーマスタ結合（規模別）
        SELECT
            sm.vendor_size,
            COUNT(DISTINCT po.supplier_id) AS supplier_count,
            SUM(po.net_amount)             AS total_spend
        FROM po_transactions po
        LEFT JOIN suppliers_master sm ON po.supplier_id = sm.supplier_id
        GROUP BY sm.vendor_size
        ORDER BY total_spend DESC
    """,
}


if __name__ == "__main__":
    print(f"procurement.db path: {DB_PATH}")
    print(f"Tables: {list_tables()}")
    for tbl in list_tables():
        print(f"  {tbl}: {row_count(tbl)} rows")
