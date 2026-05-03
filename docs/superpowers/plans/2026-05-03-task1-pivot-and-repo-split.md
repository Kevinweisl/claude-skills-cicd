# Task 1 Pivot + Three-Repo Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pivot Task 1 from custom HTTP platform → standard Claude Code Skills + Anthropic Agent SDK web shell, then split mono-repo `whaleforceAI` into three private personal-account repos with real commit dates preserved.

**Architecture:**
- Task 1 deliverable becomes 4 standard Claude Code skills (`SKILL.md` playbook + `scripts/run.py` executable). Existing `handlers.py` logic is preserved by extracting into per-skill scripts.
- Zeabur demo = thin FastAPI backend wrapping Anthropic Agent SDK; user supplies their own API key via UI (sessionStorage), nothing persists server-side.
- Mono-repo split via `git filter-repo`: keep original commit dates (Apr 30 – May 2), drop abandoned platform-foundation commits where they're empty after path filtering. New pivot work today (May 3) appears as new commits with today's date — that's correct, the pivot really did happen today.
- Three target repos under `Kevinweisl/`, all private at start: `claude-skills-cicd`, `browser-agent`, `sec-10k-extractor`.

**Tech Stack:** Python 3.12 · `anthropic` SDK · FastAPI · vanilla JS · `git-filter-repo` · `gh` CLI

---

## File-Structure Map

```
skills/                              ← already exists; will become the Task 1 deliverable
  _shared/                           ← helpers (no SKILL.md, Claude ignores)
    __init__.py                      [done]
    subprocess_helper.py             [done — run_subprocess + hash_inputs]
    redact.py                        [done — token regex redaction]
    git_fetch.py                     [TODO — shallow clone + URL prefix guard]
  lint-and-test/
    SKILL.md                         ← rewrite as playbook
    scripts/
      run.py                         ← extract from handlers.py:102-167
  build-and-release/
    SKILL.md                         ← rewrite as playbook
    scripts/
      run.py                         ← extract from handlers.py:171-244
  dependency-audit/
    SKILL.md                         ← rewrite as playbook
    scripts/
      run.py                         ← extract from handlers.py:249-318
  security-scan/
    SKILL.md                         ← rewrite as playbook
    scripts/
      run.py                         ← extract from handlers.py:323-446

src/agent_shell/                     ← NEW — Anthropic SDK web shell
  __init__.py
  main.py                            ← FastAPI app, /chat SSE endpoint
  skill_loader.py                    ← scans skills/ → Anthropic tool defs
  tool_runner.py                     ← executes scripts/run.py in sandbox

ui/
  index.html                         ← chat-style UI
  app.js                             ← vanilla JS, sessionStorage key
  styles.css

archive/platform-prototype/          ← what we're pivoting away from
  src/gateway/                       ← moved
  src/workers/base.py                ← moved
  src/workers/ci/__main__.py         ← moved
  src/workers/ci/handlers.py         ← moved (logic copied to scripts/, but original kept for history)
  src/shared/db.py                   ← moved
  migrations/                        ← moved
  README.md                          ← short note: "pivoted on 2026-05-03; see ../../docs/per-task/task1-skills-platform.md for what we built originally"

tests/
  test_run_lint.py                   ← NEW
  test_run_build.py                  ← NEW
  test_run_audit.py                  ← NEW
  test_run_scan.py                   ← NEW
  test_git_fetch.py                  ← NEW
  test_skill_loader.py               ← NEW
```

---

## Phase 0 — Setup

### Task 0.1: Install git-filter-repo + create three private repos

**Files:** none (env-level)

- [ ] **Step 1: Install git-filter-repo**

```bash
brew install git-filter-repo
git-filter-repo --version
```
Expected: prints version (e.g. `2.47.0`)

- [ ] **Step 2: Create three private repos under `Kevinweisl`**

```bash
gh repo create Kevinweisl/claude-skills-cicd --private --description "4 reusable Claude Code skills for GitHub CI/CD: lint-and-test, build-and-release, dependency-audit, security-scan. Includes Anthropic Agent SDK web shell for browser-based demo." --add-readme=false
gh repo create Kevinweisl/browser-agent      --private --description "Generic browser automation agent with self-correction and 7-tier locator ladder. Built on Playwright + Claude." --add-readme=false
gh repo create Kevinweisl/sec-10k-extractor  --private --description "Item-level structured extraction from SEC 10-K filings. Hybrid rules + LLM + XBRL cross-validation pipeline." --add-readme=false
```
Expected: 3 lines `https://github.com/Kevinweisl/<name>` printed

- [ ] **Step 3: Verify visibility**

```bash
gh repo list Kevinweisl --visibility private --limit 5
```
Expected: includes `whaleforceAI` + `claude-skills-cicd` + `browser-agent` + `sec-10k-extractor`

---

## Phase 1 — Task 1 implementation (in current `interview_hw` working tree)

> All Phase 1 work happens in the current mono-repo first. Phase 2 splits the result into per-task repos. This keeps `git filter-repo` invocations simple and lets us reuse existing CI / fixtures.

### Task 1.1: `_shared/git_fetch.py` with TDD

**Files:**
- Create: `skills/_shared/git_fetch.py`
- Create: `tests/test_git_fetch.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_git_fetch.py
from pathlib import Path
import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills"))
from _shared.git_fetch import fetch_repo, GitFetchError

def test_rejects_non_github_url(tmp_path):
    with pytest.raises(GitFetchError, match="only https://github.com/"):
        fetch_repo("https://gitlab.com/foo/bar", "main", tmp_path / "out")

def test_rejects_file_url(tmp_path):
    with pytest.raises(GitFetchError):
        fetch_repo("file:///etc/passwd", "main", tmp_path / "out")

def test_clones_real_small_public_repo(tmp_path):
    dest = tmp_path / "clone"
    result = fetch_repo("https://github.com/octocat/Hello-World", "master", dest)
    assert result == dest
    assert (dest / "README").exists()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/kevinwei/src/interview_hw && pytest tests/test_git_fetch.py -v
```
Expected: ImportError / ModuleNotFoundError

- [ ] **Step 3: Implement `git_fetch.py`**

```python
# skills/_shared/git_fetch.py
"""Shallow-clone a GitHub repo into a sandbox. Used by all 4 skills."""

from __future__ import annotations

from pathlib import Path

from .subprocess_helper import run_subprocess


class GitFetchError(RuntimeError):
    pass


def fetch_repo(repo: str, ref: str, dest: Path, timeout_s: float = 120.0) -> Path:
    """Shallow-clone repo@ref into dest. Returns dest on success.

    Only allows https://github.com/ URLs to prevent file:// / ssh:// / private-host
    side-channels. Uses --depth=1 to avoid pulling full history.
    """
    if not repo.startswith("https://github.com/"):
        raise GitFetchError(
            f"only https://github.com/ URLs allowed (got: {repo!r})"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = run_subprocess(
        ["git", "clone", "--depth=1", "--branch", ref, repo, str(dest)],
        timeout_s=timeout_s,
    )
    if r["exit_code"] != 0:
        raise GitFetchError(
            f"git clone failed (exit={r['exit_code']}): {r['stderr'][-300:]}"
        )
    return dest
```

