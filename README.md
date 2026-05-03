# claude-skills-cicd

4 reusable [Claude Code skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills) for GitHub CI/CD, plus an Anthropic Agent SDK web shell that demos them on real GitHub repos in the browser.



## What's in here

| Path | What it is |
|---|---|
| `skills/lint-and-test/`     | ruff + pytest (Python) / npm lint + npm test (Node) |
| `skills/build-and-release/` | wheel / npm tarball / docker image (gated, dry-run by default) |
| `skills/dependency-audit/`  | pip-audit / npm-audit / cargo-audit / govulncheck (CVE scan) |
| `skills/security-scan/`     | Semgrep + Bandit + gitleaks + (optional) trivy (SAST + secrets) |
| `skills/_shared/`           | Helpers (subprocess, redact, git-fetch URL guard) |
| `src/agent_shell/`          | FastAPI backend that exposes the skills to Claude via the Anthropic SDK |
| `ui/`                       | Vanilla-JS chat UI (sessionStorage API key) |
| `evals/skill-trigger/`      | Trigger-eval harness — quantifies whether each skill's `description` makes Claude pick it correctly. Last run: TPR=1.0, FPR=0.0 across 7 skills (the 4 here + 3 sibling skills used for disambiguation testing). |
| `evals/agent-shell-e2e/`    | 8 real-repo end-to-end scenarios (clone → script → JSON parse) |

## Prerequisites

- Python 3.12+
- `git` on `PATH` (the skills shallow-clone target repos)
- The actual scanner binaries are **all optional** — each skill detects them at runtime and reports `error: "binary not installed"` instead of crashing. So you only need what you actually want to use:
  - `lint-and-test` → `ruff` + `pytest` (Python repos), or `npm` (Node repos)
  - `build-and-release` → `python -m build` (wheels), `npm pack` (npm), `docker` (images)
  - `dependency-audit` → any of `pip-audit` / `npm` / `cargo audit` / `govulncheck`
  - `security-scan` → any of `semgrep` / `bandit` / `gitleaks` / `trivy`

## Quick start — install in Claude Code

The fastest way to try a skill is to symlink it into `~/.claude/skills/` and use Claude Code as you normally would:

```bash
git clone https://github.com/Kevinweisl/claude-skills-cicd
cd claude-skills-cicd
mkdir -p ~/.claude/skills
for s in lint-and-test build-and-release dependency-audit security-scan; do
  ln -sfn "$(pwd)/skills/$s" ~/.claude/skills/$s
done

# Verify install
ls -l ~/.claude/skills/   # should show 4 symlinks pointing into this repo
```

Now in any Claude Code session, prompts like *"lint and test https://github.com/psf/black at v24.10.0"* will trigger the skill, which clones the repo and runs ruff + pytest in a sandbox.

## Smoke test — does it work?

Open a fresh Claude Code session and paste each prompt below. These are the same 4 scenarios used in `evals/agent-shell-e2e/scenario-*.json`, so you know exactly what to expect:

| # | Paste this prompt | What you should see | What it proves |
|---|---|---|---|
| 1 | `lint and test https://github.com/octocat/Hello-World at master` | Triggers `lint-and-test`. Returns `ok=false, language=unknown, error="unsupported language: unknown (no pyproject.toml or package.json found)"` | Clone + URL guard + graceful failure on unrecognised repos |
| 2 | `audit deps of https://github.com/psf/requests at main` | Triggers `dependency-audit`. Returns `ok=true, ecosystems_detected=["python"]` plus a `findings_by_ecosystem.python.vulnerabilities` list (count varies with current advisories) | Multi-ecosystem auto-detect; OSV/GHSA lookup |
| 3 | `scan https://github.com/psf/requests for SAST and secrets` | Triggers `security-scan`. Returns `ok=true, scan_types_run=["semgrep","gitleaks"], secrets_redacted_in_output=true` plus a `findings` array | Parallel scanners + token-shape redaction (any leaked credential is replaced by `<redacted-N>` before reaching Claude) |
| 4 | `build a wheel for https://github.com/octocat/Hello-World, version 0.1.0` | **Claude should pause and ask for explicit confirmation** ("This will publish to a registry — are you sure?") instead of running. Only after you say yes does the skill fire (and even then, it dry-runs by default). | The marquee design choice: `build-and-release` is a side-effecting write, so `disable-model-invocation: true` blocks auto-trigger. If Claude fires it without asking, the safety boundary is broken. |

Try the same prompt twice in a row — the second call returns `_cache_hit: true` from the in-memory idempotency cache (5-minute TTL), skipping the clone + subprocess entirely. `build-and-release` with `--no-dry-run` is exempt because re-pushing on demand is sometimes the user's actual intent.

## Quick start — run the web demo

The Agent SDK web shell lets you (or an evaluator) try the skills in a browser without installing Claude Code. **Bring your own Anthropic API key** — it lives only in the browser's `sessionStorage` and is forwarded as a request header; the server never persists or logs it.

```bash
pip install -e ".[dev]"
python -m uvicorn agent_shell.main:app --port 8000 --app-dir src
```

Open `http://localhost:8000`, paste your `sk-ant-...` key into the top bar, then ask Claude things like:

