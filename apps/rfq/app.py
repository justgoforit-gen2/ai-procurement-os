"""
RFQ Workflow System — Streamlit App (PoC)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# パス設定
PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(Path(__file__).parent))   # apps/rfq/ → db.py が見える

from db import (
    init_db, create_rfq, get_rfq_list, get_rfq, update_rfq_status,
    add_rfq_suppliers, get_rfq_suppliers, get_dashboard_kpis, log_action,
    calc_required_quote_count, dispatch_rfq, update_supplier_response,
    upsert_evaluation, get_evaluations,
    create_approval_route, get_approval_route, update_approval_status,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data" / "samples"
ROLES = ["Buyer", "Requester", "Approver", "Admin"]
STATUS_LIST = ["Draft", "RFQ送信", "見積回収中", "評価中", "承認待ち", "完了"]
STATUS_COLOR = {
    "Draft": "#9e9e9e",
    "RFQ送信": "#2196f3",
    "見積回収中": "#ff9800",
    "評価中": "#9c27b0",
    "承認待ち": "#f44336",
    "完了": "#4caf50",
}
RESPONSE_STATUS_OPTS = ["Pending", "受領済", "要修正", "辞退"]
LEVEL_ORDER = {"Staff": 0, "Senior": 1, "Lead": 2, "Manager": 3, "Director": 4, "Exec": 5}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="RFQ Workflow System",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DB 初期化
# ---------------------------------------------------------------------------
init_db()

# ---------------------------------------------------------------------------
# マスターデータ読込
# ---------------------------------------------------------------------------
PROCUREMENT_DB = PROJECT_ROOT / "data" / "procurement.db"

@st.cache_data(show_spinner=False)
def _load_masters() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    マスターデータを読み込む。
    procurement.db があればSQLiteから、なければCSVフォールバック。
    """
    import sqlite3 as _sqlite3
    if PROCUREMENT_DB.exists():
        try:
            conn = _sqlite3.connect(str(PROCUREMENT_DB))
            tables_q = "SELECT name FROM sqlite_master WHERE type='table'"
            tables = [r[0] for r in conn.execute(tables_q).fetchall()]
            df_po  = pd.read_sql_query("SELECT * FROM po_transactions", conn) if "po_transactions" in tables else pd.DataFrame()
            df_sup = pd.read_sql_query("SELECT * FROM suppliers_master", conn) if "suppliers_master" in tables else pd.DataFrame()
            df_emp = pd.read_sql_query("SELECT * FROM employee_master",  conn) if "employee_master"  in tables else pd.DataFrame()
            conn.close()
            if not df_po.empty:
                return df_po, df_sup, df_emp
        except Exception:
            pass

    # フォールバック: CSV直読み
    po_file  = sorted(DATA_DIR.glob("po_transactions*.csv"))
    sup_file = sorted(DATA_DIR.glob("suppliers_master*.csv"))
    emp_file = sorted(DATA_DIR.glob("employee_master*.csv"))
    df_po  = pd.read_csv(po_file[-1],  encoding="utf-8-sig") if po_file  else pd.DataFrame()
    df_sup = pd.read_csv(sup_file[-1], encoding="utf-8-sig") if sup_file else pd.DataFrame()
    df_emp = pd.read_csv(emp_file[-1], encoding="utf-8-sig") if emp_file else pd.DataFrame()
    return df_po, df_sup, df_emp

df_po, df_sup, df_emp = _load_masters()

# ── カテゴリ選択肢 ──────────────────────────────────────────────────────────
cat_large_opts: list[str] = []
cat_mid_map:   dict[str, list[str]] = {}
cat_small_map: dict[str, list[str]] = {}
if "item_cat_l_name" in df_po.columns and "item_cat_m_name" in df_po.columns:
    cat_large_opts = sorted(df_po["item_cat_l_name"].dropna().unique().tolist())
    for large, grp in df_po.groupby("item_cat_l_name", observed=True):
        cat_mid_map[large] = sorted(grp["item_cat_m_name"].dropna().unique().tolist())
        if "item_cat_s_name" in df_po.columns:
            for mid, grp2 in grp.groupby("item_cat_m_name", observed=True):
                cat_small_map[mid] = sorted(grp2["item_cat_s_name"].dropna().unique().tolist())

# ── カテゴリ→サプライヤーマッピング（PO実績ベース）────────────────────────
cat_sup_map:       dict[tuple[str, str], list[str]] = {}
cat_sup_map_large: dict[str, list[str]]             = {}
sup_col = "supplier_parent_name"
if sup_col in df_po.columns and "item_cat_l_name" in df_po.columns and "item_cat_m_name" in df_po.columns:
    for (l, m), grp in df_po.groupby(["item_cat_l_name", "item_cat_m_name"], observed=True):
        cat_sup_map[(str(l), str(m))] = sorted(grp[sup_col].dropna().unique().tolist())
    for l, grp in df_po.groupby("item_cat_l_name", observed=True):
        cat_sup_map_large[str(l)] = sorted(grp[sup_col].dropna().unique().tolist())

