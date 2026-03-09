"""
normalize_columns.py -- カラム正規化ユーティリティ

CSV取込時のデータ型変換・クリーニングを担当。
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

# 真偽値として認識する文字列マッピング
_BOOL_TRUE  = {"true", "yes", "1", "t", "y", "on"}
_BOOL_FALSE = {"false", "no", "0", "f", "n", "off"}


def normalize_bool(val: Any) -> int | None:
    """真偽値の揺れを 1/0/None に統一"""
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in _BOOL_TRUE:
        return 1
    if s in _BOOL_FALSE:
        return 0
    return None


def normalize_date(val: Any) -> str | None:
    """日付を ISO 形式 (YYYY-MM-DD) の文字列に変換"""
    if pd.isna(val):
        return None
    try:
        return pd.to_datetime(val, errors="raise").strftime("%Y-%m-%d")
    except Exception:
        return None


def normalize_numeric(val: Any) -> float | None:
    """金額・数量列の文字列を float に変換（カンマ・通貨記号を除去）"""
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    s = re.sub(r"[,\s￥¥$€£]", "", s)  # カンマ・通貨記号を除去
    try:
        return float(s)
    except ValueError:
        return None


def normalize_text(val: Any) -> str | None:
    """文字列の空白トリム、空文字はNoneに"""
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None


def apply_column_map(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    """
    CSVカラム名 → 正規カラム名へリネーム。
    column_map = {canonical_name: csv_column_name}
    """
    reverse = {v: k for k, v in column_map.items() if v in df.columns}
    return df.rename(columns=reverse)


def normalize_dataframe(
    df: pd.DataFrame,
    date_cols: list[str],
    numeric_cols: list[str],
    bool_cols: list[str],
) -> pd.DataFrame:
    """
    DataFrame全体に対して型正規化を適用する。
    - date_cols   : ISO日付文字列へ変換
    - numeric_cols: float/Noneへ変換
    - bool_cols   : 1/0/Noneへ変換
    - その他列   : 空白トリム
    """
    df = df.copy()

    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].map(normalize_date)

    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].map(normalize_numeric)

    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].map(normalize_bool)

    # 残りの object 列: テキスト正規化
    text_cols = [
        c for c in df.select_dtypes(include="object").columns
        if c not in date_cols + bool_cols
    ]
    for col in text_cols:
        df[col] = df[col].map(normalize_text)

    return df
