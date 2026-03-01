# Procurement OS (A) — Claude Code Instructions

## Goal
Build a modular procurement platform.
POC uses Streamlit UI; product delivery is FastAPI "kits" (Standard/Expansion/Automation/Full).

## Non-negotiable rules
- Do NOT log or persist sensitive contents (supplier names, prices, line items, PDFs, extracted text).
- Audit logs must store METADATA ONLY (request_id, timestamps, hash, status, counts, versions).
- Keep entrypoints thin:
  - Streamlit: apps/*/app.py
  - FastAPI: services/api/main.py
- Put business logic in packages/proc_core/.
- Runtime behavior is config-driven (config/*.yaml). Skills markdown is design-time only.

## Where to look (source of truth)
- Latest assumptions & constraints: docs/CONTEXT.md
- Security policy: docs/runbook/security.md
- Runtime configs: config/
- Canonical schemas: schemas/
- Core code: packages/proc_core/
- API routes: services/api/routes/
- UI apps: apps/

## Kits (module toggles)
- Standard Kit: spend
- Expansion Kit: spend + rfx
- Automation Kit: spend + rfx + ocr (+ ap if needed)
- Full Package: spend + rfx + ocr + ap (+ audit/ops)

Implement module toggling via: config/app/modules.yaml
FastAPI main.py must register routes based on enabled modules.

## Audit logging policy (metadata-only)
- Define audit schema in schemas/audit_log.schema.json
- Implement in packages/proc_core/audit/:
  - events.py: build audit event objects
  - redact.py: safety redaction (in case of accidental content)
  - sink.py: write to stdout/file (configurable) WITHOUT payload/body
- API must never log request/response bodies.
- Logs include hashes (SHA-256) of input files rather than content.

## Deliverables for the first run
1) Create folder structure as specified in the "Final Tree" (latest approved tree).
2) Create placeholder files with minimal content:
   - config/app/modules.yaml, config/app/security.yaml
   - schemas/audit_log.schema.json
   - services/api/main.py with module-based route registration (stub ok)
   - packages/proc_core/audit/* (stubs ok)
   - apps/OCR-doc-reader/app.py (upload + call proc_core stub)
3) Add .gitignore and .env.example

## Final Tree (must match)
- Follow the folder tree described in the latest approved "ブラッシュアップ版".