all_supplier_opts: list[str] = []
if sup_col in df_sup.columns:
    all_supplier_opts = sorted(df_sup[sup_col].dropna().unique().tolist())
elif sup_col in df_po.columns:
    all_supplier_opts = sorted(df_po[sup_col].dropna().unique().tolist())

# ── 従業員マスター選択肢 ───────────────────────────────────────────────────
def _emp_label(row: pd.Series) -> str:
    return f"{row['employee_id']} - {row['employee_name']} ({row.get('department', '')})"

emp_buyer_opts:     list[str] = []
emp_requester_opts: list[str] = []
emp_all_opts:       list[str] = []
emp_label_to_name:  dict[str, str] = {}
emp_label_to_id:    dict[str, str] = {}

if not df_emp.empty and "employee_name" in df_emp.columns:
    active_emp = df_emp if "active" not in df_emp.columns else df_emp[df_emp["active"].astype(str).str.lower() == "true"]
    for _, row in active_emp.iterrows():
        label = _emp_label(row)
        emp_all_opts.append(label)
        emp_label_to_name[label] = str(row["employee_name"])
        emp_label_to_id[label]   = str(row["employee_id"])
        role = str(row.get("rfq_role", ""))
        if role == "Buyer":
            emp_buyer_opts.append(label)
        elif role == "Requester":
            emp_requester_opts.append(label)


# ---------------------------------------------------------------------------
# 承認ルート自動生成
# ---------------------------------------------------------------------------
def build_approval_route(budget: float | None, requester_emp_id: str, df_emp: pd.DataFrame) -> list[dict]:
    """予算とRequesterのIDから承認ルートを自動生成"""
    if df_emp.empty:
        return []

    emp_dict = df_emp.set_index("employee_id").to_dict("index")

    # 必要な承認レベル
    if budget is None or budget <= 100_000:
        required_level, level_label = "Manager", "課長"
    elif budget <= 1_000_000:
        required_level, level_label = "Director", "部長"
    else:
        required_level, level_label = "Exec", "役員"
    required_rank = LEVEL_ORDER.get(required_level, 3)

    steps: list[dict] = []

    # Step 1: Requester 起案確認
    req_info = emp_dict.get(requester_emp_id, {})
    steps.append({
        "step_order": 1,
        "approver_role": "Requester確認",
        "approver_level": req_info.get("job_level", ""),
        "approver_employee_id": requester_emp_id,
        "approver_name": req_info.get("employee_name", ""),
        "department": req_info.get("department", ""),
        "required_level": "起案確認",
    })

    # Step 2: Requester上長（必要レベル以上の管理職を探す）
    current_id = requester_emp_id
    visited: set[str] = set()
    found_manager: tuple[str, dict] | None = None
    while current_id and current_id not in visited:
        visited.add(current_id)
        emp = emp_dict.get(current_id, {})
        mgr_id = emp.get("manager_employee_id")
        if not mgr_id or str(mgr_id) == "nan":
            break
        mgr_id = str(mgr_id)
        mgr = emp_dict.get(mgr_id, {})
        mgr_level = mgr.get("job_level", "")
        if LEVEL_ORDER.get(mgr_level, 0) >= required_rank:
            found_manager = (mgr_id, mgr)
            break
        current_id = mgr_id

    if found_manager:
        mgr_id_str, mgr_info = found_manager
        steps.append({
            "step_order": 2,
            "approver_role": f"上長承認（{level_label}）",
            "approver_level": mgr_info.get("job_level", ""),
            "approver_employee_id": mgr_id_str,
            "approver_name": mgr_info.get("employee_name", ""),
            "department": mgr_info.get("department", ""),
            "required_level": level_label,
        })

    # Step 3: Procurement Finance
    if not df_emp.empty and "department" in df_emp.columns and "rfq_role" in df_emp.columns:
        finance_approvers = df_emp[
            (df_emp["department"] == "Finance") & (df_emp["rfq_role"] == "Approver")
        ]
        if not finance_approvers.empty:
            fa = finance_approvers.iloc[0]
            steps.append({
                "step_order": 3,
                "approver_role": "Procurement Finance",
                "approver_level": str(fa.get("job_level", "")),
                "approver_employee_id": str(fa["employee_id"]),
                "approver_name": str(fa["employee_name"]),
                "department": str(fa["department"]),
                "required_level": "Finance承認",
            })

    return steps


