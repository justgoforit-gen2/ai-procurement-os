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

## Pre-push secret scan (recommended)
To make the check repeatable (and not rely on memory), this repo provides a lightweight scan script and a Git `pre-push` hook.

### 1) Install the pre-push hook (Windows / PowerShell)
From the repo root:

```powershell
pwsh -File scripts/install_git_hooks.ps1
```

After this, every `git push` will run `scripts/security_scan.py` and will fail the push if it finds obvious secrets.

### 2) Run the scan manually

```powershell
python scripts/security_scan.py
```

### 3) GitHub code search (quick spot-check)
In GitHub search (Code), you can use queries like:

- `repo:justgoforit-gen2/ai-procurement-os AKIA`
- `repo:justgoforit-gen2/ai-procurement-os "BEGIN OPENSSH PRIVATE KEY"`
- `repo:justgoforit-gen2/ai-procurement-os ghp_`
- `repo:justgoforit-gen2/ai-procurement-os sk-`

If anything sensitive is found:
- Rotate/revoke the credential immediately.
- Remove it from the repo history if it was committed.
