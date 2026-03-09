"""Lightweight secret scan for this repo.

- No external deps.
- Designed to be used from a Git pre-push hook.
- Avoids printing full secret values (redacts matches).

Exit code:
- 0: no findings
- 1: findings detected
- 2: unexpected error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]


RULES: list[Rule] = [
    Rule(
        "Private key block",
        re.compile(r"-----BEGIN (RSA|OPENSSH|DSA|EC) PRIVATE KEY-----|PRIVATE KEY-----"),
    ),
    Rule("AWS Access Key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    Rule("GitHub Token", re.compile(r"\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})\b")),
    Rule("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    Rule("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    Rule(
        "Generic secret assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|client[_-]?secret)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})['\"]?"
        ),
    ),
]


TEXT_EXT_ALLOWLIST = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".env.example",
    ".csv",
}


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()


def _run_git(repo_root: Path, args: list[str]) -> str:
    cmd = ["git", "-C", str(repo_root), *args]
    return _run(cmd)


def _repo_root_from_arg(repo_root: str | None) -> Path:
    # Default: current working directory's repository.
    if not repo_root:
        root = _run(["git", "rev-parse", "--show-toplevel"])
        return Path(root)

    candidate = Path(repo_root).expanduser().resolve()
    root = _run_git(candidate, ["rev-parse", "--show-toplevel"])
    return Path(root)


def _tracked_files(repo_root: Path) -> list[Path]:
    out = _run_git(repo_root, ["ls-files"])
    paths = [Path(p) for p in out.splitlines() if p.strip()]
    return paths


def _should_scan(path: Path) -> bool:
    name = path.name.lower()
    if name == "security_scan.py":
        return False
    if name in {"uv.lock"}:
        return False

    if path.suffix.lower() in TEXT_EXT_ALLOWLIST:
        return True

    if name.endswith(".env.example"):
        return True

    # Scan files without suffix only if they look like text config.
    if path.suffix == "":
        return name in {"dockerfile", "makefile"}

    return False


def _redact(line: str) -> str:
    redacted = line
    for rule in RULES:
        redacted = rule.pattern.sub("<REDACTED>", redacted)
    return redacted


def _check_forbidden_tracked_files(tracked: set[str]) -> list[str]:
    forbidden = {
        ".env",
        ".streamlit/secrets.toml",
    }
    return sorted(forbidden.intersection(tracked))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lightweight secret scan (git tracked files).")
    p.add_argument(
        "--repo-root",
        default=None,
        help="Path to the git repository to scan (default: current repo)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(list(argv or sys.argv[1:]))

        root = _repo_root_from_arg(args.repo_root)
        files = _tracked_files(root)

        tracked_set = {str(p).replace("\\", "/") for p in files}
        forbidden_hits = _check_forbidden_tracked_files(tracked_set)

        findings: list[str] = []

        if forbidden_hits:
            for hit in forbidden_hits:
                findings.append(f"Forbidden file tracked: {hit}")

        for rel in files:
            if not _should_scan(rel):
                continue

            abs_path = root / rel
            try:
                if abs_path.stat().st_size > 2_000_000:
                    continue
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for idx, line in enumerate(content.splitlines(), start=1):
                for rule in RULES:
                    if rule.pattern.search(line):
                        snippet = _redact(line).strip()
                        findings.append(f"{rel.as_posix()}:{idx} [{rule.name}] {snippet}")
                        break

        if findings:
            print("[security_scan] Potential secrets detected. Please review:")
            for f in findings[:200]:
                print(" -", f)
            if len(findings) > 200:
                print(f" ... and {len(findings) - 200} more")
            print("[security_scan] Aborting push. If these are false positives, adjust rules in scripts/security_scan.py.")
            return 1

        print("[security_scan] OK: no obvious secrets found in tracked files.")
        return 0

    except subprocess.CalledProcessError as e:
        print("[security_scan] ERROR running git command:")
        print(e.output)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"[security_scan] ERROR: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
