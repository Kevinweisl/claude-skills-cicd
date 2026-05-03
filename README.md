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

## Quick start — install in Claude Code

The fastest way to try a skill is to symlink it into `~/.claude/skills/` and use Claude Code as you normally would:

```bash
git clone https://github.com/Kevinweisl/claude-skills-cicd
cd claude-skills-cicd
mkdir -p ~/.claude/skills
for s in lint-and-test build-and-release dependency-audit security-scan; do
  ln -sfn "$(pwd)/skills/$s" ~/.claude/skills/$s
done
```

Now in any Claude Code session, prompts like *"lint and test https://github.com/psf/black at v24.10.0"* will trigger the skill, which clones the repo and runs ruff + pytest in a sandbox.

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

## Skill design notes

Each of the four skills demonstrates a deliberately different pattern:

| Skill | Pattern |
|---|---|
| `lint-and-test`     | Multi-tool pipeline (ruff + pytest) under one boundary because they share install/cache |
| `build-and-release` | Side-effecting write skill with `disable-model-invocation: true` (Claude must be explicitly asked) and content-addressed digest for idempotency |
| `dependency-audit`  | Multi-ecosystem auto-routing (python/node/rust/go) with normalised vulnerability output |
| `security-scan`     | Parallel ensemble (Semgrep + Bandit + gitleaks + trivy) with severity-weighted dedup and token-shape redaction on every output |

## Evaluation

`evals/skill-trigger/` contains the trigger-eval harness. The 7-skill scope (4 here + 3 sibling skills from the original mono-repo) intentionally tests **disambiguation** — does Claude correctly pick `dependency-audit` for "scan my deps for CVEs" vs. `security-scan` for "find SQL injection in our handlers"? The two are semantically adjacent but require different scanners.

Last run: **TPR=1.0, FPR=0.0** on all 7 skills after 5 rounds of description tuning. See `evals/skill-trigger/last_run.json`.

`evals/agent-shell-e2e/` contains 8 deterministic real-repo scenarios that cover the happy paths plus URL guard, nonexistent repo, idempotent re-runs, and unsupported language. All 8 behave per spec; see `scenario-*.json`.

The remaining piece — Claude actually picking the right skill from natural-language prompts in the UI — needs an Anthropic API key, so it's documented as a manual checklist in `evals/agent-shell-e2e/manual-checklist.md`.

## AI collaboration notes

This repo was built with Claude Code. Major prompts and design decisions are preserved in `prompts/` and `docs/`. Notably, after writing the platform-style implementation we re-read the brief, realised "Claude Skills" meant the literal feature, and pivoted in `docs/superpowers/plans/2026-05-03-task1-pivot-and-repo-split.md`. The pre-pivot code is in `archive/platform-prototype/` for transparency.

## License

MIT — see `LICENSE`.
