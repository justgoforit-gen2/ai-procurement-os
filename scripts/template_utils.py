"""
template_utils.py -- 見積テンプレート生成ユーティリティ

commodity_templates.yaml を読み込み、コモディティ別の列定義を返す。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).parents[1] / "config"
TEMPLATES_YAML  = CONFIG_DIR / "commodity_templates.yaml"
BENCHMARK_YAML  = CONFIG_DIR / "benchmark_definitions.yaml"
COLUMN_DICT_YAML = CONFIG_DIR / "column_dictionary.yaml"


# ---------------------------------------------------------------------------
# 設定ファイル読込
# ---------------------------------------------------------------------------
def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_templates() -> dict:
    return _load_yaml(TEMPLATES_YAML)


def load_benchmarks() -> dict:
    return _load_yaml(BENCHMARK_YAML)


def list_commodities() -> list[str]:
    """利用可能なコモディティ大分類名の一覧を返す"""
    cfg = load_templates()
    return list(cfg.get("commodities", {}).keys())


# ---------------------------------------------------------------------------
# 列定義の取得
# ---------------------------------------------------------------------------
def get_columns(commodity_group: str) -> list[dict[str, Any]]:
    """
    指定コモディティの全列定義（コア + 拡張）を列順で返す。

    Returns:
        list of {name, label_ja, dtype, required, is_core, description, ...}
    """
    cfg = load_templates()
    core_cols = cfg.get("core_columns", [])
    commodities = cfg.get("commodities", {})

    if commodity_group not in commodities:
        raise ValueError(
            f"Commodity '{commodity_group}' not found. "
            f"Available: {list(commodities.keys())}"
        )

    ext_cols = commodities[commodity_group].get("extension_columns", [])

    # コア列に is_core フラグを付与
    result = []
    for i, col in enumerate(core_cols):
        c = dict(col)
        c["is_core"] = True
        c["sort_order"] = i
        result.append(c)

    # 拡張列
    offset = len(core_cols)
    for i, col in enumerate(ext_cols):
        c = dict(col)
        c["is_core"] = False
        c["sort_order"] = offset + i
        result.append(c)

    return result


def get_required_columns(commodity_group: str) -> list[str]:
    """必須列名のリストを返す"""
    return [c["name"] for c in get_columns(commodity_group) if c.get("required")]


def get_benchmark_metrics(commodity_group: str) -> list[dict]:
    """コモディティのベンチマーク指標定義を返す"""
    cfg = load_templates()
    bench_cfg = load_benchmarks()
    commodities = cfg.get("commodities", {})
    if commodity_group not in commodities:
        return []
    bench_key = commodities[commodity_group].get("benchmark_key", "")
    return bench_cfg.get("benchmarks", {}).get(bench_key, [])


# ---------------------------------------------------------------------------
# Excel スタイル定義
# ---------------------------------------------------------------------------
STYLE = {
    "header_fill":    "1F4E79",   # 濃い青（ヘッダ行）
    "core_fill":      "BDD7EE",   # 薄い青（コア列ラベル）
    "ext_fill":       "E2EFDA",   # 薄い緑（拡張列ラベル）
    "req_fill":       "FFD966",   # 黄色（必須列）
    "header_font":    "FFFFFF",   # 白文字
    "default_font":   "000000",
    "row_height":     20,
    "header_height":  30,
    "col_width_default": 18,
    "col_width_notes":   30,
}
