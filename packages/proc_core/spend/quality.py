"""
quality.py -- Data quality checks for PO transactions DataFrame.

Usage:
    from proc_core.spend.quality import check
    report = check(df_po)
    print(report["summary"])
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def check(df: pd.DataFrame, amount_tolerance: float = 0.01) -> dict:
    """Run all quality checks and return a report dict.

    Args:
        df: PO transactions DataFrame with canonical column names.
        amount_tolerance: Allowed relative difference between qty*unit_price and net_amount.

    Returns:
        {
          "summary": {...},
          "issues": [{"index": int, "type": str, "detail": str}],
          "df_clean": DataFrame  -- rows passing error checks
        }
    """
    issues = []
    error_idx = set()
    warning_idx = set()

    # 1. Required fields
    for col in ["po_number", "posting_date", "net_amount"]:
        if col not in df.columns:
            continue
        null_mask = df[col].isna()
        for i in df.index[null_mask]:
            issues.append({"index": i, "type": "NULL_REQUIRED", "detail": f"{col} is null"})
            error_idx.add(i)

    # 2. Duplicate PO lines
    if "po_number" in df.columns and "po_line" in df.columns:
        dup_mask = df.duplicated(subset=["po_number", "po_line"], keep="first")
        for i in df.index[dup_mask]:
            issues.append({"index": i, "type": "DUPLICATE_LINE", "detail": "Duplicate po_number+po_line"})
            error_idx.add(i)

    # 3. Amount reconciliation: qty * unit_price ~ net_amount
    if all(c in df.columns for c in ["quantity", "unit_price", "net_amount"]):
        calc = df["quantity"] * df["unit_price"]
        mismatch = ((calc - df["net_amount"]).abs() / df["net_amount"].replace(0, np.nan)) > amount_tolerance
        mismatch = mismatch.fillna(False)
        for i in df.index[mismatch & ~df["net_amount"].isna()]:
            issues.append({"index": i, "type": "AMOUNT_MISMATCH",
                           "detail": f"qty*unit_price != net_amount (diff > {amount_tolerance*100:.0f}%)"})
            warning_idx.add(i)

    # 4. Unit price outliers (per cat_small_id + uom)
    if all(c in df.columns for c in ["unit_price", "cat_small_id", "uom"]):
        for (cat, uom), grp in df.groupby(["cat_small_id", "uom"], observed=True):
            prices = grp["unit_price"].dropna()
            if len(prices) < 4:
                continue
            q1, q3 = prices.quantile(0.25), prices.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
            outliers = grp[((grp["unit_price"] < lo) | (grp["unit_price"] > hi)) & grp["unit_price"].notna()]
            for i in outliers.index:
                issues.append({"index": i, "type": "PRICE_OUTLIER",
                               "detail": f"unit_price outside 3*IQR for ({cat}, {uom})"})
                warning_idx.add(i)

    # 5. Missing category
    if "cat_large_id" in df.columns:
        null_cat = df["cat_large_id"].isna()
        for i in df.index[null_cat]:
            issues.append({"index": i, "type": "MISSING_CATEGORY", "detail": "cat_large_id is null"})
            warning_idx.add(i)

    df_clean = df.loc[~df.index.isin(error_idx)].copy()

    return {
        "summary": {
            "total_rows": len(df),
            "error_rows": len(error_idx),
            "warning_rows": len(warning_idx - error_idx),
            "clean_rows": len(df_clean),
            "issue_count": len(issues),
        },
        "issues": issues,
        "df_clean": df_clean,
    }
