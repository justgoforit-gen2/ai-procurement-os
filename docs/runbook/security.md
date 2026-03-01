# Security Runbook

## Audit log policy
- Only metadata fields defined in `schemas/audit_log.schema.json` may be written.
- `proc_core.audit.redact.redact()` enforces an allowlist before every emit.
- `log_content: false` in `config/ocr/default.yaml` must never be changed to true
  in production.

## File uploads
- Max size is enforced from `config/app/security.yaml` → `upload.max_file_size_mb`.
- Allowed MIME types are enforced from `config/app/security.yaml` → `upload.allowed_mime_types`.
- Uploaded bytes are hashed (SHA-256) immediately; the bytes themselves are not stored.

## Authentication
- Disabled by default (`auth.enabled: false`).
- To enable, set `auth.enabled: true` and supply `API_KEY` in the environment.
- When enabled, requests (except `/health` and CORS preflight) must include the header
  configured by `auth.api_key_header` (default: `X-API-Key`).

## Secrets
- Never commit `.env` files.
- Use `.env.example` as the template and populate a real `.env` locally.
