"""Spend Analytics Dashboard — thin Streamlit entry point."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Helper: display DataFrame as HTML table (avoids pyarrow DLL dependency)
# ---------------------------------------------------------------------------
_TABLE_CSS = """
<style>
.spend-table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
.spend-table th { background: #f0f2f6; text-align: left; padding: 6px 10px;
                  border-bottom: 2px solid #ccc; white-space: nowrap; }
.spend-table td { padding: 5px 10px; border-bottom: 1px solid #e8e8e8; }
.spend-table tr:hover td { background: #f8f9fa; }
</style>
"""

def _show_table(df: pd.DataFrame) -> None:
    """Render DataFrame as HTML — no pyarrow required."""
    st.markdown(_TABLE_CSS + df.to_html(index=False, classes="spend-table"), unsafe_allow_html=True)

def _sev_row_style(row: pd.Series) -> list[str]:
    colors = {"HIGH": "background-color:#ffd6d6", "MEDIUM": "background-color:#fff3cd"}
    col = "severity" if "severity" in row.index else "priority"
    bg = colors.get(row.get(col, ""), "")
    return [bg] * len(row)

def _show_styled_table(df: pd.DataFrame, color_col: str) -> None:
    """Render DataFrame with row-level color based on severity/priority column."""
    styled_html = (
        df.style
        .apply(_sev_row_style, axis=1)
        .set_table_attributes('class="spend-table"')
        .hide(axis="index")
        .to_html()
    )
    st.markdown(_TABLE_CSS + styled_html, unsafe_allow_html=True)

# Make proc_core importable when running from project root via
#   uv run streamlit run apps/spend-analytics/app.py
PROJECT_ROOT = Path(__file__).parents[2]
_PACKAGES = PROJECT_ROOT / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from proc_core.spend.loader import load_all
from proc_core.spend.quality import check as quality_check
from proc_core.spend.spend_overview import build_cube
from proc_core.spend.concentration import supplier_concentration
from proc_core.spend.price_variance import by_category as price_by_category
from proc_core.spend.compliance import maverick_summary, all_findings
from proc_core.spend.improvement_mining import mine as improvement_mine

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data" / "samples"

st.set_page_config(
    page_title="Spend Analytics",
    page_icon=":bar_chart:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar — filters & load button
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Spend Analytics")
    st.markdown("---")

    st.subheader("データ期間")
    col_s, col_e = st.columns(2)
    with col_s:
        start_date = st.date_input("開始", value=datetime.date(2023, 1, 1))
    with col_e:
        end_date = st.date_input("終了", value=datetime.date(2025, 12, 31))

    # Placeholder multiselects — populated after first load
    st.markdown("**コモディティ**")
    cat_large_placeholder = st.empty()
    cat_medium_placeholder = st.empty()
    cat_small_placeholder = st.empty()
    st.markdown("**購買属性**")
    dept_filter_placeholder = st.empty()
    site_filter_placeholder = st.empty()

    load_btn = st.button("読込", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="データ読込中...")
def _load(data_dir: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return load_all(data_dir, mapping="default", config_root=PROJECT_ROOT)


if load_btn:
    _load.clear()  # キャッシュをクリアして最新のyaml設定で再読込
if "df_po_raw" not in st.session_state or load_btn:
    try:
        df_po_raw, df_items, df_suppliers = _load(str(DATA_DIR))
        st.session_state["df_po_raw"] = df_po_raw
        st.session_state["df_items"] = df_items
        st.session_state["df_suppliers"] = df_suppliers
    except FileNotFoundError as e:
        st.error(f"データファイルが見つかりません: {e}")
        st.stop()

df_po_raw: pd.DataFrame = st.session_state["df_po_raw"]

# ---------------------------------------------------------------------------
# フィルタ初期化フラグ処理 — バージョンカウンタでキーを変えて強制再生成
# ---------------------------------------------------------------------------
if st.session_state.pop("_reset_filters", False):
    st.session_state["_fv"] = st.session_state.get("_fv", 0) + 1

_fv = st.session_state.get("_fv", 0)

# ---------------------------------------------------------------------------
# Sidebar multiselects — populated from loaded data
# ---------------------------------------------------------------------------
all_depts = sorted(df_po_raw["department_name"].dropna().unique().tolist()) if "department_name" in df_po_raw.columns else []
all_sites = sorted(df_po_raw["site_name"].dropna().unique().tolist()) if "site_name" in df_po_raw.columns else []

with st.sidebar:
    # --- 大分類 (always all options) ---
    all_large = sorted(df_po_raw["cat_large_name"].dropna().unique()) if "cat_large_name" in df_po_raw.columns else []
    sel_cats = cat_large_placeholder.multiselect("大分類", options=all_large, default=[], key=f"sel_large_{_fv}")

    # --- 中分類 (cascade from 大分類) ---
    if "cat_medium_name" in df_po_raw.columns:
        df_for_med = df_po_raw[df_po_raw["cat_large_name"].isin(sel_cats)] if sel_cats else df_po_raw
        all_medium = sorted(df_for_med["cat_medium_name"].dropna().unique())
    else:
        all_medium = []
    sel_medium_cats = cat_medium_placeholder.multiselect("中分類", options=all_medium, default=[], key=f"sel_medium_{_fv}")

    # --- 小分類 (cascade from 大分類 + 中分類) ---
    if "cat_small_name" in df_po_raw.columns:
        df_for_sml = df_po_raw.copy()
        if sel_cats:
            df_for_sml = df_for_sml[df_for_sml["cat_large_name"].isin(sel_cats)]
        if sel_medium_cats:
            df_for_sml = df_for_sml[df_for_sml["cat_medium_name"].isin(sel_medium_cats)]
        all_small = sorted(df_for_sml["cat_small_name"].dropna().unique())
    else:
        all_small = []
    sel_small_cats = cat_small_placeholder.multiselect("小分類", options=all_small, default=[], key=f"sel_small_{_fv}")

    sel_depts = dept_filter_placeholder.multiselect("部門", options=all_depts, default=[], key=f"sel_dept_{_fv}")
    sel_sites = site_filter_placeholder.multiselect("拠点", options=all_sites, default=[], key=f"sel_site_{_fv}")

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
df = df_po_raw.copy()
df = df[(df["posting_date"] >= pd.Timestamp(start_date)) & (df["posting_date"] <= pd.Timestamp(end_date))]
if sel_cats:
    df = df[df["cat_large_name"].isin(sel_cats)]
if sel_medium_cats:
    df = df[df["cat_medium_name"].isin(sel_medium_cats)]
if sel_small_cats:
    df = df[df["cat_small_name"].isin(sel_small_cats)]
if sel_depts:
    df = df[df["department_name"].isin(sel_depts)]
if sel_sites:
    df = df[df["site_name"].isin(sel_sites)]

if df.empty:
    st.warning("フィルタ後のデータが0件です。条件を変更してください。")
    st.stop()

# Quality check → clean data
qr = quality_check(df)
df_clean = qr["df_clean"]

# ---------------------------------------------------------------------------
# KPI bar
# ---------------------------------------------------------------------------
total_spend = df_clean["net_amount"].sum()
po_count = df_clean["po_number"].nunique()
supplier_count = df_clean["supplier_id"].nunique() if "supplier_id" in df_clean.columns else 0
avg_po = total_spend / po_count if po_count else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("総支出 (税抜)", f"¥{total_spend:,.0f}")
k2.metric("PO件数", f"{po_count:,}")
k3.metric("サプライヤ数", f"{supplier_count:,}")
k4.metric("平均PO金額", f"¥{avg_po:,.0f}")

st.markdown("---")

# ---------------------------------------------------------------------------
# 5 Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Spend Overview",
    "Concentration (集中度)",
    "Price Variance (単価ばらつき)",
    "Compliance / Maverick",
    "Improvement Candidates",
    "Supplier Map",
])

# ===========================================================================
# Tab 1: Spend Overview
# ===========================================================================
with tab1:
    st.subheader("月次トレンド")
    monthly = (
        df_clean.copy()
        .assign(month=lambda d: d["posting_date"].dt.to_period("M").astype(str))
        .groupby("month", as_index=False)["net_amount"]
        .sum()
        .sort_values("month")
    )
    fig_monthly = px.bar(
        monthly, x="month", y="net_amount",
        labels={"month": "月", "net_amount": "支出 (税抜)"},
        color_discrete_sequence=["#1f77b4"],
    )
    fig_monthly.update_layout(xaxis_tickangle=-45, height=320)
    st.plotly_chart(fig_monthly, use_container_width=True)

    col_cat, col_dept = st.columns(2)

    with col_cat:
        st.subheader("カテゴリ別支出 (上位10)")
        if "cat_large_name" in df_clean.columns:
            cat_agg = (
                df_clean.groupby("cat_large_name", as_index=False)["net_amount"]
                .sum()
                .sort_values("net_amount", ascending=False)
                .head(10)
            )
            fig_cat = px.bar(
                cat_agg, x="net_amount", y="cat_large_name", orientation="h",
                labels={"net_amount": "支出 (税抜)", "cat_large_name": "大分類"},
                color_discrete_sequence=["#2ca02c"],
            )
            fig_cat.update_layout(yaxis={"categoryorder": "total ascending"}, height=350)
            st.plotly_chart(fig_cat, use_container_width=True)

    with col_dept:
        st.subheader("部門別支出 (上位10)")
        if "department_name" in df_clean.columns:
            dept_agg = (
                df_clean.groupby("department_name", as_index=False)["net_amount"]
                .sum()
                .sort_values("net_amount", ascending=False)
                .head(10)
            )
            fig_dept = px.bar(
                dept_agg, x="net_amount", y="department_name", orientation="h",
                labels={"net_amount": "支出 (税抜)", "department_name": "部門"},
                color_discrete_sequence=["#ff7f0e"],
            )
            fig_dept.update_layout(yaxis={"categoryorder": "total ascending"}, height=350)
            st.plotly_chart(fig_dept, use_container_width=True)

    # -------------------------------------------------------------------
    # Treemap — spend by category → supplier
    # -------------------------------------------------------------------
    st.markdown("---")
    _th_col, _btn_col = st.columns([5, 1])
    _th_col.subheader("スペンドツリーマップ (大分類 → 中分類 → サプライヤ)")
    if _btn_col.button("🔄 初期化", key="treemap_reset", use_container_width=True):
        st.session_state["_reset_filters"] = True
        st.rerun()

    _has_cat = "cat_large_name" in df_clean.columns
    _has_med = "cat_medium_name" in df_clean.columns
    _has_sup = "supplier_parent_name" in df_clean.columns

    if _has_cat and _has_med and _has_sup:
        df_tree = (
            df_clean.groupby(
                ["cat_large_name", "cat_medium_name", "supplier_parent_name"], observed=True
            )["net_amount"]
            .sum()
            .reset_index()
        )
        # 中分類ごとのサプライヤ数で色分け: 1社=赤, 2社=オレンジ, 3社以上=茶色
        _med_sup_count = (
            df_clean.groupby("cat_medium_name", observed=True)["supplier_parent_name"].nunique()
        )
        def _tree_color(count: int) -> str:
            if count == 1:
                return "#FF4444"   # 赤: シングルソース
            if count >= 3:
                return "#8B4513"   # 茶色: 3社以上
            return "#FFA040"       # オレンジ: 2社
        _color_map = {med: _tree_color(int(cnt)) for med, cnt in _med_sup_count.items()}
        df_tree["_color_key"] = df_tree["cat_medium_name"]
        fig_tree = px.treemap(
            df_tree,
            path=[px.Constant("全体"), "cat_large_name", "cat_medium_name", "supplier_parent_name"],
            values="net_amount",
            color="_color_key",
            color_discrete_map=_color_map,
            custom_data=["net_amount"],
        )
        fig_tree.update_traces(
            texttemplate="<b>%{label}</b><br>¥%{value:,.0f}",
            hovertemplate="<b>%{label}</b><br>支出: ¥%{value:,.0f}<br>シェア: %{percentRoot:.1%}<extra></extra>",
            textfont_size=12,
        )
        fig_tree.update_layout(height=580, margin={"l": 0, "r": 0, "t": 10, "b": 0})
        _single_meds = sorted(_med_sup_count[_med_sup_count == 1].index.tolist())
        st.caption("🔴 1社  🟠 2社  🟫 3社以上" + (
            f"　　シングルソース中分類: {', '.join(_single_meds)}" if _single_meds else ""
        ))
        st.plotly_chart(fig_tree, use_container_width=True)
    elif _has_cat and _has_sup:
        # cat_medium_name がない場合は大分類のみ
        df_tree = (
            df_clean.groupby(["cat_large_name", "supplier_parent_name"], observed=True)["net_amount"]
            .sum().reset_index()
        )
        df_tree["_color_key"] = df_tree["cat_large_name"]
        fig_tree = px.treemap(
            df_tree,
            path=[px.Constant("全体"), "cat_large_name", "supplier_parent_name"],
            values="net_amount", color="_color_key",
            color_discrete_sequence=px.colors.qualitative.Pastel,
            custom_data=["net_amount"],
        )
        fig_tree.update_traces(
            texttemplate="<b>%{label}</b><br>¥%{value:,.0f}",
            hovertemplate="<b>%{label}</b><br>支出: ¥%{value:,.0f}<br>シェア: %{percentRoot:.1%}<extra></extra>",
            textfont_size=12,
        )
        fig_tree.update_layout(height=520, margin={"l": 0, "r": 0, "t": 10, "b": 0})
        st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("cat_large_name / supplier_parent_name 列が必要です")

# ===========================================================================
# Tab 2: Concentration
# ===========================================================================
with tab2:
    # supplier_name = supplier_child_name (50社) で集中度を見る
    SUPPLIER_LEVEL_COL = "supplier_name"

    conc = supplier_concentration(df_clean, level=SUPPLIER_LEVEL_COL)
    ranked_all = conc["ranked_df"].reset_index(drop=True)  # 全サプライヤ
    n_total = len(ranked_all)

    # 表示は上位N社に限定（全量だと可読性が落ちるため）
    DISPLAY_TOP_N_SUPPLIERS = 50
    ranked = ranked_all.head(DISPLAY_TOP_N_SUPPLIERS).copy()
    n_plot = len(ranked)

    # 80% ラインを超える最初のサプライヤ位置を特定
    _80_idx = int((ranked_all["cumulative_pct"] >= 80).idxmax()) if (ranked_all["cumulative_pct"] >= 80).any() else max(n_total - 1, 0)
    _80_sup_count = _80_idx + 1
    _80_sup = ranked_all.loc[_80_idx, SUPPLIER_LEVEL_COL] if n_total else ""

    # ヘッダー + 目立つ80%メトリクス
    _hcol1, _hcol2 = st.columns([3, 1])
    _hcol1.subheader(f"サプライヤ集中度 (全{n_total}社 / 表示上位{n_plot}社)")
    _hcol2.metric(
        label="購入額80%到達社数",
        value=f"{_80_sup_count} 社 / {n_total} 社",
        help=f"上位{_80_sup_count}社で全購入額の80%に達します",
    )

    if n_total > n_plot and _80_idx >= n_plot:
        st.caption(f"※ 購入額80%到達点（上位{_80_sup_count}社）は表示範囲（上位{n_plot}社）の外です")

    _idx_for_plot = min(_80_idx, max(n_plot - 1, 0))
    bar_colors = ["#1f77b4" if i <= _idx_for_plot else "#c8c8c8" for i in range(n_plot)]
    fig_conc = go.Figure()
    fig_conc.add_trace(go.Bar(
        x=ranked[SUPPLIER_LEVEL_COL], y=ranked["share_pct"],
        name="シェア (%)", marker_color=bar_colors,
    ))
    fig_conc.add_trace(go.Scatter(
        x=ranked[SUPPLIER_LEVEL_COL], y=ranked["cumulative_pct"],
        name="累積シェア (%)", yaxis="y2", mode="lines+markers",
        line={"color": "#d62728", "width": 2},
        marker={"size": 4},
    ))
    # 80% 水平ライン
    fig_conc.add_shape(
        type="line",
        xref="paper", x0=0, x1=1,
        yref="y2", y0=80, y1=80,
        line={"color": "#ff7f0e", "width": 2, "dash": "dash"},
    )
    fig_conc.add_annotation(
        xref="paper", x=1.01, yref="y2", y=80,
        text="80%", showarrow=False,
        font={"color": "#ff7f0e", "size": 12},
        xanchor="left",
    )
    # 80%到達ラインの垂直マーカー（表示範囲内の場合のみ）
    if _80_idx < n_plot:
        fig_conc.add_shape(
            type="line",
            xref="x", x0=_80_sup, x1=_80_sup,
            yref="paper", y0=0, y1=1,
            line={"color": "#ff7f0e", "width": 2, "dash": "dot"},
        )
        fig_conc.add_annotation(
            xref="x", x=_80_sup, yref="paper", y=1.0,
            text=f"{_80_sup_count}社で80%",
            showarrow=True, arrowhead=2, arrowcolor="#ff7f0e",
            ax=30, ay=-20,
            font={"color": "#ff7f0e", "size": 11},
            xanchor="left",
        )
    fig_conc.update_layout(
        yaxis={"title": "シェア (%)"},
        yaxis2={"title": "累積シェア (%)", "overlaying": "y", "side": "right", "range": [0, 105]},
        xaxis={"tickangle": -60, "tickfont": {"size": 9}},
        height=520,
        legend={"orientation": "h", "y": -0.25},
        margin={"r": 60, "b": 120},
    )

    # x軸: supplier_group_name は既に名前なのでそのまま表示
    _ticks = ranked[SUPPLIER_LEVEL_COL].tolist()
    fig_conc.update_xaxes(
        type="category",
        tickmode="array",
        tickvals=_ticks,
        ticktext=_ticks,
        showticklabels=True,
    )
    st.plotly_chart(fig_conc, use_container_width=True)
    st.caption(f"🔵 青: 80%到達までの上位{_80_sup_count}社　⬜ 灰: それ以降　🟠 点線: 累積80%ライン")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Top1 シェア", f"{conc['top1_share']:.1f}%")
    m2.metric("Top3 シェア", f"{conc['top3_share']:.1f}%")
    m3.metric("Top5 シェア", f"{conc['top5_share']:.1f}%")
    m4.metric("Top10 シェア", f"{conc['top10_share']:.1f}%")
    m5.metric("HHI", f"{conc['hhi']:.4f}")

    st.markdown("---")
    st.subheader("シングルソース カテゴリ")
    # NOTE: ツリーマップの「赤(1社)」と定義を揃える。
    # cat_medium_name ごとに supplier_parent_name のユニーク数が 1 のものをシングルソース扱いにする。
    if {"cat_medium_name", "supplier_parent_name"}.issubset(df_clean.columns):
        ss_med = (
            df_clean.groupby("cat_medium_name", observed=True)["supplier_parent_name"]
            .nunique()
        )
        ss_list = sorted(ss_med[ss_med == 1].index.tolist())
        if ss_list:
            ss_base = df_clean[df_clean["cat_medium_name"].isin(ss_list)].copy()

            group_col = None
            if "supplier_group_name" in ss_base.columns:
                group_col = "supplier_group_name"
            elif "supplier_group" in ss_base.columns:
                group_col = "supplier_group"

            group_keys: list[str] = ["cat_medium_name", "supplier_parent_name"]
            if "cat_large_name" in ss_base.columns:
                group_keys.insert(0, "cat_large_name")
            if group_col is not None:
                group_keys.append(group_col)

            ss_tbl = (
                ss_base.groupby(group_keys, observed=True)["net_amount"]
                .sum()
                .reset_index()
                .reset_index(drop=True)
            )

            # ---- Sort UI (HTML table has no interactive sorting) ----
            sort_options: dict[str, tuple[list[str], list[bool]]] = {
                "金額（降順）": (["net_amount"], [False]),
                "金額（昇順）": (["net_amount"], [True]),
                "Supplier名（昇順）": (["supplier_parent_name", "net_amount"], [True, False]),
                "中分類（昇順）": (["cat_medium_name", "net_amount"], [True, False]),
            }
            if "cat_large_name" in ss_tbl.columns:
                sort_options["大分類（昇順）"] = (["cat_large_name", "net_amount"], [True, False])
            if group_col is not None and group_col in ss_tbl.columns:
                sort_options["グループ名（昇順）"] = ([group_col, "net_amount"], [True, False])

            sort_label = st.selectbox(
                "ソート",
                options=list(sort_options.keys()),
                index=0,
                key="ss_sort",
            )
            sort_cols, sort_asc = sort_options[sort_label]
            ss_tbl = ss_tbl.sort_values(sort_cols, ascending=sort_asc).reset_index(drop=True)

            ss_tbl["amount_yen"] = ss_tbl["net_amount"].map(lambda v: f"\u00a5{v:,.0f}")
            show_cols = [c for c in ["cat_large_name", "cat_medium_name", "supplier_parent_name", group_col, "amount_yen"] if c and c in ss_tbl.columns]
            _show_table(ss_tbl[show_cols])

            # ---- Subtotals ----
            show_subtotal = st.checkbox("小計を表示", value=True, key="ss_show_subtotal")
            if show_subtotal:
                if "cat_large_name" in ss_tbl.columns:
                    sub_key = "cat_large_name"
                    label = "大分類"
                else:
                    sub_key = "cat_medium_name"
                    label = "中分類"

                sub_tbl = (
                    ss_tbl.groupby(sub_key, observed=True)["net_amount"]
                    .sum()
                    .reset_index()
                    .sort_values("net_amount", ascending=False)
                    .reset_index(drop=True)
                )
                sub_tbl["amount_yen"] = sub_tbl["net_amount"].map(lambda v: f"\u00a5{v:,.0f}")
                st.caption(f"小計（{label}別）")
                _show_table(sub_tbl[[sub_key, "amount_yen"]].rename(columns={sub_key: label}))

                grand_total = float(ss_tbl["net_amount"].sum())
                st.caption(f"総計: \u00a5{grand_total:,.0f}")
        else:
            st.info("シングルソースカテゴリなし")
    else:
        # fallback: 列がない場合は proc_core の結果をそのまま出す
        ss = conc.get("single_source_categories", [])
        if ss:
            _show_table(pd.DataFrame({"cat_medium_name": ss}))
        else:
            st.info("シングルソースカテゴリなし")

# ===========================================================================
# Tab 3: Price Variance
# ===========================================================================
with tab3:
    pv = price_by_category(df_clean, cv_threshold=0.30)

    st.subheader("CV上位カテゴリ (上位15)")
    top_cv = pv.head(15).copy()
    if not top_cv.empty:
        label_col = "cat_small_name" if "cat_small_name" in top_cv.columns else "cat_small_id"
        fig_pv = px.bar(
            top_cv, x="price_cv", y=label_col, orientation="h",
            labels={"price_cv": "変動係数 (CV)", label_col: "小分類"},
            color="price_cv", color_continuous_scale="Reds",
        )
        fig_pv.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
        st.plotly_chart(fig_pv, use_container_width=True)

    st.subheader("詳細テーブル (CV > 0.3)")
    high_cv = pv[pv["price_cv"] > 0.30].reset_index(drop=True) if "price_cv" in pv.columns else pd.DataFrame()
    if not high_cv.empty:
        _show_table(high_cv)
    else:
        st.info("CV > 0.3 の品目なし")

# ===========================================================================
# Tab 4: Compliance / Maverick
# ===========================================================================
with tab4:
    mav = maverick_summary(df_clean)
    overall_mav_rate = (
        df_clean[df_clean["contract_flag"].astype(int) == 0]["net_amount"].sum()
        / df_clean["net_amount"].sum()
    ) if "contract_flag" in df_clean.columns else 0.0

    st.metric("全体マーベリック率", f"{overall_mav_rate:.1%}")

    st.subheader("部門別マーベリック率")
    dept_mav = (
        mav.groupby("department_name", as_index=False)
        .agg(maverick_rate=("maverick_rate", "mean"))
        .sort_values("maverick_rate", ascending=False)
        .head(15)
    )
    fig_mav = px.bar(
        dept_mav, x="maverick_rate", y="department_name", orientation="h",
        labels={"maverick_rate": "マーベリック率", "department_name": "部門"},
        color="maverick_rate", color_continuous_scale="Reds",
    )
    fig_mav.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
    st.plotly_chart(fig_mav, use_container_width=True)

    st.subheader("全発見事項")
    findings = all_findings(df_clean)
    if not findings.empty:
        _show_styled_table(findings, color_col="severity")
    else:
        st.info("発見事項なし")

# ===========================================================================
# Tab 5: Improvement Candidates
# ===========================================================================
with tab5:
    candidates = improvement_mine(df_clean)

    total_saving = candidates["estimated_saving_net"].sum() if not candidates.empty else 0
    st.metric("総推定節減額", f"¥{total_saving:,.0f}")

    if not candidates.empty:
        st.subheader("ルール別 件数")
        rule_counts = candidates.groupby("rule_id", as_index=False).size().rename(columns={"size": "count"})
        fig_rules = px.bar(
            rule_counts, x="rule_id", y="count",
            labels={"rule_id": "ルール", "count": "件数"},
            color_discrete_sequence=["#9467bd"],
        )
        fig_rules.update_layout(height=280)
        st.plotly_chart(fig_rules, use_container_width=True)

        st.subheader("改善候補一覧 (priority順)")
        _show_styled_table(candidates, color_col="priority")
    else:
        st.info("改善候補なし")

# ===========================================================================
# Tab 6: Supplier Map
# ===========================================================================
_PREF_COORDS: dict[str, tuple[float, float]] = {
    "\u5317\u6d77\u9053": (43.064, 141.347), "\u9752\u68ee\u770c": (40.824, 140.740), "\u5ca9\u624b\u770c": (39.704, 141.153),
    "\u5bae\u57ce\u770c": (38.269, 140.872), "\u79cb\u7530\u770c": (39.719, 140.102), "\u5c71\u5f62\u770c": (38.240, 140.363),
    "\u798f\u5cf6\u770c": (37.750, 140.468), "\u8328\u57ce\u770c": (36.342, 140.447), "\u6803\u6728\u770c": (36.566, 139.884),
    "\u7fa4\u99ac\u770c": (36.391, 139.061), "\u57fc\u7389\u770c": (35.857, 139.649), "\u5343\u8449\u770c": (35.605, 140.123),
    "\u6771\u4eac\u90fd": (35.676, 139.650), "\u795e\u5948\u5ddd\u770c": (35.448, 139.643), "\u65b0\u6f5f\u770c": (37.903, 139.023),
    "\u5bcc\u5c71\u770c": (36.695, 137.211), "\u77f3\u5ddd\u770c": (36.595, 136.626), "\u798f\u4e95\u770c": (36.065, 136.222),
    "\u5c71\u68a8\u770c": (35.664, 138.568), "\u9577\u91ce\u770c": (36.651, 138.181), "\u5c90\u961c\u770c": (35.391, 136.722),
    "\u9759\u5ca1\u770c": (34.977, 138.383), "\u611b\u77e5\u770c": (35.180, 136.907), "\u4e09\u91cd\u770c": (34.730, 136.509),
    "\u6ecb\u8cc0\u770c": (35.004, 135.869), "\u4eac\u90fd\u5e9c": (35.012, 135.768), "\u5927\u962a\u5e9c": (34.694, 135.502),
    "\u5175\u5eab\u770c": (34.691, 135.183), "\u5948\u826f\u770c": (34.685, 135.833), "\u548c\u6b4c\u5c71\u770c": (34.226, 135.168),
    "\u9ce5\u53d6\u770c": (35.504, 134.238), "\u5cf6\u6839\u770c": (35.472, 133.051), "\u5ca1\u5c71\u770c": (34.662, 133.935),
    "\u5e83\u5cf6\u770c": (34.397, 132.460), "\u5c71\u53e3\u770c": (34.186, 131.471), "\u5fb3\u5cf6\u770c": (34.066, 134.559),
    "\u9999\u5ddd\u770c": (34.340, 134.043), "\u611b\u5a9b\u770c": (33.842, 132.766), "\u9ad8\u77e5\u770c": (33.560, 133.531),
    "\u798f\u5ca1\u770c": (33.590, 130.402), "\u4f50\u8cc0\u770c": (33.264, 130.301), "\u9577\u5d0e\u770c": (32.745, 129.874),
    "\u718a\u672c\u770c": (32.790, 130.742), "\u5927\u5206\u770c": (33.238, 131.613), "\u5bae\u5d0e\u770c": (31.911, 131.424),
    "\u9e7f\u5150\u5cf6\u770c": (31.560, 130.558), "\u6c96\u7e04\u770c": (26.212, 127.681),
}

# 拠点座標 (site_name → lat/lon)
_SITE_COORDS: dict[str, tuple[float, float]] = {
    "\u672c\u793e\uff08\u6771\u4eac\uff09": (35.681, 139.767),        # 本社（東京）
    "\u6a2a\u6d5c\u30aa\u30d5\u30a3\u30b9": (35.443, 139.638),        # 横浜オフィス
    "\u95a2\u6771\u7269\u6d41\u30bb\u30f3\u30bf\u30fc": (35.820, 139.950),  # 関東物流センター
    "\u95a2\u897f\u7269\u6d41\u30bb\u30f3\u30bf\u30fc": (34.735, 135.520),  # 関西物流センター
    "\u540d\u53e4\u5c4b\u62e0\u70b9": (35.170, 136.906),              # 名古屋拠点
}

# Vivid palette: same order as px uses for cat_large_name categories
_CAT_COLORS = {
    cat: color
    for cat, color in zip(
        ["IT", "\u30d3\u30b8\u30cd\u30b9\u30b5\u30fc\u30d3\u30b9",
         "\u30de\u30fc\u30b1\u30c6\u30a3\u30f3\u30b0", "\u30ea\u30c6\u30fc\u30eb\u30d7\u30ed\u30e2"],
        px.colors.qualitative.Vivid,
    )
}
_RETAIL_CAT = "\u30ea\u30c6\u30fc\u30eb\u30d7\u30ed\u30e2"  # リテールプロモ

with tab6:
    st.subheader("\u30b5\u30d7\u30e9\u30a4\u30e4\u5730\u56f3 (\u30b3\u30e2\u30c7\u30a3\u30c6\u30a3\u5225)")

    df_suppliers_raw: pd.DataFrame = st.session_state.get("df_suppliers", pd.DataFrame())

    if df_suppliers_raw.empty or "prefecture" not in df_suppliers_raw.columns:
        st.info("\u30b5\u30d7\u30e9\u30a4\u30e4\u30fc\u30de\u30b9\u30bf\u306b prefecture \u5217\u304c\u5fc5\u8981\u3067\u3059")
    else:
        # supplier_id → prefecture / supplier_parent_name
        sup_loc = (
            df_suppliers_raw[["supplier_id", "supplier_parent_name", "prefecture"]]
            .drop_duplicates("supplier_id")
            .dropna(subset=["prefecture"])
        )

        # PO spend: supplier_id × cat_large → join → re-aggregate to parent level
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
            st.warning("\u90fd\u9053\u5e9c\u770c\u30c7\u30fc\u30bf\u3092\u30de\u30c3\u30d7\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002")
        else:
            rng = np.random.default_rng(seed=42)
            map_base["lat"] += rng.uniform(-0.12, 0.12, len(map_base))
            map_base["lon"] += rng.uniform(-0.12, 0.12, len(map_base))
            map_base["spend_M"] = (map_base["net_amount"] / 1_000_000).round(1)

            # ── Layer 1: リテールプロモ 物流網ライン ──────────────────────────
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
                    width_map = {1: "~25%", 2: "25-50%", 4: "50-75%", 7: "75%+"}
                    def _wbin(a):
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
                            name=f"\u7269\u6d41\u7db2({label})" if first else f"\u7269\u6d41\u7db2({label})",
                            legendgroup="\u7269\u6d41\u7db2",
                            showlegend=first,
                            hoverinfo="skip",
                        ))
                        first = False

            # ── Layer 2: サプライヤピン (color by category) ───────────────────
            supplier_traces: list[go.Scattermapbox] = []
            for cat, grp in map_base.groupby("cat_large_name", observed=True):
                color = _CAT_COLORS.get(cat, "#888888")
                max_amt = map_base["net_amount"].max()
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

            # ── Layer 3: 拠点 星マーカー ─────────────────────────────────────
            active_sites = set(df_clean["site_name"].dropna().unique()) if "site_name" in df_clean.columns else set()
            site_rows = [
                {"site": s, "lat": c[0], "lon": c[1]}
                for s, c in _SITE_COORDS.items() if s in active_sites
            ]
            star_traces: list[go.Scattermapbox] = []
            if site_rows:
                sdf = pd.DataFrame(site_rows)
                # Mapbox open-street-map doesn't load the "star-15" sprite;
                # use a gold circle marker with "★" prefix in the text label instead.
                star_traces.append(go.Scattermapbox(
                    lat=sdf["lat"].tolist(), lon=sdf["lon"].tolist(),
                    mode="markers+text",
                    marker={"size": 22, "color": "#FFD700", "opacity": 1.0},
                    text=["\u2605 " + s for s in sdf["site"].tolist()],
                    textposition="top right",
                    textfont={"size": 12, "color": "#222", "weight": "bold"},
                    name="\u62e0\u70b9 (\u2605)",
                    hovertemplate="<b>%{text}</b><extra>\u62e0\u70b9</extra>",
                ))

            # ── Assemble figure: lines → supplier pins → stars ────────────────
            fig_map = go.Figure(data=line_traces + supplier_traces + star_traces)
            fig_map.update_layout(
                mapbox_style="open-street-map",
                mapbox={"zoom": 4.8, "center": {"lat": 36.5, "lon": 137.5}},
                height=640,
                margin={"l": 0, "r": 0, "t": 0, "b": 0},
                legend_title="\u5927\u5206\u985e / \u62e0\u70b9",
                legend={"orientation": "v", "x": 1.01},
            )
            st.plotly_chart(fig_map, use_container_width=True)

            # 都道府県別集計テーブル
            with st.expander("\u90fd\u9053\u5e9c\u770c\u5225 \u30b5\u30d7\u30e9\u30a4\u30e4\u30fc\u4e00\u89a7"):
                pref_tbl = (
                    map_base.groupby(["prefecture", "supplier_parent_name", "cat_large_name"], as_index=False)
                    .agg(spend_M=("net_amount", lambda x: round(x.sum() / 1_000_000, 1)))
                    .sort_values("spend_M", ascending=False)
                    .reset_index(drop=True)
                )
                _show_table(pref_tbl)
