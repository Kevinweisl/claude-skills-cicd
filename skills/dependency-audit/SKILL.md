---
name: dependency-audit
description: |
  Scan a repository's dependency manifests (pyproject.toml/requirements.txt,
  package.json/package-lock.json, Cargo.toml, go.mod) for KNOWN VULNERABILITIES
  in the dependency tree using OSV/GHSA advisory databases. Use this when the
  user asks to "audit dependencies", "check for vulnerable packages", "are any
  of my deps CVE-flagged", "run pip-audit", "npm audit", "check for
  vulnerabilities in third-party libs", or any vulnerability check **at the
  dependency tree** level. Do NOT use for: scanning the project's own source
  code for SAST findings or secrets (use security-scan), running tests or
  lints (use lint-and-test), or building artifacts (use build-and-release).
  Read-only. Returns SARIF-format vulnerability findings.
allowed-tools: "Bash(pip-audit *) Bash(npm audit --json) Bash(cargo audit *) Bash(osv-scanner *)"
worker_target: ci
---

# dependency-audit

Scan dependency manifests for known vulnerabilities by polling OSV/GHSA
advisory databases. Multi-ecosystem auto-detection: a single skill that
identifies the project's ecosystem from manifest filenames and routes to the
appropriate tool.

## Pattern: Read-only, multi-ecosystem routing

| Manifest detected | Tool | Advisory DB |
|---|---|---|
| `pyproject.toml` / `requirements.txt` / `Pipfile.lock` | `pip-audit` | OSV + PyPI Advisory Database |
| `package-lock.json` / `yarn.lock` | `npm audit --json` | GHSA |
| `Cargo.lock` | `cargo audit` | RustSec Advisory DB |
| `go.sum` | `osv-scanner` | OSV |

Findings from each tool are **normalized to SARIF** (Static Analysis Results
Interchange Format) so downstream callers don't have to know per-tool output
schemas. Severity uses CVSS v3 if present, else GHSA's qualitative tier.

Caching: `lockfile_hash + advisory_db_date` — re-running the same lockfile
against an unchanged advisory DB is a no-op.

## Boundary distinction (this is NOT security-scan)

`dependency-audit` looks at YOUR DEPENDENCIES (third-party libraries pulled in
via package manifests) for KNOWN CVE/GHSA advisories.

`security-scan` looks at YOUR OWN SOURCE CODE for SAST findings (insecure
patterns), secrets in commits, and container CVEs in your built image.

A user query like "scan my project for security issues" is ambiguous — it
could mean either. The trigger eval includes such queries to verify Claude
disambiguates correctly via these descriptions.

## Input
```json
{
  "repo_path": "/abs/path/to/repo",     // optional, defaults to cwd
  "ecosystems": ["python", "node"]      // optional, default: auto-detect all manifests
}
```

## Output
```json
{
  "ok": true,
  "findings_by_ecosystem": {
    "python": {"tool": "pip-audit", "vulnerabilities": [...]},
    "node": {"tool": "npm-audit", "vulnerabilities": [...]}
  },
  "sarif": {...},
  "summary": {"critical": 0, "high": 2, "medium": 5, "low": 1, "total": 8},
  "cache_key": "<sha256>"
}
```
