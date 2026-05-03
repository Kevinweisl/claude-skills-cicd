---
name: security-scan
description: Scan a repository's OWN SOURCE CODE (not its dependencies) for SAST findings, hard-coded secrets/credentials, and (optionally) container-image CVEs in a built docker image. Use this when the user asks to "run semgrep", "run gitleaks", "run SAST", "find SQL injection in our handlers", "any hardcoded passwords in the codebase", "did we leak any API keys", "did we commit a .env", "scan our Dockerfile for misconfigs", or "scan the docker image for CVEs". These are queries about CODE WE WROTE, not LIBRARIES WE IMPORTED. For known CVEs in third-party packages (lodash, requests, etc.), use dependency-audit instead. For lint/test, use lint-and-test. For build/publish, use build-and-release. Read-only.
allowed-tools: Bash(git clone:*), Bash(python:*), Bash(./skills/security-scan/scripts/run.py:*), Bash(rm -rf /tmp/skill_sandbox*)
---

# security-scan

Run SAST + secrets scanners (Semgrep, Bandit, gitleaks; optionally trivy for container CVEs) in parallel and aggregate findings. **Read-only**.

## When to use

Trigger when the user asks about issues in **their own source code** (not third-party deps):

- "run semgrep on this repo"
- "any hardcoded passwords in our codebase"
- "find SQL injection in our handlers"
- "did we accidentally commit a `.env`"
- "scan the docker image for CVEs"

**Don't use for**: known CVEs in third-party libraries → `dependency-audit`. Lint/test → `lint-and-test`. Build/publish → `build-and-release`.

## How to use

### Step 1 — get the repo onto disk

If a `https://github.com/...` URL was given, clone shallowly:

```bash
SANDBOX=/tmp/skill_sandbox/scan-$$
git clone --depth=1 --branch <REF> <REPO_URL> $SANDBOX
```

If a local path was given, use it directly.

### Step 2 — run the script

```bash
python skills/security-scan/scripts/run.py \
    --repo-path $SANDBOX \
    [--scan-types sast,secrets,container]    # default: sast,secrets
    [--image-name owner/name]                  # required only for container
```

Available scanners (each used only if its binary is installed):

- **Semgrep** (`--config=auto`) for SAST
- **Bandit** for Python-specific SAST
- **gitleaks** for secrets / credentials in git history
- **trivy** for container image CVEs (only when `container` requested + `--image-name`)

### Step 3 — interpret the JSON

```json
{
  "ok": true,
  "scan_types_run": ["semgrep", "gitleaks"],
  "findings": [
    {"tool": "semgrep", "rule_id": "python.lang.security.audit.subprocess-shell-true",
     "file": "src/runner.py", "line": 42,
     "severity": "high", "message": "..."},
    {"tool": "gitleaks", "rule_id": "github-pat",
     "file": ".env.local", "line": 3,
     "severity": "critical", "message": "secret leak: GitHub Personal Access Token"}
  ],
  "by_severity": {"critical": 1, "high": 1},
  "secrets_redacted_in_output": true,
  "tokens_redacted_count": 0,
  "cache_key": "..."
}
```

Findings are **deduplicated** by `(file, line, rule_id)` keeping the highest severity. Capped at 200 to keep output reasonable.

`secrets_redacted_in_output: true` means all messages have passed token-shape regex redaction (GitHub PAT, AWS key, OpenAI / Anthropic / NIM keys, JWT). `tokens_redacted_count` reports how many were actually replaced (usually 0; spikes indicate something interesting).

If `scan_types_run` is empty, no scanners are installed locally — the JSON includes a `warnings` array explaining this. Tell the user.

### Step 4 — clean up

```bash
rm -rf /tmp/skill_sandbox/scan-*
```

## Boundaries

- **Read-only.** Never modifies code.
- **Own code only.** For third-party CVEs, use `dependency-audit`.
- **Per-tool timeout 300 s.** Slow repos may hit this on Semgrep.
- **No platform errors raised** — script always exits 0.
- **Output is always redacted** even if a finding's message contained a real token.
