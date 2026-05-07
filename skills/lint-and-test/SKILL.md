---
name: lint-and-test
description: Run the lint-then-test pipeline (ruff + pytest for Python, npm lint + npm test for Node) on the user's CURRENT repository and return a structured pass/fail report. Default behaviour reads `$PWD` (the repo the user has checked out and is working on); no clone, no network. Use this when the user asks to "lint and test", "run CI checks", "run pytest", "type-check with mypy", "run prettier and the unit tests", "make sure ruff is clean and tests pass", "ESLint + jest", or any combined static-check-plus-test request on the working repo. To inspect a remote GitHub URL without cloning manually, the user can include the URL in their request and the skill will shallow-clone into a sandbox. For dependency CVE checks, use dependency-audit instead. For SAST or hard-coded-secret scans, use security-scan. For building or publishing artifacts, use build-and-release. Read-only.
allowed-tools: Bash(python:*), Bash(./skills/lint-and-test/scripts/run.py:*)
---

# lint-and-test

Run the canonical lint + test pipeline on a repo checkout. **Read-only**: never modifies the repo, never pushes to a registry.

## When to use

Trigger when the user asks for lint + test work. Two shapes:

- "lint and test", "run CI checks", "make sure ruff is clean and pytest passes" → run on the user's current repo (the directory they're working in)
- "lint and test https://github.com/psf/black at v24.10.0" → run against a remote GitHub URL

If the user wants only one of lint OR test, this skill is still appropriate; it reports both independently and the caller can ignore one.

**Don't use for**: dependency CVE audits → use `dependency-audit`. SAST / secret scans → use `security-scan`. Build / publish → use `build-and-release`.

## How to invoke

### Default: current repository (no clone)

```bash
python skills/lint-and-test/scripts/run.py
```

The script reads `$PWD`, validates that `.git/` exists, and runs against the working tree. No network, no sandbox, no cleanup needed.

Optional flags:

- `--language python|node|auto` (default `auto`; detects via `pyproject.toml` / `package.json`)
- `--commit-sha SHA` (cache key only, no behavior change)

### Remote: shallow-clone a GitHub URL

When the user explicitly names a remote repo:

```bash
python skills/lint-and-test/scripts/run.py \
    --repo-url https://github.com/psf/black --ref v24.10.0
```

The script shallow-clones into `/tmp/skill_sandbox_*`, runs the pipeline against the clone, and removes the sandbox in a `finally` block. URL guard: only `https://github.com/` accepted.

## Interpret the JSON output

```json
{
  "ok": true,
  "language": "python",
  "lint": {"tool": "ruff", "passed": true, "exit_code": 0, "issues": [], "duration_ms": 412},
  "test": {"tool": "pytest", "passed": true, "exit_code": 0, "summary": "623 passed", "duration_ms": 18430},
  "cache_key": "9a1f...c08"
}
```

`ok = lint.passed AND test.passed`. If `ok=false`:

- Lint failures: see `lint.issues` (first 50 ruff lines)
- Test failures: see `test.summary` (last 200 chars, or the matched `N passed/failed/error` line)
- `test.timed_out=true`: pytest exceeded 300 seconds
- `language=="unknown"`: the repo has neither `pyproject.toml` nor `package.json`; lint-and-test does not apply

## Boundaries

- **Read-only.** Never writes to the repo, never pushes to a registry.
- **No CVE checks.** For known vulnerabilities in dependencies, use `dependency-audit`.
- **No SAST.** For SQL injection / hardcoded-secret detection, use `security-scan`.
- **No exceptions on tool failure.** Script always exits 0 (only raises on missing `--repo-path` not being a git repo); branch on `result.ok`.
- **Pytest timeout 300s.** Beyond that, `test.passed=false` with `timed_out=true`.
- **URL guard.** Only `https://github.com/` accepted in `--repo-url`.
