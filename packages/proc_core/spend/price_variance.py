"""
price_variance.py -- Unit price variance analysis.

Usage:
    from proc_core.spend.price_variance import by_category, by_dimension
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def by_category(
    df: pd.DataFrame,
    min_rows: int = 3,
    cv_threshold: float = 0.30,
    range_pct_threshold: float = 50.0,
) -> pd.DataFrame:
    """Compute price statistics per (cat_small_id, uom) group.

    Returns DataFrame with columns:
        cat_small_id, cat_small_name, uom, n, price_min, price_max, price_median,
        price_mean, price_cv, price_range_pct, finding
    """
    results = []
    group_cols = ["cat_small_id", "uom"]
    if "cat_small_name" in df.columns:
        group_cols = ["cat_small_id", "cat_small_name", "uom"]

    for keys, grp in df.groupby(group_cols, observed=True):
        prices = grp["unit_price"].dropna()
        if len(prices) < min_rows:
            continue

        median = float(prices.median())
        mean = float(prices.mean())
        cv = float(prices.std() / mean) if mean != 0 else 0
        p_min = float(prices.min())
        p_max = float(prices.max())
        range_pct = (p_max - p_min) / median * 100 if median != 0 else 0

        findings = []
        if cv > cv_threshold:
            findings.append(f"High CV ({cv:.1%})")
        if range_pct > range_pct_threshold:
            findings.append(f"Wide range ({range_pct:.0f}%)")

        row = dict(zip(group_cols, keys if isinstance(keys, tuple) else [keys]))
        row.update({
            "n": len(prices),
            "price_min": p_min,
            "price_max": p_max,
            "price_median": median,
            "price_mean": mean,
            "price_cv": round(cv, 4),
            "price_range_pct": round(range_pct, 1),
            "finding": "; ".join(findings) if findings else "",
        })
        results.append(row)

    if not results:
        cols = list(group_cols) + [
            "n", "price_min", "price_max", "price_median",
            "price_mean", "price_cv", "price_range_pct", "finding",
        ]
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(results)
    return df.sort_values("price_cv", ascending=False)


def by_dimension(
    df: pd.DataFrame,
    dimension: str = "site_name",
    category_level: str = "cat_small_id",
) -> pd.DataFrame:
    """Compare average unit_price across a dimension (site/dept/buyer) per category.

    Returns pivot table: rows=category, columns=dimension values, values=avg_unit_price
    """
    pivot = (
        df.groupby([category_level, dimension], observed=True)["unit_price"]
        .median()
        .unstack(dimension)
    )
    pivot["price_range_pct"] = (
        (pivot.max(axis=1) - pivot.min(axis=1)) / pivot.min(axis=1) * 100
    )
    return pivot.sort_values("price_range_pct", ascending=False)
