# Copilot instructions (ai_procurement_os)

## Security (pre-push / before publishing)

When preparing to push changes:

- Run the repo secret scan: `python scripts/security_scan.py`.
- Ensure `.env` and `.streamlit/secrets.toml` are not tracked by git.
- If adding new config or sample data, verify it contains no API keys, tokens, passwords, or private keys.

If asked to "push", check `git status -sb`, then run the secret scan, then commit/push.

## Notes

- This repo intentionally avoids introducing new third-party dependencies for security checks.
- The scan script redacts matches in output to avoid re-leaking secrets.
