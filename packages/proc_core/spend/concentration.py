"""
concentration.py -- Supplier and category concentration (80/20) analysis.

Usage:
    from proc_core.spend.concentration import category_concentration, supplier_concentration
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def category_concentration(
    df: pd.DataFrame,
    level: str = "cat_medium_name",
    threshold: float = 0.80,
) -> pd.DataFrame:
    """Rank categories by spend and compute cumulative share.

    Returns DataFrame sorted by spend DESC with columns:
        level, total_net, share_pct, cumulative_pct, in_top80
    """
    agg = (
        df.groupby(level, observed=True)["net_amount"]
        .sum()
        .reset_index()
        .rename(columns={"net_amount": "total_net"})
        .sort_values("total_net", ascending=False)
    )
    total = agg["total_net"].sum()
    agg["share_pct"] = agg["total_net"] / total * 100
    agg["cumulative_pct"] = agg["share_pct"].cumsum()
    agg["in_top80"] = agg["cumulative_pct"] <= threshold * 100
    return agg.reset_index(drop=True)


def supplier_concentration(
    df: pd.DataFrame,
    level: str = "supplier_group_name",
) -> dict:
    """Compute supplier concentration metrics.

    Returns dict with:
        - ranked_df: suppliers sorted by spend DESC with share/cumulative columns
        - top1_share, top3_share, top5_share, top10_share (%)
        - hhi: Herfindahl-Hirschman Index (0 to 1)
        - single_source_categories: list of cat_medium_name with only 1 supplier
    """
    agg = (
        df.groupby(level, observed=True)["net_amount"]
        .sum()
        .reset_index()
        .rename(columns={"net_amount": "total_net"})
        .sort_values("total_net", ascending=False)
    )
    total = agg["total_net"].sum()
    agg["share_pct"] = agg["total_net"] / total * 100
    agg["cumulative_pct"] = agg["share_pct"].cumsum()

    shares = agg["share_pct"].values / 100
    hhi = float(np.sum(shares ** 2))

    def top_n_share(n):
        return float(agg.head(n)["share_pct"].sum())

    # Single-source categories
    cat_sup = df.groupby("cat_medium_name", observed=True)["supplier_id"].nunique()
    single_source = list(cat_sup[cat_sup == 1].index)

    return {
        "ranked_df": agg,
        "top1_share": top_n_share(1),
        "top3_share": top_n_share(3),
        "top5_share": top_n_share(5),
        "top10_share": top_n_share(10),
        "hhi": hhi,
        "single_source_categories": single_source,
    }
