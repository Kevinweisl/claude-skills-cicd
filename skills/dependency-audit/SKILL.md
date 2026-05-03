---
name: dependency-audit
description: Scan a repository's dependency manifests (pyproject.toml/requirements.txt, package.json/package-lock.json, Cargo.toml, go.mod) for KNOWN VULNERABILITIES in third-party libraries using OSV/GHSA advisory databases. Use this when the user asks to "audit dependencies", "run pip-audit", "npm audit", "check for vulnerable packages", "are any of my deps CVE-flagged", "is lodash safe", "any CVEs in our packages", "scan our requirements.txt", "check our Cargo.lock for advisories", or "any GHSA hits in our manifest". For SAST or secret scans on YOUR OWN source code, use security-scan. For lint/test, use lint-and-test. For build/publish, use build-and-release. Read-only.
allowed-tools: Bash(git clone:*), Bash(python:*), Bash(./skills/dependency-audit/scripts/run.py:*), Bash(rm -rf /tmp/skill_sandbox*)
---

# dependency-audit

Scan dependency manifests across multiple ecosystems and report known CVEs from OSV/GHSA advisory databases. **Read-only**.

## When to use

Trigger when the user asks about CVEs / advisories / vulnerabilities in **third-party libraries** (not their own code):

- "audit deps of psf/requests"
- "any CVEs in our package-lock.json"
- "check if lodash is safe"
- "run pip-audit on this repo"

**Don't use for**: SAST / secrets / SQL injection / hardcoded passwords in **the user's own code** → use `security-scan`. Lint/test → `lint-and-test`. Build/publish → `build-and-release`.

## How to use

### Step 1 — get the repo onto disk

If a `https://github.com/...` URL was given, clone shallowly:

```bash
SANDBOX=/tmp/skill_sandbox/audit-$$
git clone --depth=1 --branch <REF> <REPO_URL> $SANDBOX
```

If a local path was given, use it directly.

### Step 2 — run the script

```bash
python skills/dependency-audit/scripts/run.py \
    --repo-path $SANDBOX \
    [--ecosystems python,node,rust,go]   # optional; default detects all
```

The script auto-detects ecosystems from manifest files (`pyproject.toml`, `package-lock.json`, `Cargo.lock`, `go.sum`) and runs the appropriate auditor:

- **python** → `pip-audit`
- **node** → `npm audit`
- **rust** → `cargo audit`
- **go** → `govulncheck`

Skipped silently if the auditor binary isn't installed (recorded in output).

### Step 3 — interpret the JSON

```json
{
  "ok": true,
  "ecosystems_detected": ["python", "node"],
  "findings_by_ecosystem": {
    "python": {
      "tool": "pip-audit",
      "vulnerabilities": [
        {"package": "requests", "id": "GHSA-xxxx", "severity": "high",
         "fix_versions": ["2.32.0"]}
      ]
    },
    "node": { "tool": "npm-audit", "vulnerabilities": [...] }
  },
  "summary": {"critical": 0, "high": 1, "medium": 0, "low": 0, "total": 1},
  "cache_key": "..."
}
```

If `ecosystems_detected` is empty, the repo has no recognized manifest files — tell the user this skill doesn't apply.

If a per-ecosystem entry has `error: "binary not installed"`, the auditor isn't on PATH; mention this so the user knows the result is partial.

For each vulnerability, surface `package`, `id` (CVE/GHSA), `severity`, and `fix_versions` if present.

### Step 4 — clean up

```bash
rm -rf /tmp/skill_sandbox/audit-*
```

## Boundaries

- **Read-only.** Never modifies the manifest or installs anything.
- **Third-party only.** Will not flag issues in the user's own source code.
- **Auditor binaries optional** — missing tools are reported, not crashed on.
- **No platform errors raised** — script always exits 0; branch on `result.ok`.
