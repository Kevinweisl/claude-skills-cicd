---
name: security-scan
description: Scan the user's CURRENT repository's OWN SOURCE CODE (not its dependencies) for SAST findings, hard-coded secrets/credentials, and (optionally) container-image CVEs in a built docker image. Default behaviour reads `$PWD` (no clone, no network). Use this when the user asks to "run semgrep", "run gitleaks", "run SAST", "find SQL injection in our handlers", "any hardcoded passwords in the codebase", "did we leak any API keys", "did we commit a .env", "scan our Dockerfile for misconfigs", or "scan the docker image for CVEs". These are queries about CODE WE WROTE, not LIBRARIES WE IMPORTED. The user may also pass a remote GitHub URL to scan a third-party repo. For known CVEs in third-party packages (lodash, requests, etc.), use dependency-audit instead. For lint/test, use lint-and-test. For build/publish, use build-and-release. Read-only.
allowed-tools: Bash(python:*), Bash(./skills/security-scan/scripts/run.py:*)
---

# security-scan

Run SAST + secret-leak detection (and optionally container-image CVE scan) on the project source. **Read-only**: never modifies the repo.

## When to use

- "scan for SAST issues" / "find SQL injection" / "any leaked API keys" → run on the user's current repo
- "scan https://github.com/foo/bar for SAST and secrets" → shallow-clone, then scan

**Don't use for**: CVEs in third-party libraries → that's `dependency-audit` (this skill scans CODE WE WROTE, not libraries we imported). Lint/test → `lint-and-test`.

## How to invoke

### Default: current repository (no clone)

```bash
python skills/security-scan/scripts/run.py
```

The script reads `$PWD`, validates `.git/`, and runs scanners in parallel against the working tree.

Optional flags:

- `--scan-types sast,secrets,container` (default: `sast,secrets`)
- `--image-name OWNER/NAME` (required for `container` scan)

### Remote: shallow-clone a GitHub URL

```bash
python skills/security-scan/scripts/run.py \
    --repo-url https://github.com/foo/bar --ref main \
    --scan-types sast,secrets
```

## Interpret the JSON output

```json
{
  "ok": true,
  "scan_types_run": ["semgrep", "gitleaks"],
  "findings": [
    {"tool": "semgrep", "rule_id": "...", "file": "src/auth.py", "line": 42,
     "severity": "high", "message": "..."}
  ],
  "by_severity": {"critical": 0, "high": 1, "medium": 3},
  "secrets_redacted_in_output": true,
  "tokens_redacted_count": 2,
  "cache_key": "..."
}
```

Token-shape redaction is always applied: anything in `findings[].message` that looks like a credential (GitHub PAT, AWS key, Anthropic key, NIM key, JWT) is replaced with `<redacted-N>` before output is emitted. `tokens_redacted_count` tells you how many were caught.

## Boundaries

- **Read-only.** No source edits, no auto-fix.
- **Source code, not libraries.** Use `dependency-audit` for third-party CVE checks.
- **Token-shape redaction always on.** Cannot be bypassed; this is the safety boundary that prevents secret-scan output from leaking secrets back to the LLM context.
- **No exceptions on tool failure.** Missing scanners (gitleaks, semgrep, bandit, trivy) reduce coverage but never crash; the skill emits `warnings: [...]` and proceeds.
- **URL guard.** Only `https://github.com/` accepted in `--repo-url`.
