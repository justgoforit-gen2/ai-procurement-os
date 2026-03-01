"""KPI management — 原価低減マイルストーン管理.

Usage:
    from proc_core.spend.kpi import load_kpi_config, compute_kpi, compute_milestones
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yaml


def _fmt_yen(val: float) -> str:
    if val >= 1_000_000_000:
        return f"¥{val/1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"¥{val/1_000_000:.1f}M"
    return f"¥{val:,.0f}"


def load_kpi_config(config_root: Path) -> dict:
    """Load config/kpi/targets.yaml. Returns defaults if file not found."""
    path = config_root / "config" / "kpi" / "targets.yaml"
    if not path.exists():
        return {"fiscal_year": None, "baseline_year": None, "sites": {}}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_rate(site: str, sites_cfg: dict, default: float = 0.05) -> float:
    return float(sites_cfg.get(site, {}).get("target_rate", default))


def compute_kpi(df_po: pd.DataFrame, config: dict) -> dict:
    """Compute site-level KPI summary from PO transaction data.

    Returns:
        dict with keys:
            site_cards, merged_df, fiscal_year, baseline_year,
            total_savings_target, total_savings_actual
    """
    df = df_po.copy()
    df["year"] = df["posting_date"].dt.year
    df["month"] = df["posting_date"].dt.month

    # Determine fiscal / baseline years
    fiscal_year = config.get("fiscal_year")
    baseline_year = config.get("baseline_year")
    sites_cfg = config.get("sites", {})

    if fiscal_year is None or baseline_year is None:
        years = sorted(df["year"].dropna().unique())
        if len(years) >= 2:
            fiscal_year = int(years[-1])
            baseline_year = int(years[-2])
        else:
            fiscal_year = int(years[-1]) if years else 2025
            baseline_year = fiscal_year - 1

    # Monthly spend by site
    baseline = (
        df[df["year"] == baseline_year]
        .groupby(["site_name", "month"], as_index=False)["net_amount"]
        .sum()
        .rename(columns={"net_amount": "baseline"})
    )
    actual = (
        df[df["year"] == fiscal_year]
        .groupby(["site_name", "month"], as_index=False)["net_amount"]
        .sum()
        .rename(columns={"net_amount": "actual"})
    )

    # Build a complete grid: all sites × all 12 months
    sites_all = sorted(
        set(baseline["site_name"].tolist() + actual["site_name"].tolist())
    )
    months_all = list(range(1, 13))
    idx = pd.MultiIndex.from_product([sites_all, months_all], names=["site_name", "month"])
    base_frame = pd.DataFrame(index=idx).reset_index()

    merged = (
        base_frame
        .merge(baseline, on=["site_name", "month"], how="left")
        .merge(actual, on=["site_name", "month"], how="left")
        .fillna(0.0)
    )

    merged["target_rate"] = merged["site_name"].apply(lambda s: _get_rate(s, sites_cfg))
    merged["target"] = merged["baseline"] * (1.0 - merged["target_rate"])
    merged["savings_target"] = merged["baseline"] * merged["target_rate"]
    merged["savings_actual"] = merged["baseline"] - merged["actual"]

    # Determine last observed month in fiscal year (for YTD comparison)
    last_ytd_month = int(actual["month"].max()) if not actual.empty else 0

    # Site-level: annual target (full year) vs YTD actuals (months <= last_ytd_month)
    site_annual = merged.groupby("site_name", as_index=False).agg(
        baseline_annual=("baseline", "sum"),
        savings_target_annual=("savings_target", "sum"),
    )
    site_ytd = (
        merged[merged["month"] <= last_ytd_month]
        .groupby("site_name", as_index=False)
        .agg(
            baseline_ytd=("baseline", "sum"),
            actual_ytd=("actual", "sum"),
            savings_target_ytd=("savings_target", "sum"),
        )
    )
    site_ytd["savings_actual_ytd"] = site_ytd["baseline_ytd"] - site_ytd["actual_ytd"]

    site_agg = site_annual.merge(site_ytd, on="site_name", how="left").fillna(0.0)
    site_agg["target_rate"] = site_agg["site_name"].apply(lambda s: _get_rate(s, sites_cfg))
    site_agg["achievement_pct"] = (
        site_agg["savings_actual_ytd"] / site_agg["savings_target_ytd"].clip(lower=1) * 100
    )

    # Build site card dicts with RAG status
    site_cards = []
    for _, row in site_agg.iterrows():
        pct = float(row["achievement_pct"])
        if pct >= 80:
            border = "border-green-500"
            bar_color = "bg-green-500"
            text_color = "text-green-600"
            badge = "✓ 順調"
        elif pct >= 50:
            border = "border-yellow-400"
            bar_color = "bg-yellow-400"
            text_color = "text-yellow-600"
            badge = "△ 要注意"
        else:
            border = "border-red-500"
            bar_color = "bg-red-500"
            text_color = "text-red-600"
            badge = "✗ 要改善"

        site_cards.append({
            "site": row["site_name"],
            "target_rate_pct": f"{row['target_rate']*100:.0f}%",
            "savings_target_annual": _fmt_yen(float(row["savings_target_annual"])),
            "savings_actual_ytd": _fmt_yen(float(row["savings_actual_ytd"])),
            "baseline_ytd": _fmt_yen(float(row["baseline_ytd"])),
            "actual_ytd": _fmt_yen(float(row["actual_ytd"])),
            "achievement_pct": f"{pct:.1f}",
            "achievement_pct_clamp": min(max(pct, 0), 100),
            "border_color": border,
            "bar_color": bar_color,
            "text_color": text_color,
            "status_badge": badge,
        })

    return {
        "site_cards": site_cards,
        "merged_df": merged,
        "fiscal_year": fiscal_year,
        "baseline_year": baseline_year,
        "last_ytd_month": last_ytd_month,
        "total_savings_target": _fmt_yen(float(site_agg["savings_target_annual"].sum())),
        "total_savings_actual": _fmt_yen(float(site_agg["savings_actual_ytd"].sum())),
    }


def compute_milestones(
    merged_df: pd.DataFrame,
    site_filter: str = "",
) -> tuple[str, list[dict]]:
    """Build monthly milestone Plotly chart + table rows.

    Args:
        merged_df: Output of compute_kpi()["merged_df"]
        site_filter: Site name to filter on. Empty string = all sites aggregated.

    Returns:
        (chart_html, table_rows)
    """
    df = merged_df.copy()
    if site_filter:
        df = df[df["site_name"] == site_filter]

    monthly = (
        df.groupby("month", as_index=False).agg(
            baseline=("baseline", "sum"),
            target=("target", "sum"),
            actual=("actual", "sum"),
            savings_target=("savings_target", "sum"),
            savings_actual=("savings_actual", "sum"),
        )
        .sort_values("month")
    )

    month_labels = [f"{int(m):02d}月" for m in monthly["month"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=month_labels, y=monthly["actual"],
        name="実績", marker_color="#1f77b4", opacity=0.85,
    ))
    fig.add_trace(go.Scatter(
        x=month_labels, y=monthly["baseline"],
        name="前年実績", mode="lines+markers",
        line={"color": "#9ca3af", "width": 2, "dash": "dot"},
        marker={"size": 6},
    ))
    fig.add_trace(go.Scatter(
        x=month_labels, y=monthly["target"],
        name="削減目標", mode="lines+markers",
        line={"color": "#16a34a", "width": 2, "dash": "dash"},
        marker={"symbol": "diamond", "size": 8, "color": "#16a34a"},
    ))

    title = f"月次実績 vs 削減目標 — {site_filter or '全拠点合計'}"
    fig.update_layout(
        title={"text": title, "font": {"size": 14}},
        yaxis_title="支出 (税抜)",
        legend={"orientation": "h", "y": -0.3},
        height=340,
        margin=dict(l=60, r=20, t=50, b=90),
    )

    chart_html = fig.to_html(full_html=False, include_plotlyjs=False)

    # Build table rows (only months with data)
    table_rows = []
    for _, row in monthly.iterrows():
        # Skip future months where both baseline and actual are 0
        if row["baseline"] == 0 and row["actual"] == 0:
            continue

        st = float(row["savings_target"])
        sa = float(row["savings_actual"])
        pct = sa / st * 100 if st > 0 else 0.0
        variance = float(row["target"]) - float(row["actual"])

        if pct >= 80:
            row_class = ""
            status = "✓ 順調"
        elif pct >= 50:
            row_class = "row-medium"
            status = "△ 要注意"
        else:
            row_class = "row-high"
            status = "✗ 要改善"

        table_rows.append({
            "month": f"{int(row['month']):02d}月",
            "baseline": _fmt_yen(float(row["baseline"])),
            "target": _fmt_yen(float(row["target"])),
            "actual": _fmt_yen(float(row["actual"])),
            "variance": _fmt_yen(abs(variance)),
            "variance_positive": variance >= 0,
            "achievement_pct": f"{pct:.1f}%",
            "status": status,
            "row_class": row_class,
        })

    return chart_html, table_rows
