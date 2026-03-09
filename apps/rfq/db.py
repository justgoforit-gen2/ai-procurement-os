"""
db.py -- SQLite database setup and CRUD for RFQ Workflow System.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parents[2] / "data" / "rfq.db"

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- 見積テンプレート項目（中分類/小分類ごと）
CREATE TABLE IF NOT EXISTS quote_template_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    commodity_mid   TEXT    NOT NULL,
    commodity_small TEXT,
    item_name       TEXT    NOT NULL,
    uom             TEXT,
    sort_order      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rfq_projects (
    rfq_id              TEXT    PRIMARY KEY,
    tenant_id           INTEGER NOT NULL DEFAULT 1,
    project_name        TEXT    NOT NULL,
    commodity_large     TEXT,
    commodity_mid       TEXT,
    commodity_small     TEXT,
    buyer               TEXT,
    requester           TEXT,
    budget              REAL,
    delivery_site       TEXT,
    delivery_date       TEXT,
    deadline            TEXT,
    status              TEXT    NOT NULL DEFAULT 'Draft',
    description         TEXT,
    purpose             TEXT,
    required_quote_count INTEGER DEFAULT 3,
    spec_uploaded       INTEGER DEFAULT 0,
    nda_attached        INTEGER DEFAULT 1,
    template_attached   INTEGER DEFAULT 0,
    dispatched_at       TEXT,
    created_at          TEXT    DEFAULT (datetime('now')),
    updated_at          TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rfq_suppliers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id          TEXT    NOT NULL REFERENCES rfq_projects(rfq_id),
    tenant_id       INTEGER NOT NULL DEFAULT 1,
    supplier_name   TEXT    NOT NULL,
    invitation_date TEXT,
    response_status TEXT    DEFAULT 'Pending',
    created_at      TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quotes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id          TEXT    NOT NULL REFERENCES rfq_projects(rfq_id),
    rfq_supplier_id INTEGER REFERENCES rfq_suppliers(id),
    tenant_id       INTEGER NOT NULL DEFAULT 1,
    supplier_name   TEXT    NOT NULL,
    submitted_at    TEXT,
    total_amount    REAL,
    lead_time_days  INTEGER,
    payment_terms   TEXT,
    status          TEXT    DEFAULT 'Draft',
    note            TEXT,
    created_at      TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quote_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id    INTEGER NOT NULL REFERENCES quotes(id),
    tenant_id   INTEGER NOT NULL DEFAULT 1,
    item_name   TEXT    NOT NULL,
    unit_price  REAL,
    quantity    REAL,
    uom         TEXT,
    lead_time   INTEGER,
    moq         REAL,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS evaluations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id          TEXT    NOT NULL REFERENCES rfq_projects(rfq_id),
    tenant_id       INTEGER NOT NULL DEFAULT 1,
    supplier_name   TEXT    NOT NULL,
    -- QCJDM (5段階: 1〜5, 5が良い)
    cost_score      INTEGER,   -- System自動
    quality_score   INTEGER,   -- Requester入力
    job_score       INTEGER,   -- Requester入力
    dev_score       INTEGER,   -- Requester入力
    mgmt_score      INTEGER,   -- Requester入力
    total_score     REAL,
    is_gated_out    INTEGER DEFAULT 0,  -- 1=いずれかが1点→除外
    comment         TEXT,
    evaluated_by    TEXT,
    evaluated_at    TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS approvals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id              TEXT    NOT NULL REFERENCES rfq_projects(rfq_id),
    tenant_id           INTEGER NOT NULL DEFAULT 1,
    step_order          INTEGER NOT NULL DEFAULT 1,
    approver_role       TEXT    NOT NULL,
    approver_level      TEXT,
    approver_employee_id TEXT,
    approver_name       TEXT,
    department          TEXT,
    required_level      TEXT,
    status              TEXT    DEFAULT 'Pending',
    comment             TEXT,
    decided_at          TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id      TEXT    NOT NULL REFERENCES rfq_projects(rfq_id),
    tenant_id   INTEGER NOT NULL DEFAULT 1,
    doc_type    TEXT    NOT NULL,
    filename    TEXT    NOT NULL,
    file_path   TEXT,
    uploaded_by TEXT,
    uploaded_at TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operation_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER NOT NULL DEFAULT 1,
    user_name   TEXT,
    user_role   TEXT,
    action      TEXT    NOT NULL,
    entity      TEXT,
    entity_id   TEXT,
    detail      TEXT,
    timestamp   TEXT    DEFAULT (datetime('now'))
);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # デフォルトテナント挿入
        conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name) VALUES (1, 'Demo Company')"
        )


# ---------------------------------------------------------------------------
# RFQ Projects
# ---------------------------------------------------------------------------

def generate_rfq_id() -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM rfq_projects").fetchone()
        n = (row["cnt"] or 0) + 1
    return f"RFQ-{datetime.now().strftime('%Y%m')}-{n:04d}"


def calc_required_quote_count(budget: float | None) -> int:
    """予算に基づき必要見積社数を返す (仕様: 10万以下→2社, それ以外→3社)"""
    if budget is not None and budget <= 100_000:
        return 2
    return 3


def create_rfq(data: dict) -> str:
    rfq_id = generate_rfq_id()
    budget = data.get("budget")
    if "required_quote_count" not in data:
        data["required_quote_count"] = calc_required_quote_count(budget)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO rfq_projects
               (rfq_id, tenant_id, project_name, commodity_large, commodity_mid,
                commodity_small, buyer, requester, budget, delivery_site, delivery_date,
                deadline, status, description, purpose,
                required_quote_count, spec_uploaded, nda_attached, template_attached)
               VALUES (:rfq_id, :tenant_id, :project_name, :commodity_large, :commodity_mid,
                       :commodity_small, :buyer, :requester, :budget, :delivery_site, :delivery_date,
                       :deadline, :status, :description, :purpose,
                       :required_quote_count, :spec_uploaded, :nda_attached, :template_attached)""",
            {
                "rfq_id": rfq_id,
                "tenant_id": data.get("tenant_id", 1),
                "project_name": data.get("project_name"),
                "commodity_large": data.get("commodity_large"),
                "commodity_mid": data.get("commodity_mid"),
                "commodity_small": data.get("commodity_small"),
                "buyer": data.get("buyer"),
                "requester": data.get("requester"),
                "budget": data.get("budget"),
                "delivery_site": data.get("delivery_site"),
                "delivery_date": data.get("delivery_date"),
                "deadline": data.get("deadline"),
                "status": data.get("status", "Draft"),
                "description": data.get("description"),
                "purpose": data.get("purpose"),
                "required_quote_count": data.get("required_quote_count", 3),
                "spec_uploaded": int(data.get("spec_uploaded", 0)),
                "nda_attached": 1,
                "template_attached": int(data.get("template_attached", 0)),
            },
        )
    return rfq_id


