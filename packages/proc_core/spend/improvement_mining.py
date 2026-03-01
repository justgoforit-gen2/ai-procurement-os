"""
improvement_mining.py -- Auto-extract improvement candidates from spend data.

Usage:
    from proc_core.spend.improvement_mining import mine
    candidates = mine(df_po)
"""
from __future__ import annotations

import pandas as pd

from proc_core.spend.price_variance import by_category as price_by_cat
from proc_core.spend.concentration import supplier_concentration, category_concentration
from proc_core.spend.compliance import maverick_summary


def _priority(saving: float) -> str:
    if saving >= 5_000_000:
        return "HIGH"
    if saving >= 1_000_000:
        return "MEDIUM"
    return "LOW"


def mine(df: pd.DataFrame) -> pd.DataFrame:
    """Run all improvement rules and return ranked candidates.

    Returns DataFrame with columns:
        rule_id, cat_or_scope, finding, priority, estimated_saving_net,
        recommended_action, severity_tag
    """
    rows = []

    # IM-01: Price dispersion
    pv = price_by_cat(df, cv_threshold=0.30)
    for _, r in pv[pv["price_cv"] > 0.30].iterrows():
        cat = r.get("cat_small_name", r.get("cat_small_id", ""))
        saving = (r["price_median"] - r["price_min"]) * df[
            df.get("cat_small_id", pd.Series()) == r.get("cat_small_id", None)
        ]["quantity"].sum() if "cat_small_id" in df.columns else 0
        saving = max(saving, 0)
        rows.append({
            "rule_id": "IM-01",
            "cat_or_scope": cat,
            "finding": f"Price CV={r['price_cv']:.0%}, range={r['price_range_pct']:.0f}%",
            "priority": _priority(saving),
            "estimated_saving_net": round(saving),
            "recommended_action": f"[{cat}] 単価標準化・RFx実施",
            "severity_tag": "PRICE",
        })

    # IM-02: Maverick rate
    mav = maverick_summary(df)
    for _, r in mav[mav["maverick_rate"] > 0.30].iterrows():
        saving = r["maverick_net"] * 0.10  # conservative 10% saving estimate
        rows.append({
            "rule_id": "IM-02",
            "cat_or_scope": f"{r['department_name']} / {r['site_name']}",
            "finding": f"Maverick rate={r['maverick_rate']:.0%}, amount={r['maverick_net']:,.0f}",
            "priority": _priority(saving),
            "estimated_saving_net": round(saving),
            "recommended_action": "契約チャネル誘導・購買ポリシー強化",
            "severity_tag": "COMPLIANCE",
        })

    # IM-03: Single-source high-spend
    conc = supplier_concentration(df)
    if "cat_medium_name" in df.columns and "supplier_id" in df.columns:
        cat_sup = df.groupby("cat_medium_name", observed=True).agg(
            supplier_count=("supplier_id", "nunique"),
            total_net=("net_amount", "sum"),
        )
        single_high = cat_sup[(cat_sup["supplier_count"] == 1) & (cat_sup["total_net"] > 5_000_000)]
        for cat, r in single_high.iterrows():
            saving = r["total_net"] * 0.10
            rows.append({
                "rule_id": "IM-03",
                "cat_or_scope": cat,
                "finding": f"Single source, spend={r['total_net']:,.0f}",
                "priority": _priority(saving),
                "estimated_saving_net": round(saving),
                "recommended_action": f"[{cat}] 競争入札導入 / 第2候補サプライヤ選定",
                "severity_tag": "CONCENTRATION",
            })

    # IM-04: Channel price gap (Spot >> Framework)
    if "purchasing_channel" in df.columns and "unit_price" in df.columns:
        ch_price = df.groupby(["cat_small_id", "purchasing_channel"], observed=True)["unit_price"].median().unstack()
        if "Spot" in ch_price.columns and "Framework" in ch_price.columns:
            gap = (ch_price["Spot"] - ch_price["Framework"]) / ch_price["Framework"]
            high_gap = gap[gap > 0.20].dropna()
            for cat_id in high_gap.index:
                spot_vol = df[(df["cat_small_id"] == cat_id) & (df["purchasing_channel"] == "Spot")]["net_amount"].sum()
                saving = spot_vol * float(high_gap[cat_id])
                rows.append({
                    "rule_id": "IM-04",
                    "cat_or_scope": cat_id,
                    "finding": f"Spot vs Framework price gap={high_gap[cat_id]:.0%}",
                    "priority": _priority(saving),
                    "estimated_saving_net": round(saving),
                    "recommended_action": "Frameworkチャネルへ誘導",
                    "severity_tag": "CHANNEL",
                })

    df_out = pd.DataFrame(rows)
    if df_out.empty:
        return df_out
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    df_out["_sort"] = df_out["priority"].map(priority_order)
    return df_out.sort_values(["_sort", "estimated_saving_net"], ascending=[True, False]).drop(columns="_sort").reset_index(drop=True)
