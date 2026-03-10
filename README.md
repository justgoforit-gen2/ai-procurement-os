# Procurement OS

モジュール型調達プラットフォームのスケルトン。
POC は Streamlit UI、製品配布は FastAPI "Kit" 形式（Standard / Expansion / Automation / Full）。

---

## Quickstart

### 1. 依存関係のインストール

```bash
uv sync
```

### 2. Streamlit UI の起動（OCR Doc Reader）

```bash
uv run streamlit run apps/OCR-doc-reader/app.py
```

ブラウザで http://localhost:8501 を開く。

### 2-b. Streamlit UI の起動（Spend Analytics）

```bash
uv run streamlit run apps/spend-analytics/app.py
```

または、プロジェクトの `.venv` を必ず使って起動したい場合:

```powershell
./scripts/run_streamlit.ps1 -App "apps/spend-analytics/app.py" -Port 8501
```

### 3. FastAPI サーバーの起動

```bash
uv run uvicorn services.api.main:app --reload --port 8000
```

API ドキュメント: http://localhost:8000/docs

---

## Docker で同梱配布（API + Streamlit）

`ai_procurement_os/` ディレクトリで実行します。

```bash
docker compose up --build
```

- Streamlit UI: http://localhost:8501
- FastAPI docs: http://localhost:8000/docs

個別起動する場合:

```bash
docker compose up --build api
docker compose up --build ui
```

モジュール（機能）切替はホスト側の `config/app/modules.yaml` を編集し、再起動します。

---

## UIのエラー検出（Playwrightなし）

このPC環境では Windows の Code Integrity (WDAC) により、Playwright依存のネイティブ拡張（`.pyd`）がブロックされる場合があります。
その場合、ブラウザ自動操作（Playwright）ではなく、分析パイプラインのスモークテストで例外を検出してください。

```bash
uv run python scripts/smoke_spend_analytics.py
```

---

## モジュール切替

`config/app/modules.yaml` の `enabled` フラグを変更してサーバーを再起動するだけ。

```yaml
spend:
  enabled: true
rfx:
  enabled: false
ocr:
  enabled: true
ap:
  enabled: false
```

---

## フォルダ構成

```
ai_procurement_os/
├── config/
│   ├── app/
│   │   ├── modules.yaml        # モジュール ON/OFF
│   │   └── security.yaml       # 認証・CORS・アップロード制限
│   └── ocr/
│       └── default.yaml        # OCR エンジン設定（実行時に読込）
├── schemas/
│   └── audit_log.schema.json   # 監査ログの JSON Schema
├── packages/
│   └── proc_core/              # ビジネスロジック（Kit 共通）
│       ├── audit/
│       │   ├── events.py       # AuditEvent ビルダー
│       │   ├── redact.py       # コンテンツ漏洩防止のアローリスト
│       │   └── sink.py         # stdout / ファイルへの emit
│       ├── spend/              # 支出分析（スタブ）
│       ├── rfx/                # RFx 作成（スタブ）
│       ├── ocr/                # OCR 解析（スタブ）
│       └── ap/                 # 請求書処理（スタブ）
├── services/
│   └── api/
│       ├── main.py             # FastAPI エントリポイント
│       └── routes/             # モジュール別ルーター
│           ├── spend.py
│           ├── rfx.py
│           ├── ocr.py
│           └── ap.py
├── apps/
│   └── OCR-doc-reader/
│       └── app.py              # Streamlit UI
├── docs/
│   ├── CONTEXT.md
│   └── runbook/
│       └── security.md
├── .env.example
├── .gitignore
└── pyproject.toml
```

---

## 監査ログポリシー

- 保存するのは **メタデータのみ**（request_id, timestamp, doc_hash, カウント類）。
- サプライヤー名・価格・明細・PDF テキストは **絶対に記録しない**。
- スキーマは `schemas/audit_log.schema.json` が正規定義。
- `proc_core.audit.redact` がアローリストを強制する。