def get_rfq_list(tenant_id: int = 1) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      COUNT(DISTINCT s.id) AS supplier_count,
                      COUNT(DISTINCT q.id) AS quote_count
               FROM rfq_projects p
               LEFT JOIN rfq_suppliers s ON s.rfq_id = p.rfq_id
               LEFT JOIN quotes q ON q.rfq_id = p.rfq_id AND q.status != 'Draft'
               WHERE p.tenant_id = ?
               GROUP BY p.rfq_id
               ORDER BY p.created_at DESC""",
            (tenant_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_rfq(rfq_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM rfq_projects WHERE rfq_id = ?", (rfq_id,)
        ).fetchone()
    return dict(row) if row else None


def update_rfq_status(rfq_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE rfq_projects SET status = ?, updated_at = datetime('now') WHERE rfq_id = ?",
            (status, rfq_id),
        )


# ---------------------------------------------------------------------------
# RFQ Suppliers
# ---------------------------------------------------------------------------

def add_rfq_suppliers(rfq_id: str, supplier_names: list[str], tenant_id: int = 1) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM rfq_suppliers WHERE rfq_id = ?", (rfq_id,))
        for name in supplier_names:
            conn.execute(
                """INSERT INTO rfq_suppliers (rfq_id, tenant_id, supplier_name, invitation_date)
                   VALUES (?, ?, ?, date('now'))""",
                (rfq_id, tenant_id, name),
            )


def get_rfq_suppliers(rfq_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM rfq_suppliers WHERE rfq_id = ? ORDER BY id",
            (rfq_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Dashboard KPIs
# ---------------------------------------------------------------------------

def get_dashboard_kpis(tenant_id: int = 1) -> dict:
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM rfq_projects WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()[0]

        active = conn.execute(
            """SELECT COUNT(*) FROM rfq_projects
               WHERE tenant_id = ? AND status IN ('RFQ送信', '見積回収中', '評価中', '承認待ち')""",
            (tenant_id,),
        ).fetchone()[0]

        pending_quotes = conn.execute(
            """SELECT COUNT(*) FROM rfq_suppliers s
               JOIN rfq_projects p ON p.rfq_id = s.rfq_id
               WHERE p.tenant_id = ? AND s.response_status = 'Pending'
               AND p.status IN ('RFQ送信', '見積回収中')""",
            (tenant_id,),
        ).fetchone()[0]

        pending_approval = conn.execute(
            """SELECT COUNT(*) FROM rfq_projects
               WHERE tenant_id = ? AND status = '承認待ち'""",
            (tenant_id,),
        ).fetchone()[0]

        draft = conn.execute(
            "SELECT COUNT(*) FROM rfq_projects WHERE tenant_id = ? AND status = 'Draft'",
            (tenant_id,),
        ).fetchone()[0]

    return {
        "total": total,
        "active": active,
        "pending_quotes": pending_quotes,
        "pending_approval": pending_approval,
        "draft": draft,
    }


# ---------------------------------------------------------------------------
# Dispatch (RFP送信)
# ---------------------------------------------------------------------------

def dispatch_rfq(rfq_id: str) -> None:
    """RFQをサプライヤーへ展開（ステータスをRFQ送信に更新）"""
    with get_conn() as conn:
        conn.execute(
            """UPDATE rfq_projects
               SET status = 'RFQ送信', dispatched_at = datetime('now'), updated_at = datetime('now')
               WHERE rfq_id = ?""",
            (rfq_id,),
        )
        # 各サプライヤーの invitation_date を本日に更新
        conn.execute(
            "UPDATE rfq_suppliers SET invitation_date = date('now') WHERE rfq_id = ?",
            (rfq_id,),
        )


def update_supplier_response(rfq_supplier_id: int, status: str) -> None:
    """サプライヤーの回答状況を更新"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE rfq_suppliers SET response_status = ? WHERE id = ?",
            (status, rfq_supplier_id),
        )


