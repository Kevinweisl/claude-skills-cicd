---
name: security-scan
description: |
  Scan a repository's OWN SOURCE CODE (not its dependencies) for SAST findings,
  hard-coded secrets/credentials, and (optionally) container-image CVEs in a
  built docker image. Use this when the user asks to "run semgrep", "run
  gitleaks", "run SAST", "find SQL injection in our handlers", "any hardcoded
  passwords in the codebase", "did we leak any API keys", "did we commit a
  .env", "scan our Dockerfile for misconfigs", or "scan the docker image for
  CVEs". These are queries about CODE WE WROTE, not LIBRARIES WE IMPORTED.
  For known CVEs in third-party packages (lodash, requests, etc.), use
  dependency-audit instead. For lint/test, use lint-and-test. For
  build/publish, use build-and-release. Read-only. Aggregates findings from
  Semgrep, gitleaks, and trivy with severity-weighted dedup.
allowed-tools: "Bash(semgrep *) Bash(gitleaks *) Bash(trivy *) Bash(bandit *) Bash(git *)"
worker_target: ci
---

# security-scan

Source-code security scanner that runs three orthogonal tools in parallel and
aggregates their findings into a single severity-ranked report.

## Pattern: Multi-tool orchestration with severity-weighted aggregation

| Tool | What it finds |
|---|---|
| **Semgrep** | SAST patterns (SQL injection, XSS, insecure crypto, command injection, hardcoded secrets matched by rule) |
| **gitleaks** | Hard-coded secrets in git history (API keys, AWS access keys, JWT tokens, OpenAI keys, Anthropic keys) |
| **trivy** | Container image CVEs (when a docker image is provided) and IaC misconfigurations |
| **bandit** (Python only) | Python-specific security anti-patterns |

Findings are deduplicated by `(file, line, rule_id)` — Semgrep and bandit can
both flag the same Python file/line, and we count that as one finding (highest
severity wins). Output is SARIF-compatible.

## Boundary distinction (this is NOT dependency-audit)

`security-scan` looks at YOUR OWN SOURCE CODE: secrets in your commits, SAST
findings in your handlers, misconfigurations in your Dockerfile.

`dependency-audit` looks at YOUR THIRD-PARTY DEPENDENCIES (libraries pulled in
via package manifests) for known CVEs/GHSA advisories.

For the prompt "scan my repo for security problems" — both could apply. The
two skills coexisting in trigger eval intentionally tests this disambiguation.

## Input
```json
{
  "repo_path": "/abs/path/to/repo",       // optional, defaults to cwd
  "scan_types": ["sast", "secrets"],      // default: ["sast", "secrets"]; "container" requires `image_name`
  "image_name": "ghcr.io/org/repo:tag"    // optional, for container scan
}
```

## Output
```json
{
  "ok": true,
  "findings": [
    {"tool": "semgrep", "rule_id": "...", "file": "src/foo.py", "line": 42,
     "severity": "high", "message": "Potential SQL injection"},
    ...
  ],
  "by_severity": {"critical": 0, "high": 1, "medium": 3, "low": 7, "info": 12},
  "scan_types_run": ["sast", "secrets"],
  "secrets_redacted_in_output": true,
  "cache_key": "<sha256>"
}
```

## Output safety

ALL token-shaped strings in the output are redacted (replaced with
`<redacted-N>`) before persistence. The redaction event is logged to the
audit_events table. The whole point of running this skill is to find secrets;
emitting them downstream would defeat that.
