---
name: lint-and-test
description: |
  Run the lint-then-test pipeline on a Python or Node repo at a specific commit
  and return a structured pass/fail report. Use this when the user asks to
  "lint and test", "run CI checks", "run pytest", "type-check with mypy",
  "run prettier and the unit tests", "make sure ruff is clean and tests pass",
  "ESLint + jest", or any combined static-check-plus-test request on a
  repository. For dependency CVE checks, use dependency-audit instead. For
  SAST or hard-coded-secret scans, use security-scan. For building or
  publishing artifacts, use build-and-release. Read-only. Returns {ok,
  lint_passed, test_passed, summary, exit_code, durations}.
allowed-tools: "Bash(ruff *) Bash(pytest *) Bash(npm *) Bash(git *)"
worker_target: ci
---

# lint-and-test

Run the canonical lint-then-test pipeline on a repository checkout. Combines
static-check and test execution under one boundary because they share dependency
install + lockfile cache + the same runner — splitting them would force every
caller to dedupe install steps.

## Pattern: Multi-tool pipeline with shared install/cache

The skill **chooses** the right tool family per detected language:
- Python (`pyproject.toml` / `setup.py`): `ruff check` then `pytest`
- Node (`package.json`): `npm install` then `npm run lint` then `npm test`

Caching key: `commit_sha + lockfile_hash` — the same commit+lockfile is a no-op
re-run. Read-only: this skill never writes to the repo or any registry.

## Input
```json
{
  "repo_path": "/abs/path/to/repo",   // optional, defaults to cwd
  "commit_sha": "...",                // optional, used for cache key
  "language": "python" | "node" | "auto"   // default: auto-detect
}
```

## Output
```json
{
  "ok": true,
  "lint": {"tool": "ruff", "passed": true, "exit_code": 0, "issues": [], "duration_ms": 412},
  "test": {"tool": "pytest", "passed": true, "exit_code": 0, "summary": "142 passed", "duration_ms": 8234},
  "language": "python",
  "cache_key": "<sha256 of commit+lockfile>"
}
```

## Failure semantics

`ok = lint.passed AND test.passed`. Either failing flips ok to false but the
skill still returns a 200 result with the failing tool's `issues` / `summary` —
NOT a 500 error. Callers branch on `ok`.