- "lint and test https://github.com/psf/requests at main"
- "audit deps of https://github.com/octocat/Hello-World"
- "run semgrep + gitleaks on /path/to/local/repo"

You'll see Claude pick the right skill, the tool call, and the structured JSON result, in real-time SSE.

## Architecture

```
┌────────────────┐    SSE     ┌──────────────────────────────────────┐
│ ui/ (vanilla)  │◀──────────▶│ src/agent_shell/main.py (FastAPI)    │
│ - chat panel   │   POST     │   /chat — Anthropic SDK              │
│ - sk-ant-* in  │   /chat    │   /skills — sidebar metadata         │
│   sessionStg.  │            │   /health                            │
└────────────────┘            └──────────────────┬───────────────────┘
                                                 │ tool_use
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │ src/agent_shell/tool_runner  │
                                  │  - URL guard                 │
                                  │  - shallow git clone sandbox │
                                  │  - argparse translation      │
                                  └──────────────┬───────────────┘
                                                 │ subprocess
                                                 ▼
                              ┌──────────────────────────────────────┐
                              │ skills/<name>/scripts/run.py         │
                              │  ruff/pytest, build, audit, scan     │
                              │  → emits one JSON object on stdout   │
                              └──────────────────────────────────────┘
```

Three boundaries:
- **Claude does orchestration** (chooses skill, summarises JSON for the user). It never wields the actual subprocess directly.
- **`tool_runner` is the security boundary** — only `https://github.com/` URLs accepted; sandbox confined to `/tmp/skill_sandbox_*`; cleanup guaranteed.
- **`scripts/run.py` is deterministic** — one JSON object on stdout, never raises on tool failure (only on missing `--repo-path`).

`tool_runner` also holds a **process-local idempotency cache** (5-minute TTL): identical `(skill, input)` calls served from memory without re-cloning. Side-effecting `build-and-release` invocations with `--no-dry-run` are exempt because re-pushing may be the user's actual intent.

## Skill design notes

Each of the four skills demonstrates a deliberately different pattern:

| Skill | Pattern |
|---|---|
| `lint-and-test`     | Multi-tool pipeline (ruff + pytest) under one boundary because they share install/cache |
| `build-and-release` | Side-effecting write skill with `disable-model-invocation: true` (Claude must be explicitly asked) and content-addressed digest for idempotency |
| `dependency-audit`  | Multi-ecosystem auto-routing (python/node/rust/go) with normalised vulnerability output |
| `security-scan`     | Parallel ensemble (Semgrep + Bandit + gitleaks + trivy) with severity-weighted dedup and token-shape redaction on every output |

## Evaluation

Three layers, deliberately stacked from cheap-and-deterministic to expensive-and-realistic:

### 1. Per-skill trigger eval (NIM K=3 vote, 140 queries)

`evals/skill-trigger/` quantifies whether each skill's `description` makes Claude pick it correctly. The 7-skill scope (4 here + 3 sibling skills from the original mono-repo) intentionally tests **disambiguation** — does Claude correctly pick `dependency-audit` for "scan my deps for CVEs" vs. `security-scan` for "find SQL injection in our handlers"? The two are semantically adjacent but require different scanners.

**Last run: TPR=1.0, FPR=0.0** on all 7 skills after 5 rounds of description tuning. See `evals/skill-trigger/last_run.json`.

### 2. Cross-domain ambiguity (NIM K=3 vote, 10 queries)

The trigger eval above scores per-skill clarity. The ambiguity layer scores **decomposition**: when a prompt genuinely spans 2+ skills (`"lint, test, then audit our deps"`), does Claude pick *one* defensible first call?

**Last run: 10/10 strict majority pass, 10/10 lenient (any-voter) pass.** See `evals/skill-trigger/last_ambiguity_run.json` and `cost_report_ambiguity.md`.

### 3. End-to-end on real repos (no LLM, deterministic)

`evals/agent-shell-e2e/` contains 8 real-repo scenarios that cover happy paths plus URL guard, nonexistent repo, idempotent re-runs, and unsupported language. All 8 behave per spec; see `scenario-*.json`.

### Cost / latency

Aggregated by `evals/skill-trigger/analyze_last_run.py` from saved runs (no live LLM calls). The 140-query eval consumed an estimated ~378K tokens (~$0.17 USD) at 99.3% K-voter unanimity; the 10-query ambiguity batch cost ~$0.017 USD. See `cost_report_140q.md` / `cost_report_ambiguity.md`.

### What's left as manual

The one piece that **can't be automated** is Claude actually picking the right skill from natural-language prompts in the UI — that needs an Anthropic API key (which by design lives only in the evaluator's browser sessionStorage, never on the server). The 8-prompt checklist is in `evals/agent-shell-e2e/manual-checklist.md`.

## AI collaboration notes

This repo was built with Claude Code. Major prompts and design decisions are preserved in `prompts/` and `docs/`. Notably, after writing the platform-style implementation we re-read the brief, realised "Claude Skills" meant the literal feature, and pivoted in `docs/superpowers/plans/2026-05-03-task1-pivot-and-repo-split.md`. The pre-pivot code is in `archive/platform-prototype/` for transparency.

## License

MIT — see `LICENSE`.