- [ ] **Step 4: Run tests — verify pass**

```bash
pytest tests/test_git_fetch.py -v
```
Expected: 3 passed (test 3 needs internet; if offline, mark `@pytest.mark.network` and skip)

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/git_fetch.py tests/test_git_fetch.py
git commit -m "feat(skills): add _shared/git_fetch.py with URL prefix guard"
```

---

### Task 1.2: Extract `lint-and-test` to `scripts/run.py`

**Files:**
- Create: `skills/lint-and-test/scripts/run.py`
- Create: `tests/test_run_lint.py`
- Reference: `src/workers/ci/handlers.py:102-167` (existing logic)

- [ ] **Step 1: Write failing test**

```python
# tests/test_run_lint.py
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "lint-and-test" / "scripts" / "run.py"

def test_unsupported_language_returns_ok_false(tmp_path):
    """A repo with neither pyproject nor package.json should yield ok=false, not crash."""
    (tmp_path / "README").write_text("hi")
    r = subprocess.run([sys.executable, str(SCRIPT), "--repo-path", str(tmp_path)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert "unsupported" in out["error"].lower()

def test_python_repo_runs_ruff_and_pytest(tmp_path):
    """A trivial python project with passing test — ok should be true."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\n'
    )
    (tmp_path / "test_x.py").write_text("def test_ok():\n    assert 1 == 1\n")
    r = subprocess.run([sys.executable, str(SCRIPT), "--repo-path", str(tmp_path)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["language"] == "python"
    assert out["test"]["passed"] is True
```

- [ ] **Step 2: Run — verify fail**

```bash
pytest tests/test_run_lint.py -v
```
Expected: FileNotFoundError on SCRIPT

- [ ] **Step 3: Implement `scripts/run.py`**

```python
#!/usr/bin/env python3
"""lint-and-test skill — execute ruff + pytest (Python) or npm lint + npm test (Node).

Args:
    --repo-path PATH   absolute path to checked-out repo (required)
    --commit-sha SHA   used for cache key (optional)
    --language LANG    auto | python | node (default: auto)

Output: single JSON object on stdout. Never raises (only platform errors do).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Make sibling _shared importable when symlinked into ~/.claude/skills/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _shared.subprocess_helper import run_subprocess, hash_inputs  # noqa: E402
import hashlib


def detect_language(repo: Path) -> str:
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        return "python"
    if (repo / "package.json").exists():
        return "node"
    return "unknown"


def run_python(repo: Path) -> dict:
    ruff = run_subprocess(["ruff", "check", "."], cwd=str(repo))
    lint_passed = ruff["exit_code"] == 0
    pytest_run = run_subprocess(
        ["pytest", "-q", "--no-header"], cwd=str(repo), timeout_s=300.0,
    )
    test_passed = pytest_run["exit_code"] == 0
    summary_match = re.search(r"(\d+ passed|\d+ failed|\d+ error)", pytest_run["stdout"])
    test_summary = summary_match.group(0) if summary_match else pytest_run["stdout"][-200:]
    return {
        "lint": {"tool": "ruff", "passed": lint_passed,
                 "exit_code": ruff["exit_code"],
                 "issues": ruff["stdout"].splitlines()[:50] if not lint_passed else [],
                 "duration_ms": ruff["duration_ms"]},
        "test": {"tool": "pytest", "passed": test_passed,
                 "exit_code": pytest_run["exit_code"],
                 "summary": test_summary,
                 "duration_ms": pytest_run["duration_ms"]},
        "language": "python",
        "ok": lint_passed and test_passed,
    }


def run_node(repo: Path) -> dict:
    lint = run_subprocess(["npm", "run", "lint", "--silent"], cwd=str(repo))
    test = run_subprocess(["npm", "test", "--silent"], cwd=str(repo))
    return {
        "lint": {"tool": "npm-run-lint", "passed": lint["exit_code"] == 0,
                 "exit_code": lint["exit_code"],
                 "issues": lint["stdout"].splitlines()[-30:],
                 "duration_ms": lint["duration_ms"]},
        "test": {"tool": "npm-test", "passed": test["exit_code"] == 0,
                 "exit_code": test["exit_code"],
                 "summary": test["stdout"][-200:],
                 "duration_ms": test["duration_ms"]},
        "language": "node",
        "ok": lint["exit_code"] == 0 and test["exit_code"] == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", required=True)
    ap.add_argument("--commit-sha", default="")
    ap.add_argument("--language", default="auto", choices=["auto", "python", "node"])
    args = ap.parse_args()

    repo = Path(args.repo_path).resolve()
    language = args.language
    if language == "auto":
        language = detect_language(repo)

    lockfile_h = ""
    for f in ("pyproject.toml", "uv.lock", "package-lock.json", "yarn.lock"):
        p = repo / f
        if p.exists():
            lockfile_h += hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    cache_key = hash_inputs([str(repo), args.commit_sha, language, lockfile_h])

    if language == "python":
        result = run_python(repo)
    elif language == "node":
        result = run_node(repo)
    else:
        result = {"ok": False, "error": f"unsupported language: {language}",
                  "language": language}

    result["cache_key"] = cache_key
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable + run test**

```bash
chmod +x skills/lint-and-test/scripts/run.py
pytest tests/test_run_lint.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add skills/lint-and-test/scripts/run.py tests/test_run_lint.py
git commit -m "feat(lint-and-test): extract handler logic into scripts/run.py"
```

---

### Task 1.3: Rewrite `lint-and-test/SKILL.md` as Claude playbook

**Files:**
- Modify: `skills/lint-and-test/SKILL.md` (full rewrite)

- [ ] **Step 1: Replace SKILL.md with playbook style**

```markdown
---
name: lint-and-test
description: Run the lint-then-test pipeline on a Python or Node repository at a specific commit and return a structured pass/fail report. Use this when the user asks to "lint and test", "run CI checks", "run pytest", "type-check with mypy", "run prettier and the unit tests", "make sure ruff is clean and tests pass", "ESLint + jest", or any combined static-check-plus-test request on a repository. For dependency CVE checks, use dependency-audit instead. For SAST or hard-coded-secret scans, use security-scan. For building or publishing artifacts, use build-and-release. Read-only.
allowed-tools: Bash(git clone:*), Bash(python skills/lint-and-test/scripts/run.py:*), Bash(./skills/lint-and-test/scripts/run.py:*), Bash(rm -rf /tmp/skill_sandbox/*)
---

# lint-and-test

Run the canonical lint + test pipeline on a repo checkout. This is a **read-only** skill — it never modifies the repo or any registry.

## When to use

Trigger when the user asks to lint+test a specific repository (URL or local path). Examples:
- "lint and test https://github.com/psf/black at v24.10.0"
- "run CI checks on this repo"
- "make sure ruff is clean and pytest passes for psf/requests"

If the user wants only one of lint OR test, this skill is still appropriate — it reports both independently.

## How to use

### Step 1 — get the repo onto disk

If the user gave a GitHub URL, clone it shallowly into a sandbox:

```bash
SANDBOX=/tmp/skill_sandbox/lint-test-$(date +%s)
git clone --depth=1 --branch <REF> <REPO_URL> $SANDBOX
```

If the user gave an existing local path, use it directly — skip the clone.

Reject anything that isn't `https://github.com/...` (no `file://`, `ssh://`, or other hosts).

### Step 2 — run the script

```bash
python skills/lint-and-test/scripts/run.py --repo-path $SANDBOX
```

Optional flags:
- `--language python|node|auto` (default `auto` — detects via `pyproject.toml` / `package.json`)
- `--commit-sha <sha>` (used for cache key only)

The script prints a single JSON object to stdout. Read it.

### Step 3 — interpret the result

```json
{
  "ok": true,
  "language": "python",
  "lint": { "tool": "ruff", "passed": true, "exit_code": 0, "issues": [], "duration_ms": 412 },
  "test": { "tool": "pytest", "passed": true, "exit_code": 0, "summary": "623 passed", "duration_ms": 18430 },
  "cache_key": "9a1f...c08"
}
```

`ok = lint.passed AND test.passed`. If `ok=false`, look at `lint.issues` (list of ruff lines) or `test.summary` (last 200 chars of pytest output) to tell the user why.

If `language == "unknown"` and `ok=false`, the repo has neither `pyproject.toml` nor `package.json` — tell the user lint-and-test doesn't apply to this repo type.

### Step 4 — clean up

```bash
rm -rf /tmp/skill_sandbox/lint-test-*
```

## Boundaries

- **Read-only.** Will never write to the repo, never push to a registry. For releases, use `build-and-release`.
- **No CVE checks.** For known vulnerabilities in dependencies, use `dependency-audit`.
- **No SAST.** For SQL injection / hardcoded secret detection, use `security-scan`.
- **No platform errors raised** — script always exits 0; check `result.ok` to branch.
- **Pytest timeout 300s.** If the repo's test suite exceeds this, `test.passed=false` with `timed_out=true`.
```

- [ ] **Step 2: Verify frontmatter parses (optional)**

```bash
python3 -c "
import yaml, pathlib, re
text = pathlib.Path('skills/lint-and-test/SKILL.md').read_text()
m = re.match(r'---\n(.*?)\n---\n', text, re.DOTALL)
fm = yaml.safe_load(m.group(1))
assert fm['name'] == 'lint-and-test'
assert 'allowed-tools' in fm
print('OK', fm['name'])
"
```
Expected: `OK lint-and-test`

- [ ] **Step 3: Commit**

```bash
git add skills/lint-and-test/SKILL.md
git commit -m "feat(lint-and-test): rewrite SKILL.md as Claude playbook (drop platform metadata)"
```

---

### Task 1.4 — 1.6: Same pattern for build-and-release / dependency-audit / security-scan

For each of the three skills, repeat the Task 1.2 + 1.3 pattern. Each gets its own task numbered 1.4 / 1.5 / 1.6.

**Source mapping** (where to extract logic from):
- `build-and-release` ← `src/workers/ci/handlers.py:171-244`
- `dependency-audit` ← `src/workers/ci/handlers.py:249-318`
- `security-scan` ← `src/workers/ci/handlers.py:323-446`

Each task has 5 steps: write failing test → verify fail → implement script → verify pass → commit.
Then 3 steps for SKILL.md rewrite: replace body → frontmatter parse check → commit.

**Per-skill playbook content checklist** (matches lint-and-test structure):
- Frontmatter: `name`, `description` (use existing description from current SKILL.md, already trigger-eval-tuned), `allowed-tools` (limited to `git clone`, the script, `rm -rf` of sandbox)
- Body sections: When to use · How to use (step 1 clone / step 2 run / step 3 interpret / step 4 cleanup) · Boundaries

**Per-script CLI signature** (consistent across all 4):
- `--repo-path PATH` required
- `--commit-sha SHA` optional, cache key only
- Skill-specific flags (e.g. `--target wheel|npm|docker --version --dry-run` for build, `--ecosystem` for audit, `--scan-types` for security)
- Output: single JSON object to stdout
- `disable-model-invocation: true` in `build-and-release` frontmatter only (per existing design — write skill, model must not auto-invoke)

**Test scaffolding per skill** (`tests/test_run_<name>.py`):
- 1 test for unsupported / missing-input case → expects `ok=false` with structured error
- 1 test for happy path on a synthesized tmp_path repo → expects `ok=true`

---

### Task 1.7: Local Claude Code smoke test

**Files:** none (env-level)

- [ ] **Step 1: Symlink each skill into `~/.claude/skills/`**

```bash
mkdir -p ~/.claude/skills
for skill in lint-and-test build-and-release dependency-audit security-scan; do
  ln -sfn /Users/kevinwei/src/interview_hw/skills/$skill ~/.claude/skills/$skill
done
ls -la ~/.claude/skills/ | grep -E "lint-and-test|build-and-release|dependency-audit|security-scan"
```
Expected: 4 symlinks pointing at our repo

- [ ] **Step 2: Open a fresh Claude Code session in a scratch dir, run a trigger prompt for each skill**

For each prompt, in Claude Code, observe whether Claude picks the right skill (`/skills` will list it; the prompt should auto-trigger).

| Prompt | Expected skill triggered |
|---|---|
| `lint and test https://github.com/octocat/Hello-World at master` | `lint-and-test` |
| `audit dependencies of psf/requests at v2.31.0 for CVEs` | `dependency-audit` |
| `run semgrep + gitleaks on https://github.com/octocat/Hello-World` | `security-scan` |
| `build a wheel for our repo, dry run` (in our repo) | `build-and-release` (gated, must be explicit) |

For each, screenshot or copy the Claude Code transcript into `prompts/2026-05-03-claude-code-smoke.md`.

- [ ] **Step 3: Document the smoke test**

Create `prompts/2026-05-03-claude-code-smoke.md` with the 4 transcripts (or paraphrased outcome if transcript export not available).

- [ ] **Step 4: Commit**

```bash
git add prompts/2026-05-03-claude-code-smoke.md
git commit -m "docs: claude code smoke test of 4 skills (transcripts)"
```

---

### Task 1.8: Agent SDK web shell — backend

**Files:**
- Create: `src/agent_shell/__init__.py`
- Create: `src/agent_shell/main.py`
- Create: `src/agent_shell/skill_loader.py`
- Create: `src/agent_shell/tool_runner.py`
- Create: `tests/test_skill_loader.py`

- [ ] **Step 1: Write failing test for skill_loader**

```python
# tests/test_skill_loader.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_shell.skill_loader import load_skills

def test_load_skills_returns_4_ci_skills():
    skills_dir = Path(__file__).resolve().parents[1] / "skills"
    tools = load_skills(skills_dir)
    names = [t["name"] for t in tools]
    assert set(names) >= {"lint-and-test", "build-and-release",
                          "dependency-audit", "security-scan"}
    for t in tools:
        assert "description" in t
        assert "input_schema" in t

def test_load_skills_skips_underscore_dirs():
    skills_dir = Path(__file__).resolve().parents[1] / "skills"
    tools = load_skills(skills_dir)
    names = [t["name"] for t in tools]
    assert "_shared" not in names
```

- [ ] **Step 2: Run — verify fail**

```bash
pytest tests/test_skill_loader.py -v
```
Expected: ModuleNotFoundError

- [ ] **Step 3: Implement `skill_loader.py`**

```python
# src/agent_shell/skill_loader.py
"""Scan skills/ → list of Anthropic tool definitions for the SDK."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


# Per-skill input schema. Hardcoded here (not derived from SKILL.md) because
# Anthropic SDK tool input_schema needs JSON Schema, not free-form Markdown.
_INPUT_SCHEMAS = {
    "lint-and-test": {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "GitHub URL or local path"},
            "ref": {"type": "string", "description": "branch/tag/sha", "default": "main"},
            "language": {"type": "string", "enum": ["auto", "python", "node"], "default": "auto"},
        },
        "required": ["repo"],
    },
    "build-and-release": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "ref": {"type": "string", "default": "main"},
            "target": {"type": "string", "enum": ["wheel", "npm", "docker"]},
            "version": {"type": "string"},
            "dry_run": {"type": "boolean", "default": True},
            "image_name": {"type": "string"},
        },
        "required": ["repo", "target", "version"],
    },
    "dependency-audit": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "ref": {"type": "string", "default": "main"},
            "ecosystems": {"type": "array", "items": {"type": "string"}, "default": []},
        },
        "required": ["repo"],
    },
    "security-scan": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "ref": {"type": "string", "default": "main"},
            "scan_types": {
                "type": "array",
                "items": {"type": "string", "enum": ["sast", "secrets", "container"]},
                "default": ["sast", "secrets"],
            },
            "image_name": {"type": "string"},
        },
        "required": ["repo"],
    },
}


def _read_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def load_skills(skills_dir: Path) -> list[dict]:
    """Return list of Anthropic tool definitions, one per skill folder."""
    tools = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = _read_frontmatter(skill_md)
        name = fm.get("name", child.name)
        tools.append({
            "name": name,
            "description": fm.get("description", ""),
            "input_schema": _INPUT_SCHEMAS.get(name, {"type": "object", "properties": {}}),
        })
    return tools
```

- [ ] **Step 4: Verify test passes**

```bash
pytest tests/test_skill_loader.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_shell/__init__.py src/agent_shell/skill_loader.py tests/test_skill_loader.py
git commit -m "feat(agent-shell): skill_loader scans skills/ → Anthropic tool defs"
```

- [ ] **Step 6: Implement `tool_runner.py`**

```python
# src/agent_shell/tool_runner.py
"""Execute a skill's scripts/run.py given Anthropic tool_use input."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills"))
from _shared.git_fetch import fetch_repo, GitFetchError  # noqa: E402
from _shared.subprocess_helper import run_subprocess  # noqa: E402


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


def run_skill(name: str, args: dict) -> dict:
    """Execute the skill named `name` with input `args`. Returns parsed JSON."""
    script = SKILLS_DIR / name / "scripts" / "run.py"
    if not script.exists():
        return {"ok": False, "error": f"skill {name!r} has no scripts/run.py"}

    repo_arg = args.get("repo", "")
    sandbox: Path | None = None
    try:
        if repo_arg.startswith("https://github.com/"):
            sandbox = Path(tempfile.mkdtemp(prefix="skill_sandbox_"))
            try:
                fetch_repo(repo_arg, args.get("ref", "main"), sandbox / "repo")
            except GitFetchError as exc:
                return {"ok": False, "error": str(exc)}
            repo_path = sandbox / "repo"
        else:
            repo_path = Path(repo_arg).resolve()

        cmd = [sys.executable, str(script), "--repo-path", str(repo_path)]
        for k, v in args.items():
            if k in ("repo", "ref"):
                continue
            if isinstance(v, bool):
                if v:
                    cmd.append(f"--{k.replace('_', '-')}")
            elif isinstance(v, list):
                if v:
                    cmd.extend([f"--{k.replace('_', '-')}", ",".join(map(str, v))])
            else:
                cmd.extend([f"--{k.replace('_', '-')}", str(v)])

        r = run_subprocess(cmd, timeout_s=600.0)
        if r["exit_code"] != 0:
            return {"ok": False, "error": "script crashed",
                    "stderr": r["stderr"][-500:]}
        try:
            return json.loads(r["stdout"])
        except json.JSONDecodeError:
            return {"ok": False, "error": "script did not emit JSON",
                    "stdout_tail": r["stdout"][-500:]}
    finally:
        if sandbox and sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
```

- [ ] **Step 7: Implement FastAPI `main.py`**

```python
# src/agent_shell/main.py
"""Anthropic Agent SDK web shell.

POST /chat with header `X-Anthropic-Key: sk-ant-...` and JSON body
{"messages": [...]} streams the conversation back as SSE events:
  - event: text  (model text delta)
  - event: tool_use  (Claude calling a skill)
  - event: tool_result (skill output)
  - event: done
"""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent_shell.skill_loader import load_skills
from agent_shell.tool_runner import run_skill

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
UI_DIR = REPO_ROOT / "ui"

app = FastAPI(title="Claude Skills CI/CD — Agent Shell")


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "claude-opus-4-7"


@app.post("/chat")
async def chat(req: ChatRequest, x_anthropic_key: str = Header(...)) -> StreamingResponse:
    if not x_anthropic_key.startswith("sk-ant-"):
        raise HTTPException(401, "invalid API key shape")

    client = anthropic.Anthropic(api_key=x_anthropic_key)
    tools = load_skills(SKILLS_DIR)

    async def gen():
        messages = list(req.messages)
        # Multi-turn loop: keep calling until model stops requesting tools.
        for _ in range(8):  # max 8 tool round-trips
            resp = client.messages.create(
                model=req.model,
                max_tokens=4096,
                tools=tools,
                messages=messages,
            )
            for block in resp.content:
                if block.type == "text":
                    yield f"event: text\ndata: {json.dumps({'text': block.text})}\n\n"
                elif block.type == "tool_use":
                    yield f"event: tool_use\ndata: {json.dumps({'name': block.name, 'input': block.input})}\n\n"
                    result = run_skill(block.name, block.input)
                    yield f"event: tool_result\ndata: {json.dumps({'name': block.name, 'result': result})}\n\n"
                    messages.append({"role": "assistant", "content": resp.content})
                    messages.append({"role": "user", "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }]})
                    break
            else:
                # No tool_use this turn — model is done.
                yield "event: done\ndata: {}\n\n"
                return
        yield "event: done\ndata: {\"warning\": \"max tool round-trips reached\"}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# UI mount (root → ui/index.html)
if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 8: Commit**

```bash
git add src/agent_shell/main.py src/agent_shell/tool_runner.py
git commit -m "feat(agent-shell): FastAPI /chat endpoint with SSE + per-request API key"
```

---

### Task 1.9: Chat UI

**Files:**
- Create: `ui/index.html`
- Create: `ui/app.js`
- Create: `ui/styles.css`

- [ ] **Step 1: Write `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Claude Skills CI/CD</title>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header>
  <h1>Claude Skills CI/CD</h1>
  <input id="api-key" type="password" placeholder="sk-ant-..." autocomplete="off">
  <small id="key-status">key required</small>
</header>
<aside id="skills">
  <h2>Skills</h2>
  <ul>
    <li><b>lint-and-test</b><br><span>ruff + pytest / npm lint+test</span></li>
    <li><b>build-and-release</b><br><span>wheel / npm / docker (gated)</span></li>
    <li><b>dependency-audit</b><br><span>pip-audit / npm-audit / OSV</span></li>
    <li><b>security-scan</b><br><span>semgrep + gitleaks (+ trivy)</span></li>
  </ul>
</aside>
<main>
  <div id="conversation"></div>
  <form id="chat-form">
    <textarea id="user-input" placeholder='lint and test https://github.com/octocat/Hello-World at master'></textarea>
    <button type="submit">Send</button>
  </form>
</main>
<script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `app.js`**

```javascript
// ui/app.js
const keyInput = document.getElementById("api-key");
const keyStatus = document.getElementById("key-status");
const form = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const convo = document.getElementById("conversation");

const stored = sessionStorage.getItem("anthropic_key");
if (stored) { keyInput.value = stored; keyStatus.textContent = "key set"; }

keyInput.addEventListener("change", () => {
  sessionStorage.setItem("anthropic_key", keyInput.value);
  keyStatus.textContent = keyInput.value ? "key set" : "key required";
});

const messages = [];

function addBlock(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  convo.appendChild(div);
  convo.scrollTop = convo.scrollHeight;
  return div;
}

function addTool(name, input) {
  const div = document.createElement("div");
  div.className = "tool-use";
  div.innerHTML = `<b>→ ${name}</b><pre>${JSON.stringify(input, null, 2)}</pre>`;
  convo.appendChild(div);
  return div;
}

function addToolResult(name, result) {
  const div = document.createElement("div");
  div.className = "tool-result";
  const ok = result.ok ? "✓" : "✗";
  div.innerHTML = `<b>${ok} ${name} result</b><pre>${JSON.stringify(result, null, 2)}</pre>`;
  convo.appendChild(div);
  return div;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = userInput.value.trim();
  if (!text) return;
  if (!keyInput.value) { alert("Enter API key first"); return; }

  addBlock("user", text);
  messages.push({ role: "user", content: text });
  userInput.value = "";

  const resp = await fetch("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Anthropic-Key": keyInput.value,
    },
    body: JSON.stringify({ messages }),
  });
  if (!resp.ok) {
    addBlock("error", `HTTP ${resp.status}`);
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let textBlock = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();
    for (const evt of events) {
      const lines = evt.split("\n");
      const type = lines.find(l => l.startsWith("event:"))?.slice(7);
      const data = lines.find(l => l.startsWith("data:"))?.slice(6);
      if (!type || !data) continue;
      const payload = JSON.parse(data);
      if (type === "text") {
        if (!textBlock) textBlock = addBlock("assistant", "");
        textBlock.textContent += payload.text;
      } else if (type === "tool_use") {
        textBlock = null;
        addTool(payload.name, payload.input);
      } else if (type === "tool_result") {
        addToolResult(payload.name, payload.result);
      } else if (type === "done") {
        textBlock = null;
      }
    }
  }
});
```

- [ ] **Step 3: Write `styles.css`**

```css
body { font-family: system-ui, sans-serif; margin: 0; display: grid;
       grid-template-columns: 200px 1fr; grid-template-rows: 50px 1fr; height: 100vh; }
header { grid-column: 1 / 3; background: #111; color: #eee; display: flex;
         align-items: center; padding: 0 16px; gap: 16px; }
header h1 { margin: 0; font-size: 1rem; }
header input { padding: 4px 8px; width: 280px; font-family: monospace; }
header small { opacity: 0.7; }
aside { background: #f4f4f4; padding: 12px; overflow-y: auto; }
aside ul { list-style: none; padding: 0; }
aside li { padding: 8px 0; border-bottom: 1px solid #ddd; font-size: 0.85rem; }
aside li span { color: #666; font-size: 0.75rem; }
main { display: flex; flex-direction: column; padding: 16px; }
#conversation { flex: 1; overflow-y: auto; }
.msg { padding: 8px 12px; margin: 4px 0; border-radius: 6px; max-width: 80%; }
.msg.user { background: #e3f2fd; margin-left: auto; }
.msg.assistant { background: #f1f8e9; }
.msg.error { background: #ffebee; color: #c62828; }
.tool-use, .tool-result { background: #fff3e0; border-left: 3px solid #ff9800;
                          padding: 8px; margin: 4px 0; font-size: 0.85rem; }
.tool-result { border-left-color: #4caf50; }
pre { white-space: pre-wrap; word-break: break-word; margin: 4px 0 0; }
form { display: flex; gap: 8px; }
textarea { flex: 1; height: 60px; font-family: inherit; padding: 8px; }
button { padding: 0 24px; background: #1976d2; color: white; border: none; cursor: pointer; }
```

- [ ] **Step 4: Manual smoke test**

```bash
cd /Users/kevinwei/src/interview_hw
$(conda info --base)/envs/hw/bin/python -m uvicorn agent_shell.main:app --reload --port 8000 --app-dir src
```
Open `http://localhost:8000`, paste your `sk-ant-...` key, type `lint and test https://github.com/octocat/Hello-World at master`, observe:
- skill list visible left
- text streaming in
- tool_use block (`lint-and-test` with input)
- tool_result block (JSON, `ok`, language=`unknown` since Hello-World has neither pyproject nor package.json)
- final assistant text summarizing

- [ ] **Step 5: Commit**

```bash
git add ui/index.html ui/app.js ui/styles.css
git commit -m "feat(ui): vanilla chat UI with sessionStorage API key"
```

---

### Task 1.10: End-to-end real-repo verification

**Files:**
- Create: `evals/agent-shell-e2e/scenarios.md` (manual log)

- [ ] **Step 1: Run all 8 scenarios from spec, log results**

For each row, type the prompt in the running UI, observe outputs, write the actual result + any deviations into the markdown log.

| # | Prompt | Expected |
|---|---|---|
| 1 | `lint and test https://github.com/psf/black at 24.10.0` | tool_use lint-and-test, tool_result ok=true (or actual lint issues) |
| 2 | (Same prompt again) | tool_use again — confirm script-level `cache_key` matches between runs |
| 3 | `audit deps of https://github.com/psf/requests at main` | tool_use dependency-audit, ecosystems_detected=["python"] |
| 4 | `run semgrep + gitleaks on https://github.com/psf/requests at main` | tool_use security-scan, scan_types_run includes semgrep+gitleaks |
| 5 | `build a wheel for https://github.com/octocat/Hello-World at master, version 0.1.0, dry run` | tool_use build-and-release, ok=false because no pyproject.toml — verify graceful fail |
| 6 | `lint and test https://gitlab.com/foo/bar` | tool_result ok=false, error="only https://github.com/ URLs allowed" |
| 7 | `lint and test https://github.com/does/not/exist at main` | tool_result ok=false, error contains git stderr |
| 8 | `lint and test https://github.com/octocat/Hello-World at master` | tool_result ok=false, language=unknown — silent failure caught |

- [ ] **Step 2: Capture transcript / screenshot per scenario**

Save under `evals/agent-shell-e2e/<scenario-N>.json` (paste full chat).

- [ ] **Step 3: Commit**

```bash
git add evals/agent-shell-e2e/
git commit -m "eval: e2e agent shell — 8 scenarios on real repos"
```

---

### Task 1.11: Archive abandoned platform code

**Files:**
- Move: `src/gateway/` → `archive/platform-prototype/src/gateway/`
- Move: `src/workers/base.py` → `archive/platform-prototype/src/workers/base.py`
- Move: `src/workers/ci/__main__.py` → `archive/platform-prototype/src/workers/ci/__main__.py`
- Move: `src/workers/ci/handlers.py` → `archive/platform-prototype/src/workers/ci/handlers.py`
- Move: `src/shared/db.py` → `archive/platform-prototype/src/shared/db.py`
- Move: `migrations/` → `archive/platform-prototype/migrations/`
- Create: `archive/platform-prototype/README.md`

- [ ] **Step 1: Move files**

```bash
mkdir -p archive/platform-prototype/src/{gateway,workers/ci,shared}
git mv src/gateway archive/platform-prototype/src/gateway
git mv src/workers/base.py archive/platform-prototype/src/workers/base.py
git mv src/workers/ci/__main__.py archive/platform-prototype/src/workers/ci/__main__.py
git mv src/workers/ci/handlers.py archive/platform-prototype/src/workers/ci/handlers.py
git mv src/shared/db.py archive/platform-prototype/src/shared/db.py
git mv migrations archive/platform-prototype/migrations
```

- [ ] **Step 2: Write archive README**

```markdown
# Archived: platform prototype (Days 1, 5)

Initial direction was a Postgres-backed FastAPI platform that hosted skills as
HTTP services. After re-reading the brief on 2026-05-03 we pivoted to standard
Claude Code Skills (`SKILL.md` + `scripts/run.py`) so that Claude — not our
router — triggers them. Anthropic Agent SDK web shell at `src/agent_shell/`
provides the deployable demo the brief asks for.

The handler logic in `src/workers/ci/handlers.py` here was not lost — its
subprocess + parsing code was extracted into `skills/<name>/scripts/run.py`.

These files are kept for git-history transparency about what we tried and
abandoned. Not used at runtime.
```

- [ ] **Step 3: Update top-level `pyproject.toml` to drop archived modules from package**

```bash
# In pyproject.toml, change:
#   packages = ["src/gateway", "src/workers", "src/shared"]
# to:
#   packages = ["src/agent_shell"]
# (uses Edit tool — exact replacement)
```

- [ ] **Step 4: Run all tests to confirm nothing depends on archived code**

```bash
pytest tests/ -v --ignore=tests/test_align.py --ignore=tests/test_manifest_scanner.py
```
Expected: lint/audit/scan/build tests + skill_loader test all pass. Old platform tests (`test_align`, `test_manifest_scanner`) will be skipped — they belong to archived code and will be filter-repo'd out in Phase 2.

- [ ] **Step 5: Commit**

```bash
git add archive/ pyproject.toml src/
git commit -m "refactor: archive platform prototype after pivot to Claude Code Skills"
```

---

## Phase 2 — Three-repo split with `git filter-repo`

> Run from a **fresh clone** to avoid mutating the working tree. Each repo gets its own clone-and-filter pass.

### Task 2.1: Map files → repos

| Path | claude-skills-cicd | browser-agent | sec-10k-extractor |
|---|---|---|---|
| `skills/_shared/` | ✓ | – | – |
| `skills/lint-and-test/` `build-and-release/` `dependency-audit/` `security-scan/` | ✓ | – | – |
| `skills/browser-task/` | – | ✓ | – |
| `skills/sec-extract-10k/` | – | – | ✓ |
| `skills/hello/` | ✓ (smoke skill) | – | – |
| `src/agent_shell/` | ✓ | – | – |
| `src/workers/browser/` | – | ✓ | – |
| `src/workers/extractor/` | – | – | ✓ |
| `src/shared/` (llm.py, retry.py — minus db.py archived) | duplicate to all 3 | duplicate to all 3 | duplicate to all 3 |
| `ui/` | ✓ | – | – |
| `evals/skill-trigger/` | ✓ | – | – |
| `evals/browser-tasks/` | – | ✓ | – |
| `evals/sec-extraction/` | – | – | ✓ |
| `evals/agent-shell-e2e/` | ✓ | – | – |
| `tests/test_run_*.py test_git_fetch test_skill_loader` | ✓ | – | – |
| `tests/test_browser_*.py` | – | ✓ | – |
| `tests/test_*` (extraction-related — align/cover_page/era/iou/llm_*/regex_*/retry/segment_*/xbrl_*/classifier/eval_runner) | – | – | ✓ |
| `tests/test_ci_handlers.py test_manifest_scanner.py` | drop (refer to archived code) | – | – |
| `archive/platform-prototype/` | drop entirely (filter-repo) | – | – |
| `docs/per-task/task1-*.md task2-task3-orchestration-decision.md` | ✓ | – | – |
| `docs/per-task/task2-*.md` | – | ✓ | – |
| `docs/per-task/task3-*.md` | – | – | ✓ |
| `docs/research/`, `docs/design/` | duplicate to all 3 (origin reference) | duplicate to all 3 | duplicate to all 3 |
| `prompts/` | filter to T1-relevant | filter to T2-relevant | filter to T3-relevant |
| `pyproject.toml` | new, scoped | new, scoped | new, scoped |
| `README.md` | new (replaces mono README) | new | new |
| `LICENSE` | MIT new | MIT new | MIT new |
| `.env.example` | new (skill-relevant only) | new | new |
| `tasks/lessons.md` | duplicate (cross-cutting) | duplicate | duplicate |
| `CLAUDE.md` | duplicate | duplicate | duplicate |
| `migrations/` | drop | drop | drop |

- [ ] **Document this map in plan only — no commit needed.**

---

### Task 2.2: Split #1 — `claude-skills-cicd`

**Files:** none in source tree (filter-repo runs on a fresh clone)

- [ ] **Step 1: Fresh clone**

```bash
cd /tmp
rm -rf split-cicd
git clone https://github.com/Kevinweisl/whaleforceAI split-cicd
cd split-cicd
```

- [ ] **Step 2: Run filter-repo to keep only Task 1 paths**

```bash
git filter-repo \
  --path skills/_shared \
  --path skills/lint-and-test \
  --path skills/build-and-release \
  --path skills/dependency-audit \
  --path skills/security-scan \
  --path skills/hello \
  --path src/agent_shell \
  --path src/shared \
  --path ui \
  --path evals/skill-trigger \
  --path evals/agent-shell-e2e \
  --path-glob 'tests/test_run_*.py' \
  --path tests/test_git_fetch.py \
  --path tests/test_skill_loader.py \
  --path docs/design \
  --path docs/research \
  --path docs/per-task/task1-skills-platform.md \
  --path docs/per-task/task2-task3-orchestration-decision.md \
  --path docs/superpowers \
  --path tasks/lessons.md \
  --path CLAUDE.md \
  --invert-paths --path archive
```

(Note: filter-repo treats two passes here — first the path keep-list, then `--invert-paths` to additionally drop archive even if it sneaks in. If filter-repo errors on combining, run twice: once with the keep list, then `git filter-repo --path archive --invert-paths` separately.)

- [ ] **Step 3: Verify history**

```bash
git log --oneline | head -20
git log --all --pretty=format:"%ai %s" | head -10
```
Expected: real dates (Apr 30 – May 3) preserved. Empty commits dropped automatically.

- [ ] **Step 4: Author / committer pass-through**

filter-repo defaults to keeping author + committer. No action needed unless we want to anonymize.

- [ ] **Step 5: Add the 3 new files (LICENSE, README, scoped pyproject)**

Copy LICENSE (MIT), write a fresh `README.md` for this repo, write a scoped `pyproject.toml`. Commit with author date matching today (May 3) — that's accurate, the split happened today.

```bash
# LICENSE — standard MIT, year 2026, copyright "Kevin Wei"
# README.md — see Task 2.5 template below
# pyproject.toml — see Task 2.6 template below
git add LICENSE README.md pyproject.toml
git commit -m "chore: claude-skills-cicd repo bootstrap (LICENSE + README + scoped pyproject)"
```

- [ ] **Step 6: Push to private repo**

```bash
git remote add origin https://github.com/Kevinweisl/claude-skills-cicd.git
git push -u origin main
```

- [ ] **Step 7: Verify**

```bash
gh repo view Kevinweisl/claude-skills-cicd --web
```
Open in browser, confirm: 4 skills present, README rendering, no platform/archive directories, commit dates Apr 30 – May 3.

---

### Task 2.3: Split #2 — `browser-agent`

Same pattern as Task 2.2, with these path changes:

- Keep paths:
  - `skills/browser-task` (if exists — it's a Task 2 skill)
  - `src/workers/browser`
  - `src/shared` (subset: llm.py, retry.py)
  - `evals/browser-tasks`
  - `tests/test_browser_*.py`
  - `tests/test_llm_*.py` `tests/test_retry.py` `tests/test_classifier.py` (browser uses these)
  - `docs/per-task/task2-browser-agent.md`
  - `docs/design`, `docs/research`
  - `tasks/lessons.md`, `CLAUDE.md`
  - `prompts/` (T2-relevant subset — filter manually post-clone if needed)
- Drop: `archive/`, `skills/_shared` (redundant for T2), `migrations/`

```bash
cd /tmp
rm -rf split-browser
git clone https://github.com/Kevinweisl/whaleforceAI split-browser
cd split-browser
git filter-repo \
  --path skills/browser-task \
  --path src/workers/browser \
  --path src/shared \
  --path evals/browser-tasks \
  --path-glob 'tests/test_browser_*.py' \
  --path-glob 'tests/test_llm_*.py' \
  --path tests/test_retry.py \
  --path tests/test_classifier.py \
  --path docs/per-task/task2-browser-agent.md \
  --path docs/design \
  --path docs/research \
  --path tasks/lessons.md \
  --path CLAUDE.md
```

Add LICENSE / README / scoped pyproject, push to `Kevinweisl/browser-agent`.

---

### Task 2.4: Split #3 — `sec-10k-extractor`

Same pattern, with these paths:

- Keep:
  - `skills/sec-extract-10k`
  - `src/workers/extractor`
  - `src/shared`
  - `evals/sec-extraction`
  - `tests/test_align.py` `test_cover_page.py` `test_era.py` `test_iou.py` `test_llm_*.py` `test_xbrl_check.py` `test_regex_segment.py` `test_segment_trim.py` `test_retry.py` `test_classifier.py` `test_eval_runner.py`
  - `docs/per-task/task3-llm-threshold-decision.md`
  - `docs/design`, `docs/research`
  - `tasks/lessons.md`, `CLAUDE.md`

```bash
cd /tmp
rm -rf split-sec
git clone https://github.com/Kevinweisl/whaleforceAI split-sec
cd split-sec
git filter-repo \
  --path skills/sec-extract-10k \
  --path src/workers/extractor \
  --path src/shared \
  --path evals/sec-extraction \
  --path tests/test_align.py \
  --path tests/test_cover_page.py \
  --path tests/test_era.py \
  --path tests/test_iou.py \
  --path-glob 'tests/test_llm_*.py' \
  --path tests/test_xbrl_check.py \
  --path tests/test_regex_segment.py \
  --path tests/test_segment_trim.py \
  --path tests/test_retry.py \
  --path tests/test_classifier.py \
  --path tests/test_eval_runner.py \
  --path docs/per-task/task3-llm-threshold-decision.md \
  --path docs/design \
  --path docs/research \
  --path tasks/lessons.md \
  --path CLAUDE.md
```

Add LICENSE / README / scoped pyproject, push to `Kevinweisl/sec-10k-extractor`.

---

### Task 2.5: README template (per-repo)

Each repo gets its own `README.md` written from scratch (NOT a copy of the mono README). Contents:

1. **One-line tagline** + status badge (e.g. private/coming-soon)
2. **What this is** (3-4 sentences for a non-context reader)
3. **Why it exists** (origin: AI Coding Test 2026 — interview deliverable)
4. **Quick start** (real shell commands, copy-paste runnable)
5. **Demo** (Zeabur URL once deployed, otherwise screenshot)
6. **Skills this contains** (for `claude-skills-cicd`: 4 skills with descriptions)
7. **Architecture** (1 ASCII diagram)
8. **Evaluation results** (link to evals/, paste headline numbers)
9. **AI collaboration notes** (link to `prompts/`, mention Claude Code skills used)
10. **License** (MIT)

Writing this is part of Task 2.2 step 5 (cicd), 2.3 step 5 (browser), 2.4 step 5 (sec). Each takes ~30 min.

---

### Task 2.6: Scoped `pyproject.toml` per repo

#### claude-skills-cicd

```toml
[project]
name = "claude-skills-cicd"
version = "0.1.0"
description = "4 reusable Claude Code skills for GitHub CI/CD + Anthropic Agent SDK web shell"
requires-python = ">=3.12"
dependencies = [
  "anthropic>=0.40",
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pyyaml>=6.0",
  "pydantic>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "ruff>=0.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_shell"]
sources = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["src", "skills"]
```

#### browser-agent

```toml
[project]
name = "browser-agent"
version = "0.1.0"
description = "Generic browser automation agent with self-correction (Playwright + Claude)"
requires-python = ">=3.12"
dependencies = [
  "playwright>=1.49",
  "anthropic>=0.40",
  "openai>=1.50",
  "httpx>=0.27",
  "tenacity>=8.5",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/workers/browser", "src/shared"]
sources = ["src"]
```

#### sec-10k-extractor

```toml
[project]
name = "sec-10k-extractor"
version = "0.1.0"
description = "Item-level structured extraction from SEC 10-K filings (rules + LLM + XBRL hybrid)"
requires-python = ">=3.12"
dependencies = [
  "edgartools>=5.30",
  "lxml>=5.3",
  "openai>=1.50",
  "httpx>=0.27",
  "tenacity>=8.5",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/workers/extractor", "src/shared"]
sources = ["src"]
```

---

## Phase 3 — Verification

### Task 3.1: Per-repo verification matrix

For each of the three new repos, fresh-clone and verify:

- [ ] **Step 1: Clone fresh**

```bash
cd /tmp
gh repo clone Kevinweisl/<repo>
cd <repo>
```

- [ ] **Step 2: Run tests**

```bash
$(conda info --base)/envs/hw/bin/python -m pip install -e ".[dev]"
pytest -v
```
Expected: all tests pass. (For T1 cicd, the 4 run_*, git_fetch, skill_loader tests.)

- [ ] **Step 3: Verify no platform leakage**

```bash
test ! -d archive/ && echo "no archive ok"
test ! -d src/gateway/ && echo "no gateway ok"
test ! -d migrations/ && echo "no migrations ok"
```

- [ ] **Step 4: Verify commit dates span real timeline**

```bash
git log --pretty=format:"%ai" | sort | uniq -c
```
Expected: counts on dates from Apr 30 to May 3, not all on May 3.

- [ ] **Step 5: For claude-skills-cicd only, run agent shell end-to-end**

```bash
$(conda info --base)/envs/hw/bin/python -m uvicorn agent_shell.main:app --port 8000 --app-dir src
```
Open `http://localhost:8000`, paste API key, run scenario 1 from Task 1.10. Expected: same outcome.

---

### Task 3.2: Update memory + lessons

**Files:**
- Modify: `/Users/kevinwei/.claude/projects/-Users-kevinwei-src-interview-hw/memory/MEMORY.md`
- Add new memory file documenting the pivot

- [ ] **Step 1: Add a new project memory file**

```markdown
# .../memory/project_pivot_2026_05_03.md
---
name: Task 1 pivot — Claude Code Skills (2026-05-03)
description: Pivot from custom Postgres-FastAPI platform to standard Claude Code Skills + Agent SDK web shell after re-reading brief
type: project
---

On 2026-05-03 we re-read the brief and pivoted Task 1: from a custom HTTP
"Skills Platform" (Postgres queue, gateway, workers) to standard Claude Code
Skills (`SKILL.md` playbook + `scripts/run.py`). Reason: brief literally says
"Claude Skills" + recommends kaochenlong tutorial, and "description triggered by
Claude" means by the Claude model, not by our router.

What stayed: handler logic (lifted into `scripts/run.py`), token redaction,
git-fetch URL guard.

What's new: Anthropic Agent SDK web shell (`src/agent_shell/`) — user supplies
their own API key in UI (sessionStorage); nothing persists server-side.

Repo split: mono-repo `whaleforceAI` split into 3 private repos under
`Kevinweisl` (`claude-skills-cicd` / `browser-agent` / `sec-10k-extractor`).

How to apply: when discussing Task 1, the deliverable is the 4 standard Claude
Code skills, not a platform. The Zeabur demo is the Agent SDK shell.
```

- [ ] **Step 2: Add pointer to MEMORY.md index**

```markdown
- [Task 1 pivot 2026-05-03](project_pivot_2026_05_03.md) — Pivoted to standard Claude Code Skills + Agent SDK shell; mono-repo split into 3 private repos
```

- [ ] **Step 3: Update lessons.md if needed**

Add a brief lesson: "Re-read brief at every major design decision — we missed 'Claude Code Skills' literal meaning on first pass."

---

## Self-Review Checklist

- ✅ Spec coverage: each section in `2026-05-03-task1-ui-design.md` ... wait, that spec is now stale (UI design assumed platform). Plan supersedes spec. **No spec→plan gap because plan replaces spec.**
- ✅ No placeholders: every step has actual command / actual code.
- ✅ Type consistency: `_INPUT_SCHEMAS` keys match SKILL.md `name` fields; `tool_runner.run_skill` calls `skills/{name}/scripts/run.py` matching the actual paths.
- ✅ Order: Phase 1 finishes inside `interview_hw`, then Phase 2 splits — this avoids running filter-repo on a tree that's still being modified.

## Open question for the user

- **Real timeline preservation**: this plan keeps original commit dates from filter-repo (Apr 30 – May 2). The new pivot commits get today's date (May 3). That's the *real* timeline — pivot really did happen today. Confirm this is what you want; if you'd rather backdate the pivot work to look like it happened across more days, say so before Phase 1 starts (we'd use `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` to spread commits across May 1-3).

---

## Time estimate

| Phase | Time |
|---|---|
| Phase 0 setup | 0.3h |
| Phase 1 (Tasks 1.1 – 1.11) | 7h |
| Phase 2 (3 splits) | 2h |
| Phase 3 verification + memory | 1h |
| **Total** | **~10.5h** |
