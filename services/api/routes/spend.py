"""Spend Analytics — FastAPI routes with Jinja2 + htmx UI."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Path setup — ensure proc_core is importable
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_ROOT = _HERE.parents[2]
_PACKAGES = _ROOT / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from proc_core.spend.loader import load_all
from proc_core.spend.quality import check as quality_check
from proc_core.spend.spend_overview import build_cube
from proc_core.spend.concentration import supplier_concentration
from proc_core.spend.price_variance import by_category as price_by_category
from proc_core.spend.compliance import maverick_summary, all_findings
from proc_core.spend.improvement_mining import mine as improvement_mine
from proc_core.spend.kpi import load_kpi_config, compute_kpi, compute_milestones

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR = _ROOT / "data" / "samples"
TEMPLATES = Jinja2Templates(directory=_HERE.parent / "templates")

router = APIRouter()

# ---------------------------------------------------------------------------
# Map constants (Unicode-escaped to avoid cp932 issues on Windows)
# ---------------------------------------------------------------------------
_PREF_COORDS: dict[str, tuple[float, float]] = {
    "\u5317\u6d77\u9053": (43.064, 141.347), "\u9752\u68ee\u770c": (40.824, 140.740),
    "\u5ca9\u624b\u770c": (39.704, 141.153), "\u5bae\u57ce\u770c": (38.269, 140.872),
    "\u79cb\u7530\u770c": (39.719, 140.102), "\u5c71\u5f62\u770c": (38.240, 140.363),
    "\u798f\u5cf6\u770c": (37.750, 140.468), "\u8328\u57ce\u770c": (36.342, 140.447),
    "\u6803\u6728\u770c": (36.566, 139.884), "\u7fa4\u99ac\u770c": (36.391, 139.061),
    "\u57fc\u7389\u770c": (35.857, 139.649), "\u5343\u8449\u770c": (35.605, 140.123),
    "\u6771\u4eac\u90fd": (35.676, 139.650), "\u795e\u5948\u5ddd\u770c": (35.448, 139.643),
    "\u65b0\u6f5f\u770c": (37.903, 139.023), "\u5bcc\u5c71\u770c": (36.695, 137.211),
    "\u77f3\u5ddd\u770c": (36.595, 136.626), "\u798f\u4e95\u770c": (36.065, 136.222),
    "\u5c71\u68a8\u770c": (35.664, 138.568), "\u9577\u91ce\u770c": (36.651, 138.181),
    "\u5c90\u961c\u770c": (35.391, 136.722), "\u9759\u5ca1\u770c": (34.977, 138.383),
    "\u611b\u77e5\u770c": (35.180, 136.907), "\u4e09\u91cd\u770c": (34.730, 136.509),
    "\u6ecb\u8cc0\u770c": (35.004, 135.869), "\u4eac\u90fd\u5e9c": (35.012, 135.768),
    "\u5927\u962a\u5e9c": (34.694, 135.502), "\u5175\u5eab\u770c": (34.691, 135.183),
    "\u5948\u826f\u770c": (34.685, 135.833), "\u548c\u6b4c\u5c71\u770c": (34.226, 135.168),
    "\u9ce5\u53d6\u770c": (35.504, 134.238), "\u5cf6\u6839\u770c": (35.472, 133.051),
    "\u5ca1\u5c71\u770c": (34.662, 133.935), "\u5e83\u5cf6\u770c": (34.397, 132.460),
    "\u5c71\u53e3\u770c": (34.186, 131.471), "\u5fb3\u5cf6\u770c": (34.066, 134.559),
    "\u9999\u5ddd\u770c": (34.340, 134.043), "\u611b\u5a9b\u770c": (33.842, 132.766),
    "\u9ad8\u77e5\u770c": (33.560, 133.531), "\u798f\u5ca1\u770c": (33.590, 130.402),
    "\u4f50\u8cc0\u770c": (33.264, 130.301), "\u9577\u5d0e\u770c": (32.745, 129.874),
    "\u718a\u672c\u770c": (32.790, 130.742), "\u5927\u5206\u770c": (33.238, 131.613),
    "\u5bae\u5d0e\u770c": (31.911, 131.424), "\u9e7f\u5150\u5cf6\u770c": (31.560, 130.558),
    "\u6c96\u7e04\u770c": (26.212, 127.681),
}

_SITE_COORDS: dict[str, tuple[float, float]] = {
    "\u672c\u793e\uff08\u6771\u4eac\uff09": (35.681, 139.767),
    "\u6a2a\u6d5c\u30aa\u30d5\u30a3\u30b9": (35.443, 139.638),
    "\u95a2\u6771\u7269\u6d41\u30bb\u30f3\u30bf\u30fc": (35.820, 139.950),
    "\u95a2\u897f\u7269\u6d41\u30bb\u30f3\u30bf\u30fc": (34.735, 135.520),
    "\u540d\u53e4\u5c4b\u62e0\u70b9": (35.170, 136.906),
}

_CAT_COLORS = {
    cat: color
    for cat, color in zip(
        ["IT", "\u30d3\u30b8\u30cd\u30b9\u30b5\u30fc\u30d3\u30b9",
         "\u30de\u30fc\u30b1\u30c6\u30a3\u30f3\u30b0",
         "\u30ea\u30c6\u30fc\u30eb\u30d7\u30ed\u30e2"],
        px.colors.qualitative.Vivid,
    )
}
_RETAIL_CAT = "\u30ea\u30c6\u30fc\u30eb\u30d7\u30ed\u30e2"

# ---------------------------------------------------------------------------
# Data cache (module-level singleton; reloaded only on server restart)
# ---------------------------------------------------------------------------
_DATA_CACHE: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None = None


def _get_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    global _DATA_CACHE
    if _DATA_CACHE is None:
        _DATA_CACHE = load_all(str(DATA_DIR), mapping="default", config_root=_ROOT)
    return _DATA_CACHE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _apply_filters(
    df: pd.DataFrame,
    start: str,
    end: str,
    cats: list[str],
    medium_cats: list[str],
    small_cats: list[str],
    depts: list[str],
    sites: list[str],
) -> pd.DataFrame:
    df = df[
        (df["posting_date"] >= pd.Timestamp(start))
        & (df["posting_date"] <= pd.Timestamp(end))
    ]
    if cats:
        df = df[df["cat_large_name"].isin(cats)]
    if medium_cats:
        df = df[df["cat_medium_name"].isin(medium_cats)]
    if small_cats:
        df = df[df["cat_small_name"].isin(small_cats)]
    if depts:
        df = df[df["department_name"].isin(depts)]
    if sites:
        df = df[df["site_name"].isin(sites)]
    return df


def _chart(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _fmt_yen(val: float) -> str:
    if val >= 1_000_000_000:
        return f"¥{val/1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"¥{val/1_000_000:.1f}M"
    return f"¥{val:,.0f}"


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def _build_overview_charts(df_clean: pd.DataFrame) -> dict:
    # Monthly trend
    monthly = (
        df_clean.assign(month=lambda d: d["posting_date"].dt.to_period("M").astype(str))
        .groupby("month", as_index=False)["net_amount"].sum()
        .sort_values("month")
    )
    fig_monthly = px.bar(
        monthly, x="month", y="net_amount",
        labels={"month": "\u6708", "net_amount": "\u652f\u51fa (\u7a0e\u629c)"},
        color_discrete_sequence=["#1f77b4"],
    )
    fig_monthly.update_layout(xaxis_tickangle=-45, height=300, margin=dict(l=40, r=10, t=20, b=60))

    # Category bar
    cat_agg = (
        df_clean.groupby("cat_large_name", as_index=False)["net_amount"]
        .sum().sort_values("net_amount", ascending=False).head(10)
    ) if "cat_large_name" in df_clean.columns else pd.DataFrame()
    fig_cat = px.bar(
        cat_agg, x="net_amount", y="cat_large_name", orientation="h",
        labels={"net_amount": "\u652f\u51fa", "cat_large_name": "\u5927\u5206\u985e"},
        color_discrete_sequence=["#2ca02c"],
    ) if not cat_agg.empty else go.Figure()
    fig_cat.update_layout(
        yaxis={"categoryorder": "total ascending"}, height=320,
        margin=dict(l=160, r=10, t=20, b=40),
    )

    # Department bar
    dept_agg = (
        df_clean.groupby("department_name", as_index=False)["net_amount"]
        .sum().sort_values("net_amount", ascending=False).head(10)
    ) if "department_name" in df_clean.columns else pd.DataFrame()
    fig_dept = px.bar(
        dept_agg, x="net_amount", y="department_name", orientation="h",
        labels={"net_amount": "\u652f\u51fa", "department_name": "\u90e8\u9580"},
        color_discrete_sequence=["#ff7f0e"],
    ) if not dept_agg.empty else go.Figure()
    fig_dept.update_layout(
        yaxis={"categoryorder": "total ascending"}, height=320,
        margin=dict(l=160, r=10, t=20, b=40),
    )

    # Treemap
    df_tree = (
        df_clean.groupby(["cat_large_name", "supplier_parent_name"], observed=True)["net_amount"]
        .sum().reset_index()
    ) if "cat_large_name" in df_clean.columns and "supplier_parent_name" in df_clean.columns else pd.DataFrame()
    fig_tree = px.treemap(
        df_tree,
        path=[px.Constant("\u5168\u4f53"), "cat_large_name", "supplier_parent_name"],
        values="net_amount", color="cat_large_name",
        color_discrete_sequence=px.colors.qualitative.Pastel,
    ) if not df_tree.empty else go.Figure()
    fig_tree.update_traces(
        texttemplate="<b>%{label}</b><br>\u00a5%{value:,.0f}",
        hovertemplate="<b>%{label}</b><br>\u652f\u51fa: \u00a5%{value:,.0f}<br>\u30b7\u30a7\u30a2: %{percentRoot:.1%}<extra></extra>",
        textfont_size=12,
    )
    fig_tree.update_layout(height=480, margin=dict(l=0, r=0, t=10, b=0))

    return {
        "monthly": _chart(fig_monthly),
        "cat": _chart(fig_cat),
        "dept": _chart(fig_dept),
        "tree": _chart(fig_tree),
    }


def _build_concentration_charts(df_clean: pd.DataFrame) -> dict:
    conc = supplier_concentration(df_clean)
    ranked = conc["ranked_df"].head(10).reset_index(drop=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=ranked["supplier_group_name"], y=ranked["share_pct"],
        name="\u30b7\u30a7\u30a2 (%)", marker_color="#1f77b4",
    ))
    fig.add_trace(go.Scatter(
        x=ranked["supplier_group_name"], y=ranked["cumulative_pct"],
        name="\u7d2f\u7a4d\u30b7\u30a7\u30a2 (%)", yaxis="y2",
        mode="lines+markers", line={"color": "#d62728", "width": 2},
    ))
    fig.update_layout(
        yaxis={"title": "\u30b7\u30a7\u30a2 (%)"},
        yaxis2={"title": "\u7d2f\u7a4d\u30b7\u30a7\u30a2 (%)", "overlaying": "y",
                "side": "right", "range": [0, 100]},
        xaxis_tickangle=-35, height=360,
        legend={"orientation": "h"},
        margin=dict(l=40, r=60, t=20, b=80),
    )

    return {
        "chart": _chart(fig),
        "top1": f"{conc['top1_share']:.1f}%",
        "top3": f"{conc['top3_share']:.1f}%",
        "top5": f"{conc['top5_share']:.1f}%",
        "top10": f"{conc['top10_share']:.1f}%",
        "hhi": f"{conc['hhi']:.4f}",
        "single_source": conc["single_source_categories"],
    }


def _build_price_variance_charts(df_clean: pd.DataFrame) -> dict:
    pv = price_by_category(df_clean, cv_threshold=0.30)
    top_cv = pv.head(15).copy()

    fig = go.Figure()
    if not top_cv.empty:
        label_col = "cat_small_name" if "cat_small_name" in top_cv.columns else "cat_small_id"
        fig = px.bar(
            top_cv, x="price_cv", y=label_col, orientation="h",
            labels={"price_cv": "CV", label_col: "\u5c0f\u5206\u985e"},
            color="price_cv", color_continuous_scale="Reds",
        )
        fig.update_layout(
            yaxis={"categoryorder": "total ascending"}, height=380,
            margin=dict(l=160, r=10, t=20, b=40),
        )

    high_cv = pv[pv["price_cv"] > 0.30].reset_index(drop=True)
    return {
        "chart": _chart(fig),
        "table": high_cv.to_dict("records"),
        "table_cols": list(high_cv.columns) if not high_cv.empty else [],
    }


def _build_compliance_charts(df_clean: pd.DataFrame) -> dict:
    mav = maverick_summary(df_clean)
    overall = (
        df_clean[df_clean["contract_flag"].astype(int) == 0]["net_amount"].sum()
        / df_clean["net_amount"].sum()
    ) if "contract_flag" in df_clean.columns else 0.0

    dept_mav = (
        mav.groupby("department_name", as_index=False)
        .agg(maverick_rate=("maverick_rate", "mean"))
        .sort_values("maverick_rate", ascending=False).head(15)
    )
    fig = px.bar(
        dept_mav, x="maverick_rate", y="department_name", orientation="h",
        labels={"maverick_rate": "\u30de\u30fc\u30d9\u30ea\u30c3\u30af\u7387",
                "department_name": "\u90e8\u9580"},
        color="maverick_rate", color_continuous_scale="Reds",
    )
    fig.update_layout(
        yaxis={"categoryorder": "total ascending"}, height=380,
        margin=dict(l=160, r=10, t=20, b=40),
    )

    findings = all_findings(df_clean)
    return {
        "overall_rate": f"{overall:.1%}",
        "chart": _chart(fig),
        "table": findings.to_dict("records"),
        "table_cols": list(findings.columns) if not findings.empty else [],
    }


def _build_improvements(df_clean: pd.DataFrame) -> dict:
    candidates = improvement_mine(df_clean)
    total_saving = candidates["estimated_saving_net"].sum() if not candidates.empty else 0

    fig = go.Figure()
    if not candidates.empty:
        rule_counts = candidates.groupby("rule_id", as_index=False).size().rename(columns={"size": "count"})
        fig = px.bar(
            rule_counts, x="rule_id", y="count",
            labels={"rule_id": "\u30eb\u30fc\u30eb", "count": "\u4ef6\u6570"},
            color_discrete_sequence=["#9467bd"],
        )
        fig.update_layout(height=260, margin=dict(l=40, r=10, t=20, b=40))

    return {
        "total_saving": _fmt_yen(total_saving),
        "chart": _chart(fig),
        "table": candidates.to_dict("records") if not candidates.empty else [],
        "table_cols": list(candidates.columns) if not candidates.empty else [],
    }


def _build_map(df_clean: pd.DataFrame, df_suppliers: pd.DataFrame) -> str:
    if df_suppliers.empty or "prefecture" not in df_suppliers.columns:
        return ""

    sup_loc = (
        df_suppliers[["supplier_id", "supplier_parent_name", "prefecture"]]
        .drop_duplicates("supplier_id").dropna(subset=["prefecture"])
    )
    map_base = (
        df_clean.groupby(["supplier_id", "cat_large_name"], observed=True)["net_amount"]
        .sum().reset_index()
    )
    map_base = map_base.merge(sup_loc, on="supplier_id", how="left").dropna(subset=["prefecture"])
    map_base = (
        map_base.groupby(["supplier_parent_name", "cat_large_name", "prefecture"], observed=True)["net_amount"]
        .sum().reset_index()
    )
    map_base["lat"] = map_base["prefecture"].map(lambda p: _PREF_COORDS.get(p, (None, None))[0])
    map_base["lon"] = map_base["prefecture"].map(lambda p: _PREF_COORDS.get(p, (None, None))[1])
    map_base = map_base.dropna(subset=["lat", "lon"])

    if map_base.empty:
        return ""

    rng = np.random.default_rng(seed=42)
    map_base["lat"] += rng.uniform(-0.12, 0.12, len(map_base))
    map_base["lon"] += rng.uniform(-0.12, 0.12, len(map_base))
    map_base["spend_M"] = (map_base["net_amount"] / 1_000_000).round(1)

    line_traces: list[go.Scattermapbox] = []
    retail_df = df_clean[df_clean["cat_large_name"] == _RETAIL_CAT].copy() if "cat_large_name" in df_clean.columns else pd.DataFrame()
    if not retail_df.empty and "site_name" in retail_df.columns:
        logi = (
            retail_df.groupby(["supplier_id", "site_name"], observed=True)["net_amount"]
            .sum().reset_index()
        )
        logi = logi.merge(sup_loc[["supplier_id", "supplier_parent_name", "prefecture"]], on="supplier_id", how="left")
        logi = logi.dropna(subset=["prefecture"])
        logi = (
            logi.groupby(["supplier_parent_name", "prefecture", "site_name"], observed=True)["net_amount"]
            .sum().reset_index()
        )
        logi["sup_lat"] = logi["prefecture"].map(lambda p: _PREF_COORDS.get(p, (None, None))[0])
        logi["sup_lon"] = logi["prefecture"].map(lambda p: _PREF_COORDS.get(p, (None, None))[1])
        logi["site_lat"] = logi["site_name"].map(lambda s: _SITE_COORDS.get(s, (None, None))[0])
        logi["site_lon"] = logi["site_name"].map(lambda s: _SITE_COORDS.get(s, (None, None))[1])
        logi = logi.dropna(subset=["sup_lat", "site_lat"])

        if not logi.empty:
            q25, q50, q75 = logi["net_amount"].quantile([0.25, 0.50, 0.75])

            def _wbin(a: float) -> int:
                if a <= q25: return 1
                if a <= q50: return 2
                if a <= q75: return 4
                return 7

            logi["line_w"] = logi["net_amount"].apply(_wbin)
            first = True
            for w, label in [(1, "~25%"), (2, "25-50%"), (4, "50-75%"), (7, "75%+")]:
                sub = logi[logi["line_w"] == w]
                if sub.empty:
                    continue
                lats, lons = [], []
                for _, row in sub.iterrows():
                    lats += [row["sup_lat"], row["site_lat"], None]
                    lons += [row["sup_lon"], row["site_lon"], None]
                line_traces.append(go.Scattermapbox(
                    lat=lats, lon=lons, mode="lines",
                    line={"width": w, "color": "rgba(210,80,20,0.55)"},
                    name=f"\u7269\u6d41\u7db2({label})",
                    legendgroup="\u7269\u6d41\u7db2",
                    showlegend=first, hoverinfo="skip",
                ))
                first = False

    supplier_traces: list[go.Scattermapbox] = []
    max_amt = map_base["net_amount"].max()
    for cat, grp in map_base.groupby("cat_large_name", observed=True):
        color = _CAT_COLORS.get(cat, "#888888")
        sizes = (grp["net_amount"] / max_amt * 38 + 7).tolist()
        supplier_traces.append(go.Scattermapbox(
            lat=grp["lat"].tolist(), lon=grp["lon"].tolist(),
            mode="markers",
            marker={"size": sizes, "color": color, "opacity": 0.85},
            name=str(cat),
            text=grp["supplier_parent_name"].tolist(),
            customdata=grp[["spend_M", "prefecture"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "\u652f\u51fa: \u00a5%{customdata[0]:.1f}M<br>"
                "\u90fd\u9053\u5e9c\u770c: %{customdata[1]}<extra>" + str(cat) + "</extra>"
            ),
        ))

    active_sites = set(df_clean["site_name"].dropna().unique()) if "site_name" in df_clean.columns else set()
    site_rows = [{"site": s, "lat": c[0], "lon": c[1]} for s, c in _SITE_COORDS.items() if s in active_sites]
    star_traces: list[go.Scattermapbox] = []
    if site_rows:
        sdf = pd.DataFrame(site_rows)
        star_traces.append(go.Scattermapbox(
            lat=sdf["lat"].tolist(), lon=sdf["lon"].tolist(),
            mode="markers+text",
            marker={"size": 22, "color": "#FFD700", "opacity": 1.0},
            text=["\u2605 " + s for s in sdf["site"].tolist()],
            textposition="top right",
            textfont={"size": 12, "color": "#222"},
            name="\u62e0\u70b9 (\u2605)",
            hovertemplate="<b>%{text}</b><extra>\u62e0\u70b9</extra>",
        ))

    fig = go.Figure(data=line_traces + supplier_traces + star_traces)
    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox={"zoom": 4.8, "center": {"lat": 36.5, "lon": 137.5}},
        height=600, margin={"l": 0, "r": 0, "t": 0, "b": 0},
        legend_title="\u5927\u5206\u985e / \u62e0\u70b9",
        legend={"orientation": "v", "x": 1.01},
    )
    return _chart(fig)


def _build_kpi(
    df_po: pd.DataFrame,
    cats: list[str],
    medium_cats: list[str],
    small_cats: list[str],
    depts: list[str],
    sites: list[str],
    site_filter: str = "",
) -> dict:
    """Build KPI data. Uses all years (not date-filtered) for YoY comparison."""
    # Apply category/dept/site filters but NOT date filter
    df = _apply_filters(df_po, "2000-01-01", "2099-12-31", cats, medium_cats, small_cats, depts, sites)
    qr = quality_check(df)
    df_clean = qr["df_clean"]
    config = load_kpi_config(_ROOT)
    result = compute_kpi(df_clean, config)
    chart_html, table_rows = compute_milestones(result["merged_df"], site_filter)
    return {**result, "monthly_chart": chart_html, "milestone_table": table_rows}


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------
def _filter_params(request: Request) -> dict:
    """Extract filter query params from request."""
    p = request.query_params
    return {
        "start": p.get("start", "2023-01-01"),
        "end": p.get("end", "2025-12-31"),
        "cats": p.getlist("cats") if hasattr(p, "getlist") else request.query_params._list and [v for k, v in request.query_params._list if k == "cats"],
        "medium_cats": [v for k, v in request.query_params._list if k == "medium_cats"],
        "small_cats": [v for k, v in request.query_params._list if k == "small_cats"],
        "depts": [v for k, v in request.query_params._list if k == "depts"],
        "sites": [v for k, v in request.query_params._list if k == "sites"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/health")
def spend_health() -> dict:
    return {"module": "spend", "status": "ok"}


@router.get("/", response_class=HTMLResponse)
def spend_index(request: Request) -> HTMLResponse:
    df_po, df_items, df_suppliers = _get_data()

    all_large = sorted(df_po["cat_large_name"].dropna().unique()) if "cat_large_name" in df_po.columns else []
    all_medium = sorted(df_po["cat_medium_name"].dropna().unique()) if "cat_medium_name" in df_po.columns else []
    all_small = sorted(df_po["cat_small_name"].dropna().unique()) if "cat_small_name" in df_po.columns else []
    all_depts = sorted(df_po["department_name"].dropna().unique()) if "department_name" in df_po.columns else []
    all_sites = sorted(df_po["site_name"].dropna().unique()) if "site_name" in df_po.columns else []

    return TEMPLATES.TemplateResponse("spend/base.html", {
        "request": request,
        "all_large": all_large,
        "all_medium": all_medium,
        "all_small": all_small,
        "all_depts": all_depts,
        "all_sites": all_sites,
        "start": "2023-01-01",
        "end": "2025-12-31",
    })


@router.get("/dashboard", response_class=HTMLResponse)
def spend_dashboard(
    request: Request,
    tab: str = "overview",
    start: str = "2023-01-01",
    end: str = "2025-12-31",
    cats: Annotated[list[str], Query()] = [],
    medium_cats: Annotated[list[str], Query()] = [],
    small_cats: Annotated[list[str], Query()] = [],
    depts: Annotated[list[str], Query()] = [],
    sites: Annotated[list[str], Query()] = [],
) -> HTMLResponse:
    df_po, df_items, df_suppliers = _get_data()
    df = _apply_filters(df_po, start, end, cats, medium_cats, small_cats, depts, sites)

    if df.empty:
        return HTMLResponse("<p class='text-red-500 p-4'>フィルタ後のデータが0件です。条件を変更してください。</p>")

    qr = quality_check(df)
    df_clean = qr["df_clean"]

    total_spend = df_clean["net_amount"].sum()
    po_count = df_clean["po_number"].nunique()
    supplier_count = df_clean["supplier_id"].nunique() if "supplier_id" in df_clean.columns else 0
    avg_po = total_spend / po_count if po_count else 0

    kpis = {
        "total_spend": _fmt_yen(total_spend),
        "po_count": f"{po_count:,}",
        "supplier_count": f"{supplier_count:,}",
        "avg_po": _fmt_yen(avg_po),
    }

    ctx: dict = {
        "request": request,
        "tab": tab,
        "kpis": kpis,
        "start": start, "end": end,
        "sel_cats": cats, "sel_medium": medium_cats, "sel_small": small_cats,
        "sel_depts": depts, "sel_sites": sites,
    }

    if tab == "overview":
        ctx.update(_build_overview_charts(df_clean))
    elif tab == "concentration":
        ctx.update(_build_concentration_charts(df_clean))
    elif tab == "price_variance":
        ctx.update(_build_price_variance_charts(df_clean))
    elif tab == "compliance":
        ctx.update(_build_compliance_charts(df_clean))
    elif tab == "improvements":
        ctx.update(_build_improvements(df_clean))
    elif tab == "map":
        ctx["map_html"] = _build_map(df_clean, df_suppliers)
    elif tab == "kpi":
        ctx.update(_build_kpi(df_po, cats, medium_cats, small_cats, depts, sites))

    return TEMPLATES.TemplateResponse("spend/partials/dashboard.html", ctx)


@router.get("/filters/medium", response_class=HTMLResponse)
def filters_medium(
    request: Request,
    cats: Annotated[list[str], Query()] = [],
) -> HTMLResponse:
    df_po, _, _ = _get_data()
    if "cat_medium_name" not in df_po.columns:
        return HTMLResponse("")
    df_f = df_po[df_po["cat_large_name"].isin(cats)] if cats else df_po
    options = sorted(df_f["cat_medium_name"].dropna().unique())
    return TEMPLATES.TemplateResponse("spend/partials/filter_medium.html", {
        "request": request, "options": options,
    })


@router.get("/filters/small", response_class=HTMLResponse)
def filters_small(
    request: Request,
    cats: Annotated[list[str], Query()] = [],
    medium_cats: Annotated[list[str], Query()] = [],
) -> HTMLResponse:
    df_po, _, _ = _get_data()
    if "cat_small_name" not in df_po.columns:
        return HTMLResponse("")
    df_f = df_po.copy()
    if cats:
        df_f = df_f[df_f["cat_large_name"].isin(cats)]
    if medium_cats:
        df_f = df_f[df_f["cat_medium_name"].isin(medium_cats)]
    options = sorted(df_f["cat_small_name"].dropna().unique())
    return TEMPLATES.TemplateResponse("spend/partials/filter_small.html", {
        "request": request, "options": options,
    })


@router.get("/kpi/milestones", response_class=HTMLResponse)
def kpi_milestones(
    request: Request,
    kpi_site: str = "",
    cats: Annotated[list[str], Query()] = [],
    medium_cats: Annotated[list[str], Query()] = [],
    small_cats: Annotated[list[str], Query()] = [],
    depts: Annotated[list[str], Query()] = [],
    sites: Annotated[list[str], Query()] = [],
) -> HTMLResponse:
    """htmx partial: milestone chart + table for a selected site."""
    df_po, _, _ = _get_data()
    df = _apply_filters(df_po, "2000-01-01", "2099-12-31", cats, medium_cats, small_cats, depts, sites)
    qr = quality_check(df)
    df_clean = qr["df_clean"]
    config = load_kpi_config(_ROOT)
    result = compute_kpi(df_clean, config)
    chart_html, table_rows = compute_milestones(result["merged_df"], kpi_site)
    return TEMPLATES.TemplateResponse("spend/partials/kpi_milestones.html", {
        "request": request,
        "monthly_chart": chart_html,
        "milestone_table": table_rows,
    })
