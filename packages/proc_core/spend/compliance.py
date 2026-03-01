"""
compliance.py -- Maverick buying and contract compliance detection.

Usage:
    from proc_core.spend.compliance import maverick_summary, split_order_detection, all_findings
"""
from __future__ import annotations

import pandas as pd


def maverick_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Compute maverick (non-contract) spend rate by department and site.

    Returns DataFrame with: department_name, site_name,
        total_net, maverick_net, maverick_rate, finding
    """
    df = df.copy()
    df["is_maverick"] = df["contract_flag"].astype(int) == 0

    agg = (
        df.groupby(["department_name", "site_name"], observed=True)
        .agg(
            total_net=("net_amount", "sum"),
            maverick_net=("net_amount", lambda x: x[df.loc[x.index, "is_maverick"]].sum()),
            maverick_count=("po_number", lambda x: x[df.loc[x.index, "is_maverick"]].nunique()),
            total_count=("po_number", "nunique"),
        )
        .reset_index()
    )
    agg["maverick_rate"] = agg["maverick_net"] / agg["total_net"]
    agg["finding"] = agg["maverick_rate"].apply(
        lambda r: "HIGH maverick" if r > 0.30 else ("MED maverick" if r > 0.15 else "")
    )
    return agg.sort_values("maverick_rate", ascending=False)


def channel_compliance(df: pd.DataFrame) -> pd.DataFrame:
    """Detect rows where contract exists (flag=1) but Spot channel was used."""
    mask = (df["contract_flag"].astype(int) == 1) & (df["purchasing_channel"] == "Spot")
    flagged = df[mask][["po_number", "po_line", "department_name", "supplier_name",
                         "cat_medium_name", "net_amount", "purchasing_channel", "contract_flag"]].copy()
    flagged["finding_type"] = "CONTRACT_EXISTS_BUT_SPOT"
    flagged["severity"] = "MEDIUM"
    return flagged


def split_order_detection(
    df: pd.DataFrame,
    min_occurrences: int = 3,
    amount_threshold: float = 1_000_000,
) -> pd.DataFrame:
    """Detect potential split orders (same supplier+dept+category in same month, many small POs).

    Args:
        min_occurrences: Minimum number of POs in the group to flag.
        amount_threshold: Each PO net_amount must be below this to flag.
    """
    df = df.copy()
    df["month"] = df["posting_date"].dt.to_period("M").astype(str)

    group = (
        df.groupby(["supplier_id", "department_id", "cat_small_id", "month"], observed=True)
        .agg(
            po_count=("po_number", "nunique"),
            max_amount=("net_amount", "max"),
            total_amount=("net_amount", "sum"),
        )
        .reset_index()
    )
    flagged = group[
        (group["po_count"] >= min_occurrences) &
        (group["max_amount"] < amount_threshold)
    ].copy()
    flagged["finding_type"] = "SPLIT_ORDER"
    flagged["severity"] = "MEDIUM"
    return flagged.sort_values("total_amount", ascending=False)


def all_findings(df: pd.DataFrame) -> pd.DataFrame:
    """Run all compliance checks and return a unified findings DataFrame."""
    rows = []

    # Maverick high-risk
    mav = maverick_summary(df)
    for _, r in mav[mav["finding"].str.startswith("HIGH", na=False)].iterrows():
        rows.append({
            "finding_type": "HIGH_MAVERICK",
            "scope": f"{r['department_name']} / {r['site_name']}",
            "net_amount": r["maverick_net"],
            "severity": "HIGH",
            "detail": f"Maverick rate {r['maverick_rate']:.0%}",
        })

    # Channel compliance
    ch = channel_compliance(df)
    for _, r in ch.iterrows():
        rows.append({
            "finding_type": r["finding_type"],
            "scope": f"PO {r['po_number']} line {r['po_line']}",
            "net_amount": r["net_amount"],
            "severity": r["severity"],
            "detail": f"Supplier: {r['supplier_name']}, Cat: {r['cat_medium_name']}",
        })

    # Split orders
    sp = split_order_detection(df)
    for _, r in sp.iterrows():
        rows.append({
            "finding_type": r["finding_type"],
            "scope": f"Supplier {r['supplier_id']} / Dept {r['department_id']} / {r['month']}",
            "net_amount": r["total_amount"],
            "severity": r["severity"],
            "detail": f"{r['po_count']} POs, max single PO < {r['max_amount']:,.0f}",
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["finding_type", "scope", "net_amount", "severity", "detail"]
    )
