# claude-skills-cicd web demo

Browser shell for trying the 4 CI/CD skills without installing Claude Code locally.

```text
You     : audit deps of https://github.com/octocat/Hello-World
Claude  : (picks `dependency-audit`, clones the repo, runs pip-audit)
          (SSE stream shows tool call, JSON result, then chat summary)
Claude  : No Python dependency files found in this repo.
```

**Bring your own Anthropic API key.** It lives only in the browser's `sessionStorage` and is forwarded as a request header on each `/chat` call. The FastAPI server never persists or logs it.

The skills themselves live one folder up in [`../skills/`](../skills/) and run anywhere something can shell out to a Python script. **This folder is just the demo wrapper.** For native Claude Code install (the recommended path), see the [top-level README](../README.md).

## Quick start

```bash
# from the repo root
pip install -e ".[dev]"
python -m uvicorn agent_shell.main:app --port 8000 --app-dir src
```

Open <http://localhost:8000>, paste your `sk-ant-...` key into the top bar, then try:

- `lint and test https://github.com/psf/requests at main`
- `audit deps of https://github.com/octocat/Hello-World`
- `run semgrep + gitleaks on https://github.com/psf/requests`

You'll see Claude pick a skill, the tool call, and the structured JSON result, all streamed in real time.

## Why a web shell?

The 4 skills already work natively inside Claude Code. The web shell exists for three reasons:

1. **No-install demo path.** An evaluator without Claude Code on their machine can still try the skills with just an API key.
2. **Observable security boundary.** URL guard, sandbox creation, and redaction all show up directly in the SSE stream. Useful for verifying the security claims rather than trusting them blind.
3. **Realistic deployment shape.** Mirrors how a real product would actually expose these skills behind an API instead of a local CLI.

## Architecture

```
┌────────────────┐    SSE     ┌──────────────────────────────────────┐
│ ui/ (vanilla)  │◀──────────▶│ src/agent_shell/main.py (FastAPI)    │
│ - chat panel   │   POST     │   /chat   : Anthropic SDK            │
│ - sk-ant-* in  │   /chat    │   /skills : sidebar metadata         │
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

Three boundaries this path enforces:

- **Claude orchestrates.** Picks the skill, summarises the JSON result for the user. Never wields the subprocess directly.
- **`tool_runner.py` is the security boundary.** Only `https://github.com/` URLs accepted. Clones go into `/tmp/skill_sandbox_*`. Cleanup guaranteed.
- **`scripts/run.py` is the deterministic actor.** One JSON object on stdout, never raises on tool failure.

`tool_runner.py` also holds a process-local idempotency cache (5-minute TTL): identical `(skill, input)` calls served from memory without re-cloning. Side-effecting `build-and-release` invocations with `--no-dry-run` are exempt because re-pushing may be the user's actual intent.

## What's in this folder

| File | What it is |
|---|---|
| `index.html` | Chat panel + sidebar + API-key input |
| `app.js`     | SSE client. Key lives in `sessionStorage` and is sent as `X-Anthropic-Key`. |
| `styles.css` | Vanilla CSS, no framework |

Backend code (FastAPI app, tool runner, skill loader) is in [`../src/agent_shell/`](../src/agent_shell/).

## Manual eval checklist

Full 8-prompt evaluator script (happy paths, URL guard, unsupported language, idempotent re-runs, `disable-model-invocation` gate) is in [`../evals/agent-shell-e2e/manual-checklist.md`](../evals/agent-shell-e2e/manual-checklist.md).
