---
name: dependency-audit
description: Scan the user's CURRENT repository (or a remote GitHub URL) for KNOWN VULNERABILITIES in third-party dependencies using OSV/GHSA advisory databases. Detects ecosystem from manifest files (pyproject.toml/requirements.txt, package.json/package-lock.json, Cargo.toml, go.mod) and runs the matching auditor (pip-audit, npm audit, cargo audit, govulncheck). Default behaviour reads `$PWD` (no clone). Use this when the user asks to "audit dependencies", "run pip-audit", "npm audit", "check for vulnerable packages", "are any of my deps CVE-flagged", "is lodash safe", "any CVEs in our packages", "scan our requirements.txt", "check our Cargo.lock for advisories", or "any GHSA hits in our manifest". For SAST or secret scans on YOUR OWN source code, use security-scan. For lint/test, use lint-and-test. For build/publish, use build-and-release. Read-only.
allowed-tools: Bash(python:*), Bash(./skills/dependency-audit/scripts/run.py:*)
---

# dependency-audit

Look up known CVEs in the project's third-party dependencies. **Read-only**: never modifies manifests, never pushes to a registry.

## When to use

- "audit my deps for CVEs" / "any vulnerabilities in our packages" → run on the user's current repo
- "audit deps of https://github.com/psf/requests" → shallow-clone the remote URL

**Don't use for**: vulnerabilities in the project's OWN code (SAST) → that's `security-scan`. Lint/test → `lint-and-test`. Build/release → `build-and-release`.

## How to invoke

### Default: current repository (no clone)

```bash
python skills/dependency-audit/scripts/run.py
```

The script reads `$PWD`, validates `.git/`, walks the manifest files, and fans out to per-ecosystem auditors.

Optional flags:

- `--ecosystems python,node,rust,go` (default: auto-detect from manifest files)

### Remote: shallow-clone a GitHub URL

```bash
python skills/dependency-audit/scripts/run.py \
    --repo-url https://github.com/psf/requests --ref main
```

## Interpret the JSON output

```json
{
  "ok": true,
  "ecosystems_detected": ["python"],
  "findings_by_ecosystem": {
    "python": {
      "tool": "pip-audit",
      "vulnerabilities": [
        {"package": "requests", "id": "GHSA-...", "severity": "high", "fix_versions": ["2.32.0"]}
      ]
    }
  },
  "summary": {"critical": 0, "high": 1, "medium": 0, "low": 0, "total": 1},
  "cache_key": "..."
}
```

If a scanner binary is missing (e.g. `pip-audit` not on PATH), the per-ecosystem entry has `error: "binary not installed"` and an empty `vulnerabilities` list. The skill does not crash; that ecosystem is simply skipped.

## Boundaries

- **Read-only.** No manifest edits, no auto-upgrade.
- **Third-party libraries only.** For SAST findings in the user's own code, use `security-scan`.
- **No exceptions on tool failure.** Branch on `result.ok` and per-ecosystem `error` keys.
- **URL guard.** Only `https://github.com/` accepted in `--repo-url`.
