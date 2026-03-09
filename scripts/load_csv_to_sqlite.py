"""
load_csv_to_sqlite.py -- CSV → SQLite (data/procurement.db) 取込スクリプト

使い方:
    python scripts/load_csv_to_sqlite.py            # 初期ロード（全テーブル）
    python scripts/load_csv_to_sqlite.py --mode update   # 更新ロード
    python scripts/load_csv_to_sqlite.py --table po_transactions  # 単テーブル
    python scripts/load_csv_to_sqlite.py --dry-run  # 確認のみ（書き込みなし）

オプション:
    --mode    init | update  (default: init)
    --table   テーブル名（省略時は全テーブル）
    --config  設定ファイルパス (default: config/import_tables.yaml)
    --data    CSV格納ディレクトリ (default: data/samples/)
    --db      DBファイルパス (default: data/procurement.db)
    --dry-run 書き込まずに確認のみ
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

# プロジェクトルートを sys.path に追加
PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.db_utils import get_procurement_conn, DB_PATH
from scripts.normalize_columns import apply_column_map, normalize_dataframe

# ---------------------------------------------------------------------------
# ロガー設定
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 設定ファイル読込
# ---------------------------------------------------------------------------
def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 単テーブル取込
# ---------------------------------------------------------------------------
def import_table(
    table_key: str,
    table_cfg: dict,
    data_dir: Path,
    db_path: Path,
    mode: str = "init",
    dry_run: bool = False,
) -> dict:
    """
    Returns:
        dict with keys: table, file, read_count, loaded_count, skipped_count,
                        error_count, errors
    """
    result: dict = {
        "table": table_cfg["table_name"],
        "file": None,
        "read_count": 0,
        "loaded_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "errors": [],
    }

    # ── CSVファイル特定 ────────────────────────────────────────────────────
    pattern = table_cfg["file_pattern"]
    matches = sorted(data_dir.glob(pattern))
    if not matches:
        msg = f"No CSV file matching '{pattern}' in {data_dir}"
        log.warning(msg)
        result["errors"].append(msg)
        return result

    csv_path = matches[-1]  # 最新ファイル
    result["file"] = str(csv_path)
    log.info(f"[{table_cfg['table_name']}] Loading: {csv_path.name}")

    # ── CSV読込 ──────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, low_memory=False)
    except Exception as e:
        result["errors"].append(f"CSV read error: {e}")
        result["error_count"] = 1
        return result

    result["read_count"] = len(df)
    log.info(f"[{table_cfg['table_name']}] Read {len(df)} rows from CSV")

    # ── カラムマッピング ──────────────────────────────────────────────────
    column_map = table_cfg.get("column_map", {})
    df = apply_column_map(df, column_map)

    # ── 型正規化 ──────────────────────────────────────────────────────────
    df = normalize_dataframe(
        df,
        date_cols=table_cfg.get("date_cols", []),
        numeric_cols=table_cfg.get("numeric_cols", []),
        bool_cols=table_cfg.get("bool_cols", []),
    )

    # ── 必須列チェック ────────────────────────────────────────────────────
    required = table_cfg.get("required_cols", [])
    before = len(df)
    for col in required:
        if col in df.columns:
            df = df[df[col].notna()]
    skipped = before - len(df)
    result["skipped_count"] = skipped
    if skipped > 0:
        log.warning(f"[{table_cfg['table_name']}] Skipped {skipped} rows (missing required cols)")

    if dry_run:
        log.info(f"[DRY-RUN] {table_cfg['table_name']}: would write {len(df)} rows (mode={mode})")
        result["loaded_count"] = len(df)
        return result

    # ── SQLite書込 ────────────────────────────────────────────────────────
    table_name = table_cfg["table_name"]
    pks = table_cfg.get("primary_key", [])

    with get_procurement_conn(db_path) as conn:
        if mode == "init":
            # 全件置換: テーブル削除→再作成
            conn.execute(f"DROP TABLE IF EXISTS [{table_name}]")
            df.to_sql(table_name, conn, if_exists="replace", index=False)
            # 主キーインデックス作成
            if pks:
                idx_cols = ", ".join(f"[{c}]" for c in pks)
                conn.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_pk "
                    f"ON [{table_name}] ({idx_cols})"
                )
            result["loaded_count"] = len(df)
            log.info(f"[{table_name}] Init load: {len(df)} rows written")

        elif mode == "update":
            # 更新ロード: 既存キーはスキップ（INSERT OR IGNORE）
            existing_count = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
            if existing_count == 0:
                # テーブルが空なら初期ロードと同じ
                df.to_sql(table_name, conn, if_exists="replace", index=False)
                result["loaded_count"] = len(df)
            else:
                cols = list(df.columns)
                placeholders = ", ".join("?" * len(cols))
                col_list = ", ".join(f"[{c}]" for c in cols)
                sql = f"INSERT OR IGNORE INTO [{table_name}] ({col_list}) VALUES ({placeholders})"
                loaded = 0
                for row in df.itertuples(index=False, name=None):
                    try:
                        conn.execute(sql, row)
                        loaded += 1
                    except sqlite3.Error as e:
                        result["error_count"] += 1
                        result["errors"].append(str(e))
                result["loaded_count"] = loaded
                log.info(f"[{table_name}] Update load: {loaded}/{len(df)} rows inserted")
        else:
            raise ValueError(f"Unknown mode: {mode}. Use 'init' or 'update'")

    return result


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------
def run_import(
    mode: str = "init",
    target_table: Optional[str] = None,
    config_path: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
    dry_run: bool = False,
) -> list[dict]:
    config_path = config_path or PROJECT_ROOT / "config" / "import_tables.yaml"
    data_dir    = data_dir    or PROJECT_ROOT / "data" / "samples"
    db_path     = db_path     or DB_PATH

    log.info("=" * 60)
    log.info(f"CSV → SQLite Import  mode={mode}  dry_run={dry_run}")
    log.info(f"Config : {config_path}")
    log.info(f"DataDir: {data_dir}")
    log.info(f"DB     : {db_path}")
    log.info("=" * 60)

    cfg = load_config(config_path)
    results = []

    for key, table_cfg in cfg.items():
        if key.startswith("#") or not isinstance(table_cfg, dict):
            continue
        if target_table and table_cfg.get("table_name") != target_table:
            continue
        res = import_table(key, table_cfg, data_dir, db_path, mode=mode, dry_run=dry_run)
        results.append(res)

    # ── サマリ出力 ────────────────────────────────────────────────────────
    log.info("-" * 60)
    log.info("Import Summary:")
    total_loaded = 0
    total_errors = 0
    for r in results:
        status = "OK" if r["error_count"] == 0 else "ERROR"
        log.info(
            f"  [{status}] {r['table']}: "
            f"read={r['read_count']}, loaded={r['loaded_count']}, "
            f"skipped={r['skipped_count']}, errors={r['error_count']}"
        )
        if r["errors"]:
            for e in r["errors"]:
                log.warning(f"         {e}")
        total_loaded += r["loaded_count"]
        total_errors += r["error_count"]

    log.info(f"Total: {total_loaded} rows loaded, {total_errors} errors")
    log.info("=" * 60)
    return results


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CSV → SQLite importer for procurement.db")
    parser.add_argument("--mode",    default="init",  choices=["init", "update"])
    parser.add_argument("--table",   default=None,    help="特定テーブルのみ取込")
    parser.add_argument("--config",  default=None,    help="import_tables.yaml のパス")
    parser.add_argument("--data",    default=None,    help="CSV格納ディレクトリ")
    parser.add_argument("--db",      default=None,    help="SQLite DBファイルパス")
    parser.add_argument("--dry-run", action="store_true", help="書き込まずに確認のみ")
    args = parser.parse_args()

    run_import(
        mode=args.mode,
        target_table=args.table,
        config_path=Path(args.config) if args.config else None,
        data_dir=Path(args.data) if args.data else None,
        db_path=Path(args.db) if args.db else None,
        dry_run=args.dry_run,
    )