# ---------------------------------------------------------------------------
# Sidebar — ロール選択
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📋 RFQ System")
    st.markdown("---")

    current_role = st.selectbox(
        "ロール",
        ROLES,
        index=0,
        key="current_role",
        help="PoCのため認証なしでロールを切り替えます",
    )
    _role_emp_map = {
        "Buyer": emp_buyer_opts or emp_all_opts,
        "Requester": emp_requester_opts or emp_all_opts,
        "Approver": emp_all_opts,
        "Admin": emp_all_opts,
    }
    _emp_opts_for_role = _role_emp_map.get(current_role, emp_all_opts)
    current_user_label = st.selectbox(
        "ユーザー",
        _emp_opts_for_role,
        key="current_user_label",
        help="従業員マスターから選択",
    )
    current_user    = emp_label_to_name.get(current_user_label, current_user_label)
    current_user_id = emp_label_to_id.get(current_user_label, "")

    st.markdown("---")
    st.markdown(f"**テナント**: Demo Company")
    st.markdown(f"**ロール**: `{current_role}`")

    st.markdown("---")
    if st.button("💡 Spend Analytics を開く", use_container_width=True):
        st.info("別タブで http://localhost:8501 を開いてください")

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
TAB_DASHBOARD = "📊 ダッシュボード"
TAB_NEW_RFQ   = "➕ RFQ作成"
TAB_RFQ_LIST  = "📋 案件一覧"
TAB_DETAIL    = "🔍 案件詳細"

tab_dashboard, tab_new_rfq, tab_rfq_list, tab_detail = st.tabs(
    [TAB_DASHBOARD, TAB_NEW_RFQ, TAB_RFQ_LIST, TAB_DETAIL]
)