# ---------------------------------------------------------------------------
# QCJDM Evaluation
# ---------------------------------------------------------------------------

def upsert_evaluation(rfq_id: str, supplier_name: str, scores: dict, evaluated_by: str = "", tenant_id: int = 1) -> None:
    """QCJDM評価を登録/更新。いずれかが1点ならゲーティング除外。"""
    vals = [scores.get(k) for k in ("quality_score", "job_score", "dev_score", "mgmt_score", "cost_score")]
    is_gated = 1 if any(v == 1 for v in vals if v is not None) else 0
    filled = [v for v in vals if v is not None]
    total = round(sum(filled) / len(filled), 2) if filled else None

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM evaluations WHERE rfq_id=? AND supplier_name=?",
            (rfq_id, supplier_name),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE evaluations SET cost_score=:cost, quality_score=:q, job_score=:j,
                   dev_score=:d, mgmt_score=:m, total_score=:total, is_gated_out=:gated,
                   comment=:comment, evaluated_by=:by, evaluated_at=datetime('now')
                   WHERE rfq_id=:rfq AND supplier_name=:sup""",
                {"cost": scores.get("cost_score"), "q": scores.get("quality_score"),
                 "j": scores.get("job_score"), "d": scores.get("dev_score"),
                 "m": scores.get("mgmt_score"), "total": total, "gated": is_gated,
                 "comment": scores.get("comment", ""), "by": evaluated_by,
                 "rfq": rfq_id, "sup": supplier_name},
            )
        else:
            conn.execute(
                """INSERT INTO evaluations
                   (rfq_id, tenant_id, supplier_name, cost_score, quality_score, job_score,
                    dev_score, mgmt_score, total_score, is_gated_out, comment, evaluated_by)
                   VALUES (:rfq, :tid, :sup, :cost, :q, :j, :d, :m, :total, :gated, :comment, :by)""",
                {"rfq": rfq_id, "tid": tenant_id, "sup": supplier_name,
                 "cost": scores.get("cost_score"), "q": scores.get("quality_score"),
                 "j": scores.get("job_score"), "d": scores.get("dev_score"),
                 "m": scores.get("mgmt_score"), "total": total, "gated": is_gated,
                 "comment": scores.get("comment", ""), "by": evaluated_by},
            )


def get_evaluations(rfq_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM evaluations WHERE rfq_id = ? ORDER BY total_score DESC NULLS LAST",
            (rfq_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Approval Route
# ---------------------------------------------------------------------------

def create_approval_route(rfq_id: str, steps: list[dict], tenant_id: int = 1) -> None:
    """承認ルートを登録（既存を削除して再登録）"""
    with get_conn() as conn:
        conn.execute("DELETE FROM approvals WHERE rfq_id = ?", (rfq_id,))
        for step in steps:
            conn.execute(
                """INSERT INTO approvals
                   (rfq_id, tenant_id, step_order, approver_role, approver_level,
                    approver_employee_id, approver_name, department, required_level, status)
                   VALUES (:rfq_id, :tid, :order, :role, :level, :emp_id, :name, :dept, :req_level, 'Pending')""",
                {
                    "rfq_id": rfq_id, "tid": tenant_id,
                    "order": step["step_order"], "role": step["approver_role"],
                    "level": step.get("approver_level", ""), "emp_id": step.get("approver_employee_id", ""),
                    "name": step.get("approver_name", ""), "dept": step.get("department", ""),
                    "req_level": step.get("required_level", ""),
                },
            )


def get_approval_route(rfq_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE rfq_id = ? ORDER BY step_order",
            (rfq_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_approval_status(approval_id: int, status: str, comment: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE approvals SET status=?, comment=?, decided_at=datetime('now') WHERE id=?",
            (status, comment, approval_id),
        )


# ---------------------------------------------------------------------------
# Operation Log
# ---------------------------------------------------------------------------

def log_action(
    action: str,
    entity: str = "",
    entity_id: str = "",
    user_name: str = "system",
    user_role: str = "",
    detail: str = "",
    tenant_id: int = 1,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO operation_logs
               (tenant_id, user_name, user_role, action, entity, entity_id, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, user_name, user_role, action, entity, entity_id, detail),
        )
