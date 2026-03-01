"""
spend_overview.py -- Spend Cube aggregation.

Usage:
    from proc_core.spend.spend_overview import build_cube, period_over_period
    cube = build_cube(df_po, dims=["cat_large_name", "department_name"])
"""
from __future__ import annotations

import pandas as pd


def build_cube(
    df: pd.DataFrame,
    dims: list[str] | None = None,
    period: str = "M",
) -> pd.DataFrame:
    """Aggregate PO spend across requested dimensions + time period.

    Args:
        df: Clean PO transactions with canonical columns.
        dims: Dimension columns to group by (default: cat_large_name, department_name).
        period: Pandas period alias for time bucketing ('M'=month, 'Q'=quarter, 'Y'=year).

    Returns:
        DataFrame with columns: period, <dims>, total_net, po_count, line_count, supplier_count, avg_po_size
    """
    if dims is None:
        dims = ["cat_large_name", "department_name"]

    df = df.copy()
    df["period"] = df["posting_date"].dt.to_period(period).astype(str)

    group_cols = ["period"] + [d for d in dims if d in df.columns]

    agg = (
        df.groupby(group_cols, observed=True)
        .agg(
            total_net=("net_amount", "sum"),
            po_count=("po_number", "nunique"),
            line_count=("po_number", "count"),
            supplier_count=("supplier_id", "nunique"),
        )
        .reset_index()
    )
    agg["avg_po_size"] = agg["total_net"] / agg["po_count"]
    return agg


def period_over_period(
    df: pd.DataFrame,
    current_period: str,
    prior_period: str,
    group_col: str = "cat_large_name",
) -> pd.DataFrame:
    """Compare spend between two periods and decompose delta into volume vs price effect.

    Returns DataFrame with: group, current_net, prior_net, delta, delta_pct,
                            volume_effect, price_effect (if unit_price available)
    """
    def _agg(df_p: pd.DataFrame) -> pd.DataFrame:
        return (
            df_p.groupby(group_col, observed=True)
            .agg(
                net=("net_amount", "sum"),
                qty=("quantity", "sum"),
                avg_price=("unit_price", "mean"),
            )
            .reset_index()
        )

    df["period"] = df["posting_date"].dt.to_period("M").astype(str)
    cur = _agg(df[df["period"] == current_period])
    pri = _agg(df[df["period"] == prior_period])

    merged = cur.merge(pri, on=group_col, how="outer", suffixes=("_cur", "_pri")).fillna(0)
    merged["delta"] = merged["net_cur"] - merged["net_pri"]
    merged["delta_pct"] = (merged["delta"] / merged["net_pri"].replace(0, float("nan"))) * 100
    merged["volume_effect"] = (merged["qty_cur"] - merged["qty_pri"]) * merged["avg_price_pri"]
    merged["price_effect"] = (merged["avg_price_cur"] - merged["avg_price_pri"]) * merged["qty_cur"]
    return merged.rename(columns={"net_cur": "current_net", "net_pri": "prior_net"})