# ===========================================================================
# Tab 1: Dashboard
# ===========================================================================
with tab_dashboard:
    st.header("調達ダッシュボード")

    kpi = get_dashboard_kpis(tenant_id=1)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("RFQ総数", kpi["total"])
    c2.metric("進行中", kpi["active"])
    c3.metric("未回収見積", kpi["pending_quotes"])
    c4.metric("承認待ち", kpi["pending_approval"])
    c5.metric("Draft", kpi["draft"])

    st.markdown("---")

    rfq_list = get_rfq_list(tenant_id=1)
    if rfq_list:
        df_rfq = pd.DataFrame(rfq_list)

        col_chart, col_table = st.columns([1, 2])
        with col_chart:
            st.subheader("ステータス別")
            status_cnt = df_rfq["status"].value_counts().reset_index()
            status_cnt.columns = ["status", "count"]
            colors = [STATUS_COLOR.get(s, "#9e9e9e") for s in status_cnt["status"]]
            fig_pie = go.Figure(go.Pie(
                labels=status_cnt["status"],
                values=status_cnt["count"],
                marker_colors=colors,
                textinfo="label+value",
                hole=0.4,
            ))
            fig_pie.update_layout(height=280, margin={"t": 0, "b": 0, "l": 0, "r": 0}, showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_table:
            st.subheader("最近の案件")
            display_cols = ["rfq_id", "project_name", "commodity_mid", "buyer", "deadline", "status", "supplier_count", "quote_count"]
            display_cols = [c for c in display_cols if c in df_rfq.columns]
            df_display = df_rfq[display_cols].head(10).copy()
            rename_map = {
                "rfq_id": "RFQ ID", "project_name": "案件名", "commodity_mid": "中分類",
                "buyer": "担当", "deadline": "期限", "status": "ステータス",
                "supplier_count": "サプライヤ数", "quote_count": "見積数",
            }
            df_display.columns = [rename_map.get(c, c) for c in display_cols]
            st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("案件がまだありません。「RFQ作成」タブから最初の案件を作成してください。")
        demo_data = pd.DataFrame({"status": STATUS_LIST, "count": [3, 5, 4, 2, 1, 8]})
        fig_demo = px.bar(demo_data, x="status", y="count", color="status",
                          color_discrete_map=STATUS_COLOR,
                          labels={"status": "ステータス", "count": "件数"})
        fig_demo.update_layout(height=280, showlegend=False)
        st.plotly_chart(fig_demo, use_container_width=True)

# ===========================================================================
# Tab 2: RFQ作成（起案）
# ===========================================================================
with tab_new_rfq:
    st.header("新規RFQ作成（起案）")

    if current_role not in ("Buyer", "Admin"):
        st.warning(f"RFQ作成は Buyer または Admin のみ可能です（現在: {current_role}）")
    else:
        # ── ① 案件基本情報 ────────────────────────────────────────────────
        st.subheader("① 案件基本情報")
        col1, col2 = st.columns(2)
        with col1:
            project_name = st.text_input("案件名 *", placeholder="例: 梱包材 2025年度一括調達", key="f_project_name")
            buyer_label = st.selectbox(
                "購買担当者 (Buyer) *",
                emp_buyer_opts or emp_all_opts,
                key="f_buyer",
                help="従業員マスター (rfq_role=Buyer) から選択",
            )
            buyer = emp_label_to_name.get(buyer_label, buyer_label)
            budget = st.number_input("予算上限 (円)", min_value=0, value=0, step=100_000, key="f_budget",
                                     help="10万円以下→2社見積可、超える場合→3社必須")

            # 予算連動で必要見積社数を表示
            req_count = calc_required_quote_count(float(budget) if budget > 0 else None)
            if budget > 0:
                if budget <= 100_000:
                    st.info(f"📌 予算 ¥{budget:,.0f} → **{req_count}社見積**で可（10万円以下）")
                else:
                    st.warning(f"📌 予算 ¥{budget:,.0f} → **{req_count}社見積**が必須です")
            else:
                st.caption(f"📌 予算未入力の場合: {req_count}社見積が必要です")

        with col2:
            req_label = st.selectbox(
                "依頼部門担当者 (Requester)",
                ["（未選択）"] + (emp_requester_opts or emp_all_opts),
                key="f_requester",
                help="従業員マスター (rfq_role=Requester) から選択",
            )
            requester      = emp_label_to_name.get(req_label, "") if req_label != "（未選択）" else ""
            requester_id   = emp_label_to_id.get(req_label, "")   if req_label != "（未選択）" else ""
            deadline       = st.date_input("見積回答期限 *", key="f_deadline",
                                           help="送信日から通常14日")
            delivery_date  = st.date_input("希望納期", key="f_delivery_date")
            delivery_site  = st.text_input("希望納入先（事業所/拠点）", key="f_delivery_site",
                                           placeholder="例: 東京HQ / 大阪工場")

        purpose     = st.text_area("目的・背景 *", height=70, key="f_purpose",
                                   placeholder="例: 旧製品の代替品調達。2025年Q2以降の生産ラインに必要。")
        description = st.text_area("追加説明・仕様補足", height=60, key="f_desc")

        # ── ② カテゴリ ──────────────────────────────────────────────────
        st.subheader("② カテゴリ（コモディティ分類）")
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            sel_large = st.selectbox("大分類", [""] + cat_large_opts, key="f_large")
        with col_c2:
            mid_opts  = cat_mid_map.get(sel_large, []) if sel_large else []
            sel_mid   = st.selectbox("中分類", [""] + mid_opts, key="f_mid")
        with col_c3:
            small_opts = cat_small_map.get(sel_mid, []) if sel_mid else []
            sel_small  = st.selectbox("小分類", [""] + small_opts, key="f_small")

        # ── ③ サプライヤー選定 ──────────────────────────────────────────
        st.subheader("③ 候補サプライヤー選定")
        if sel_large and sel_mid:
            filtered_sups = cat_sup_map.get((sel_large, sel_mid), all_supplier_opts)
            st.caption(f"📦 **{sel_large} / {sel_mid}** のPO実績サプライヤー: {len(filtered_sups)} 社")
        elif sel_large:
            filtered_sups = cat_sup_map_large.get(sel_large, all_supplier_opts)
            st.caption(f"📦 **{sel_large}** のPO実績サプライヤー: {len(filtered_sups)} 社")
        else:
            filtered_sups = all_supplier_opts
            st.caption(f"📦 全サプライヤー: {len(filtered_sups)} 社（カテゴリを選択すると絞り込まれます）")

        selected_suppliers = st.multiselect(
            f"招待するサプライヤー（{req_count}社{'以上' if req_count > 2 else ''}選択）",
            options=filtered_sups,
            key="f_suppliers",
        )
        n_sel = len(selected_suppliers)
        if n_sel < req_count:
            st.warning(f"⚠ {req_count}社必要ですが、現在 {n_sel} 社選択中")
        else:
            st.success(f"✅ {n_sel} 社選択済（必要: {req_count}社）")

        # ── ④ 添付書類 ────────────────────────────────────────────────
        st.subheader("④ 添付書類")
        col_doc1, col_doc2, col_doc3 = st.columns(3)
        with col_doc1:
            spec_file = st.file_uploader(
                "仕様書 *（PDF推奨）",
                type=["pdf", "docx", "xlsx", "png", "jpg"],
                key="f_spec",
            )
            if spec_file:
                st.success(f"✅ {spec_file.name}")
        with col_doc2:
            st.markdown("**NDA**")
            st.success("✅ 自動添付（全案件に自動付与）")
        with col_doc3:
            st.markdown("**見積明細フォーマット**")
            if sel_mid:
                st.success(f"✅ 自動生成（{sel_mid}用）")
            else:
                st.caption("中分類を選択すると自動生成されます")

        st.markdown("---")

        # ── 承認ルートプレビュー ────────────────────────────────────────
        if requester_id and budget > 0:
            with st.expander("🔐 承認ルートプレビュー（自動算出）", expanded=False):
                preview_steps = build_approval_route(float(budget), requester_id, df_emp)
                for s in preview_steps:
                    st.markdown(
                        f"**Step {s['step_order']}** — {s['approver_role']}:  "
                        f"``{s['approver_name']}`` ({s['approver_level']} / {s['department']})"
                    )

        # ── 提出ボタン ──────────────────────────────────────────────────
        if st.button("RFQを起案する", type="primary", use_container_width=True, key="f_submit"):
            errors = []
            if not project_name:
                errors.append("案件名は必須です")
            if not buyer:
                errors.append("購買担当者は必須です")
            if not purpose:
                errors.append("目的・背景は必須です")
            if n_sel < req_count:
                errors.append(f"サプライヤーを {req_count} 社以上選択してください（現在 {n_sel} 社）")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                rfq_data = {
                    "project_name": project_name,
                    "commodity_large": sel_large or None,
                    "commodity_mid": sel_mid or None,
                    "commodity_small": sel_small or None,
                    "buyer": buyer,
                    "requester": requester or None,
                    "budget": float(budget) if budget > 0 else None,
                    "delivery_site": delivery_site or None,
                    "delivery_date": str(delivery_date) if delivery_date else None,
                    "deadline": str(deadline),
                    "status": "Draft",
                    "description": description or None,
                    "purpose": purpose or None,
                    "spec_uploaded": 1 if spec_file else 0,
                    "template_attached": 1 if sel_mid else 0,
                }
                rfq_id = create_rfq(rfq_data)
                add_rfq_suppliers(rfq_id, selected_suppliers)

                # 承認ルート自動生成
                if requester_id:
                    approval_steps = build_approval_route(float(budget) if budget > 0 else None, requester_id, df_emp)
                    if approval_steps:
                        create_approval_route(rfq_id, approval_steps)

                log_action(
                    action="RFQ_CREATED",
                    entity="rfq_projects",
                    entity_id=rfq_id,
                    user_name=current_user,
                    user_role=current_role,
                    detail=f"案件名: {project_name}, サプライヤ: {n_sel}社, 予算: {budget:,.0f}円",
                )
                st.success(f"✅ RFQ起案完了: **{rfq_id}** — 「案件詳細」タブで確認・展開できます")
                st.balloons()

# ===========================================================================
# Tab 3: RFQ一覧
# ===========================================================================
with tab_rfq_list:
    st.header("案件一覧")

    rfq_list = get_rfq_list(tenant_id=1)

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        filter_status = st.multiselect("ステータス絞込", STATUS_LIST, default=[], key="list_status")
    with col_f2:
        filter_buyer = st.text_input("担当者で絞込", key="list_buyer")
    with col_f3:
        st.markdown("　")
        if st.button("🔄 更新", use_container_width=True, key="list_refresh"):
            st.rerun()

    if rfq_list:
        df_rfq = pd.DataFrame(rfq_list)
        if filter_status:
            df_rfq = df_rfq[df_rfq["status"].isin(filter_status)]
        if filter_buyer:
            df_rfq = df_rfq[df_rfq["buyer"].str.contains(filter_buyer, na=False)]

        st.markdown(f"**{len(df_rfq)} 件**")

        for _, row in df_rfq.iterrows():
            color = STATUS_COLOR.get(row.get("status", ""), "#9e9e9e")
            with st.container(border=True):
                r1, r2, r3 = st.columns([3, 2, 1])
                with r1:
                    st.markdown(f"**{row['rfq_id']}** — {row['project_name']}")
                    cat_str = " / ".join(filter(None, [
                        row.get("commodity_large"), row.get("commodity_mid"), row.get("commodity_small")
                    ]))
                    if cat_str:
                        st.caption(f"📦 {cat_str}")
                with r2:
                    budget_str = f"¥{row['budget']:,.0f}" if row.get("budget") else "未設定"
                    st.caption(f"👤 {row.get('buyer', '')}　　💰 {budget_str}")
                    st.caption(f"🏭 サプライヤ {row.get('supplier_count', 0)}社　　⏰ 期限: {row.get('deadline', '')}")
                with r3:
                    st.markdown(
                        f"<span style='background:{color};color:white;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.85em'>{row.get('status','')}</span>",
                        unsafe_allow_html=True,
                    )
    else:
        st.info("案件がありません。「RFQ作成」タブから作成してください。")

# ===========================================================================
# Tab 4: 案件詳細（サブタブ構成）
# ===========================================================================
with tab_detail:
    st.header("案件詳細")

    rfq_list_for_select = get_rfq_list(tenant_id=1)
    if not rfq_list_for_select:
        st.info("案件がありません。")
    else:
        rfq_options = {f"{r['rfq_id']} — {r['project_name']}": r["rfq_id"] for r in rfq_list_for_select}
        selected_label = st.selectbox("案件を選択", list(rfq_options.keys()), key="detail_select")
        selected_rfq_id = rfq_options[selected_label]
        rfq       = get_rfq(selected_rfq_id)
        suppliers = get_rfq_suppliers(selected_rfq_id)

        if not rfq:
            st.error("案件データが取得できません")
        else:
            # ── ステータスバッジ ──────────────────────────────────────────
            color = STATUS_COLOR.get(rfq["status"], "#9e9e9e")
            st.markdown(
                f"<span style='background:{color};color:white;padding:4px 14px;"
                f"border-radius:14px;font-size:1em;font-weight:bold'>{rfq['status']}</span>",
                unsafe_allow_html=True,
            )
            st.markdown("")

            # ── サブタブ ──────────────────────────────────────────────────
            sub_info, sub_buyer, sub_tracking, sub_qcjdm, sub_approval = st.tabs([
                "📋 基本情報",
                "✅ バイヤーチェック & 展開",
                "📬 見積トラッキング",
                "⭐ QCJDM評価",
                "🔐 承認ルート",
            ])

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # サブタブ 1: 基本情報
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            with sub_info:
                st.subheader(rfq["project_name"])
                d1, d2, d3, d4 = st.columns(4)
                d1.metric("予算", f"¥{rfq['budget']:,.0f}" if rfq.get("budget") else "未設定")
                d2.metric("回答期限", rfq.get("deadline") or "未設定")
                d3.metric("希望納期", rfq.get("delivery_date") or "未設定")
                d4.metric("必要見積社数", rfq.get("required_quote_count", 3))

                st.markdown(f"**希望納入先**: {rfq.get('delivery_site') or '未設定'}")
                st.markdown(f"**カテゴリ**: {rfq.get('commodity_large','')} / {rfq.get('commodity_mid','')} / {rfq.get('commodity_small','')}")
                st.markdown(f"**購買担当**: {rfq.get('buyer','')}　　**起案者**: {rfq.get('requester','')}")

                if rfq.get("purpose"):
                    st.markdown("**目的・背景**")
                    st.info(rfq["purpose"])
                if rfq.get("description"):
                    st.markdown("**追加説明**")
                    st.caption(rfq["description"])

                # 添付書類状況
                st.markdown("**添付書類状況**")
                dc1, dc2, dc3 = st.columns(3)
                dc1.markdown("✅ NDA 自動添付済" if rfq.get("nda_attached") else "❌ NDA 未添付")
                dc2.markdown("✅ 仕様書 アップロード済" if rfq.get("spec_uploaded") else "⚠ 仕様書 未アップロード")
                dc3.markdown("✅ 見積テンプレ 添付済" if rfq.get("template_attached") else "⚠ 見積テンプレ 未添付")

                # 招待サプライヤー
                st.markdown("---")
                st.subheader(f"招待サプライヤー ({len(suppliers)}社)")
                if suppliers:
                    df_sup_d = pd.DataFrame(suppliers)[["supplier_name", "invitation_date", "response_status"]]
                    df_sup_d.columns = ["サプライヤー名", "招待日", "回答状況"]
                    st.dataframe(df_sup_d, use_container_width=True, hide_index=True)
                else:
                    st.caption("サプライヤーが登録されていません")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # サブタブ 2: バイヤーチェック & 展開
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            with sub_buyer:
                st.subheader("バイヤー確認チェックリスト（配信前）")

                req_count_rfq = rfq.get("required_quote_count", 3)
                n_suppliers   = len(suppliers)

                checks = {
                    f"候補サプライヤー {req_count_rfq}社 選定済": n_suppliers >= req_count_rfq,
                    "仕様書 アップロード済": bool(rfq.get("spec_uploaded")),
                    "NDA 自動添付済": bool(rfq.get("nda_attached")),
                    "見積明細フォーマット 添付済": bool(rfq.get("template_attached")),
                }
                all_ok = all(checks.values())
                for label, ok in checks.items():
                    icon = "✅" if ok else "❌"
                    st.markdown(f"{icon} {label}")

                st.markdown("---")
                already_dispatched = bool(rfq.get("dispatched_at"))

                if already_dispatched:
                    st.success(f"✅ 展開済み — {rfq.get('dispatched_at')}")
                    st.caption(f"ステータス: {rfq['status']}")
                elif current_role in ("Buyer", "Admin"):
                    if not all_ok:
                        st.warning("上記チェックを全て満たすと展開ボタンが有効になります")
                    dispatch_btn = st.button(
                        "🚀 展開ボタン（RFPをサプライヤーへ一斉送信）",
                        type="primary",
                        disabled=not all_ok,
                        use_container_width=True,
                        key="dispatch_btn",
                    )
                    if dispatch_btn:
                        dispatch_rfq(selected_rfq_id)
                        log_action("RFQ_DISPATCHED", "rfq_projects", selected_rfq_id,
                                   current_user, current_role,
                                   f"{n_suppliers}社へRFP送信")
                        st.success(f"✅ {n_suppliers}社へRFPを送信しました！ステータスを「RFQ送信」に更新")
                        st.rerun()
                else:
                    st.caption("展開はBuyer/Adminのみ可能です")

                # ステータス手動変更（Buyer/Admin用）
                if current_role in ("Buyer", "Admin"):
                    st.markdown("---")
                    st.subheader("ステータス変更")
                    new_status = st.selectbox(
                        "新ステータス", STATUS_LIST,
                        index=STATUS_LIST.index(rfq["status"]) if rfq["status"] in STATUS_LIST else 0,
                        key="detail_status",
                    )
                    if st.button("更新", key="detail_status_btn"):
                        update_rfq_status(selected_rfq_id, new_status)
                        log_action("STATUS_UPDATED", "rfq_projects", selected_rfq_id,
                                   current_user, current_role, f"{rfq['status']} → {new_status}")
                        st.success(f"ステータスを「{new_status}」に変更しました")
                        st.rerun()

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # サブタブ 3: 見積トラッキング
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            with sub_tracking:
                st.subheader("見積回収トラッキング")

                dispatched_at = rfq.get("dispatched_at")
                deadline_str  = rfq.get("deadline")

                if not dispatched_at:
                    st.info("まだRFPを展開していません。「バイヤーチェック & 展開」タブから展開してください。")
                else:
                    st.markdown(f"**送信日**: {dispatched_at[:10]}　　**提出期限**: {deadline_str}　（送信から14日以内）")

                    if suppliers:
                        st.markdown("---")
                        for sup in suppliers:
                            sid   = sup["id"]
                            sname = sup["supplier_name"]
                            rstatus = sup.get("response_status", "Pending")
                            color_map = {
                                "Pending": "#ff9800", "受領済": "#4caf50",
                                "要修正": "#f44336", "辞退": "#9e9e9e",
                            }
                            badge_color = color_map.get(rstatus, "#9e9e9e")

                            with st.container(border=True):
                                sc1, sc2, sc3 = st.columns([3, 2, 2])
                                with sc1:
                                    st.markdown(f"**{sname}**")
                                    st.markdown(
                                        f"<span style='background:{badge_color};color:white;"
                                        f"padding:2px 8px;border-radius:8px;font-size:0.8em'>{rstatus}</span>",
                                        unsafe_allow_html=True,
                                    )
                                with sc2:
                                    st.caption(f"招待日: {sup.get('invitation_date','')}")
                                with sc3:
                                    if current_role in ("Buyer", "Admin"):
                                        new_rs = st.selectbox(
                                            "状況更新",
                                            RESPONSE_STATUS_OPTS,
                                            index=RESPONSE_STATUS_OPTS.index(rstatus) if rstatus in RESPONSE_STATUS_OPTS else 0,
                                            key=f"rs_{sid}",
                                        )
                                        if st.button("更新", key=f"rs_btn_{sid}"):
                                            update_supplier_response(sid, new_rs)
                                            log_action("RESPONSE_UPDATED", "rfq_suppliers", str(sid),
                                                       current_user, current_role, f"{sname}: {rstatus}→{new_rs}")
                                            st.rerun()
                    else:
                        st.caption("サプライヤーが登録されていません")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # サブタブ 4: QCJDM評価
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            with sub_qcjdm:
                st.subheader("QCJDM評価（5段階: 1=最低 / 5=最高）")
                st.caption("⚠ いずれかの評価が **1点** の場合、当該サプライヤーは提案不可（ゲーティング除外）となります")

                if not suppliers:
                    st.info("サプライヤーが登録されていません")
                else:
                    existing_evals = {e["supplier_name"]: e for e in get_evaluations(selected_rfq_id)}

                    for sup in suppliers:
                        sname = sup["supplier_name"]
                        ev    = existing_evals.get(sname, {})
                        is_gated = ev.get("is_gated_out", 0)

                        header_color = "#f44336" if is_gated else "#1976d2"
                        gated_label  = " 🚫 ゲーティング除外" if is_gated else ""
                        st.markdown(
                            f"<div style='background:{header_color};color:white;padding:6px 12px;"
                            f"border-radius:6px;font-weight:bold;margin:10px 0 4px'>"
                            f"{sname}{gated_label}</div>",
                            unsafe_allow_html=True,
                        )

                        can_eval = current_role in ("Buyer", "Requester", "Admin")
                        sc1, sc2, sc3, sc4, sc5 = st.columns(5)

                        with sc1:
                            cost_val = ev.get("cost_score") or 3
                            # Cost は系統自動（見積金額から算出）→ここでは手動入力でデモ
                            cost_s = st.selectbox(
                                "C: コスト（自動）",
                                [1, 2, 3, 4, 5],
                                index=cost_val - 1,
                                key=f"cost_{sname}",
                                disabled=not can_eval,
                                help="見積金額から自動スコアリング（現在はデモ手動入力）",
                            )
                        with sc2:
                            q_val = ev.get("quality_score") or 3
                            q_s = st.selectbox("Q: 品質", [1, 2, 3, 4, 5], index=q_val - 1,
                                               key=f"q_{sname}", disabled=not can_eval)
                        with sc3:
                            j_val = ev.get("job_score") or 3
                            j_s = st.selectbox("J: 対応力", [1, 2, 3, 4, 5], index=j_val - 1,
                                               key=f"j_{sname}", disabled=not can_eval)
                        with sc4:
                            d_val = ev.get("dev_score") or 3
                            d_s = st.selectbox("D: 開発力", [1, 2, 3, 4, 5], index=d_val - 1,
                                               key=f"d_{sname}", disabled=not can_eval)
                        with sc5:
                            m_val = ev.get("mgmt_score") or 3
                            m_s = st.selectbox("M: 管理力", [1, 2, 3, 4, 5], index=m_val - 1,
                                               key=f"m_{sname}", disabled=not can_eval)

                        comment = st.text_input(
                            "コメント",
                            value=ev.get("comment", ""),
                            key=f"ev_comment_{sname}",
                            disabled=not can_eval,
                        )

                        if can_eval:
                            if st.button(f"評価を保存（{sname}）", key=f"ev_save_{sname}"):
                                scores = {
                                    "cost_score": cost_s, "quality_score": q_s,
                                    "job_score": j_s, "dev_score": d_s,
                                    "mgmt_score": m_s, "comment": comment,
                                }
                                upsert_evaluation(selected_rfq_id, sname, scores, current_user)
                                log_action("QCJDM_SAVED", "evaluations", selected_rfq_id,
                                           current_user, current_role, f"{sname}: QCJDM={cost_s}/{q_s}/{j_s}/{d_s}/{m_s}")
                                st.success(f"✅ {sname} の評価を保存しました")
                                st.rerun()

                    # 評価サマリ
                    evals = get_evaluations(selected_rfq_id)
                    if evals:
                        st.markdown("---")
                        st.subheader("評価サマリ")
                        df_ev = pd.DataFrame(evals)[[
                            "supplier_name", "cost_score", "quality_score", "job_score",
                            "dev_score", "mgmt_score", "total_score", "is_gated_out"
                        ]].copy()
                        df_ev.columns = ["サプライヤー", "C(コスト)", "Q(品質)", "J(対応)", "D(開発)", "M(管理)", "平均", "除外"]
                        df_ev["除外"] = df_ev["除外"].map({0: "", 1: "🚫 除外"})
                        st.dataframe(df_ev, use_container_width=True, hide_index=True)

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # サブタブ 5: 承認ルート
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            with sub_approval:
                st.subheader("承認ルート")

                budget_val = rfq.get("budget")
                if budget_val:
                    if budget_val <= 100_000:
                        st.caption(f"予算 ¥{budget_val:,.0f} → 課長承認ルート")
                    elif budget_val <= 1_000_000:
                        st.caption(f"予算 ¥{budget_val:,.0f} → 部長承認ルート")
                    else:
                        st.caption(f"予算 ¥{budget_val:,.0f} → 役員承認ルート")

                approval_steps = get_approval_route(selected_rfq_id)

                # 承認ルートが未生成の場合は再生成ボタン
                if not approval_steps and current_role in ("Buyer", "Admin"):
                    requester_name = rfq.get("requester", "")
                    req_row = df_emp[df_emp["employee_name"] == requester_name] if not df_emp.empty else pd.DataFrame()
                    if st.button("🔁 承認ルートを自動生成", key="regen_approval"):
                        if not req_row.empty:
                            req_id = str(req_row.iloc[0]["employee_id"])
                            steps = build_approval_route(budget_val, req_id, df_emp)
                            create_approval_route(selected_rfq_id, steps)
                            log_action("APPROVAL_ROUTE_CREATED", "approvals", selected_rfq_id,
                                       current_user, current_role, f"{len(steps)}ステップ")
                            st.rerun()
                        else:
                            st.warning("起案者の従業員情報が見つかりません")

                if approval_steps:
                    status_map_approval = {
                        "Pending": ("⏳", "#ff9800"),
                        "Approved": ("✅", "#4caf50"),
                        "Rejected": ("❌", "#f44336"),
                    }
                    for step in approval_steps:
                        icon, badge_col = status_map_approval.get(step["status"], ("⏳", "#9e9e9e"))
                        with st.container(border=True):
                            ac1, ac2, ac3 = st.columns([1, 4, 3])
                            with ac1:
                                st.markdown(f"**Step {step['step_order']}**")
                                st.markdown(
                                    f"<span style='background:{badge_col};color:white;"
                                    f"padding:2px 8px;border-radius:6px;font-size:0.8em'>{icon} {step['status']}</span>",
                                    unsafe_allow_html=True,
                                )
                            with ac2:
                                st.markdown(f"**{step['approver_role']}**")
                                st.caption(f"承認者: {step.get('approver_name','')}  ({step.get('approver_level','')} / {step.get('department','')})")
                                if step.get("comment"):
                                    st.caption(f"コメント: {step['comment']}")
                            with ac3:
                                # 現在のユーザーが承認者の場合は承認/却下ボタン
                                is_my_step = (
                                    step["status"] == "Pending"
                                    and current_role == "Approver"
                                    and (
                                        step.get("approver_name") == current_user
                                        or step.get("approver_employee_id") == current_user_id
                                    )
                                )
                                if is_my_step:
                                    comment_key = f"ap_comment_{step['id']}"
                                    ap_comment = st.text_input("コメント（任意）", key=comment_key)
                                    col_ap, col_rj = st.columns(2)
                                    with col_ap:
                                        if st.button("✅ 承認", key=f"ap_ok_{step['id']}", type="primary"):
                                            update_approval_status(step["id"], "Approved", ap_comment)
                                            log_action("APPROVAL_APPROVED", "approvals", selected_rfq_id,
                                                       current_user, current_role, f"Step {step['step_order']}")
                                            st.rerun()
                                    with col_rj:
                                        if st.button("❌ 却下", key=f"ap_ng_{step['id']}"):
                                            update_approval_status(step["id"], "Rejected", ap_comment)
                                            log_action("APPROVAL_REJECTED", "approvals", selected_rfq_id,
                                                       current_user, current_role, f"Step {step['step_order']}")
                                            st.rerun()
                                else:
                                    if step.get("decided_at"):
                                        st.caption(f"決裁日: {step['decided_at'][:10]}")
                else:
                    st.info("承認ルートが設定されていません。（RFQ作成時に起案者を選択すると自動生成されます）")
