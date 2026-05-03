---
name: lint-and-test
description: Run the lint-then-test pipeline on a Python or Node repository and return a structured pass/fail report. Use this when the user asks to "lint and test", "run CI checks", "run pytest", "type-check with mypy", "run prettier and the unit tests", "make sure ruff is clean and tests pass", "ESLint + jest", or any combined static-check-plus-test request on a repository. For dependency CVE checks, use dependency-audit instead. For SAST or hard-coded-secret scans, use security-scan. For building or publishing artifacts, use build-and-release. Read-only.
allowed-tools: Bash(git clone:*), Bash(python:*), Bash(./skills/lint-and-test/scripts/run.py:*), Bash(rm -rf /tmp/skill_sandbox*)
---

# lint-and-test

Run the canonical lint + test pipeline on a repo checkout. **Read-only** — never modifies the repo or any registry.

## When to use

Trigger when the user asks to lint+test a specific repository (URL or local path). Examples:

- "lint and test https://github.com/psf/black at v24.10.0"
- "run CI checks on this repo"
- "make sure ruff is clean and pytest passes for psf/requests"

If the user wants only one of lint OR test, this skill is still appropriate — it reports both independently and the caller can ignore one.

**Don't use for**: dependency CVE audits → use `dependency-audit`. SAST / secret scans → use `security-scan`. Build / publish → use `build-and-release`.

## How to use

### Step 1 — get the repo onto disk

If the user gave a `https://github.com/...` URL, clone shallowly into a sandbox:

```bash
SANDBOX=/tmp/skill_sandbox/lint-test-$$
git clone --depth=1 --branch <REF> <REPO_URL> $SANDBOX
```

Reject anything not starting with `https://github.com/` (no `file://`, `ssh://`, other hosts).

If the user gave an existing local path, use it directly — skip the clone.

### Step 2 — run the script

```bash
python skills/lint-and-test/scripts/run.py --repo-path $SANDBOX
```

Optional flags:

- `--language python|node|auto` (default `auto` — detects via `pyproject.toml` / `package.json`)
- `--commit-sha <sha>` (cache key only, no behavior change)

The script always prints exactly one JSON object on stdout and exits 0 on tool-level failures (it raises only on missing `--repo-path`).

### Step 3 — interpret the JSON

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

- Look at `lint.issues` (first 50 ruff lines) for lint failures.
- Look at `test.summary` (last 200 chars of pytest output, or the matched `N passed/failed/error` line) for test failures.
- If `test.timed_out=true`, the suite exceeded 300 seconds — tell the user so.
- If `language=="unknown"`, the repo has neither `pyproject.toml` nor `package.json`. Report this to the user; lint-and-test does not apply.

### Step 4 — clean up

```bash
rm -rf /tmp/skill_sandbox/lint-test-*
```

## Boundaries

- **Read-only.** Never writes to the repo, never pushes to a registry.
- **No CVE checks.** For known vulnerabilities in dependencies, use `dependency-audit`.
- **No SAST.** For SQL injection / hardcoded secret detection, use `security-scan`.
- **No platform errors raised** — script always exits 0 (unless `--repo-path` doesn't exist); branch on `result.ok`.
- **Pytest timeout 300 s.** Beyond that, `test.passed=false` with `timed_out=true`.
- **URL guard**: only `https://github.com/` URLs accepted in step 1.
