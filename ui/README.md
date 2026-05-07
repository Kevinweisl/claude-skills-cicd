# claude-skills-cicd web demo

Browser shell for trying the 4 CI/CD skills without installing Claude Code locally.

```text
You     : audit deps of https://github.com/psf/requests
Claude  : (picks `dependency-audit`, clones the repo, runs pip-audit)
          (SSE stream shows tool call, JSON result, then chat summary)
Claude  : Found 0 known CVEs in the Python deps.
```

**Bring your own Anthropic API key.** It lives only in the browser's `sessionStorage` and is forwarded as a request header on each `/chat` call. The FastAPI server never persists or logs it.

The skills themselves live one folder up in [`../skills/`](../skills/) and run anywhere something can shell out to a Python script. **This folder is just the demo wrapper.** For native Claude Code install (the recommended path), see the [top-level README](../README.md).

## Differences from native Claude Code

The web shell runs the **same** 4 skills (same `SKILL.md` descriptions, same `scripts/run.py` actors) via the Anthropic Agent SDK, but two things behave differently from a native Claude Code session:

### 1. URL-only repo input (no `$PWD`)

Native Claude Code defaults to running each skill against `$PWD` (your current working directory). The web shell **cannot** do that: the FastAPI server is a different machine from your laptop, and `$PWD` on the server is meaningless to you. So the web shell always uses the URL flow:

- The user's prompt must include a `https://github.com/...` URL.
- `tool_runner.py` shallow-clones the repo into `/tmp/skill_sandbox_*`.
- The skill runs against the clone.
- The sandbox is removed in a `finally` block.

If you want skills to operate on your local working tree (with uncommitted changes visible), use Claude Code natively per the [top-level README](../README.md).

### 2. `disable-model-invocation` is not enforced here

`build-and-release` ships with `disable-model-invocation: true` in its `SKILL.md` frontmatter. Native Claude Code reads that flag and refuses to fire the skill from a soft natural-language prompt; only an explicit `/claude-skills-cicd:build-and-release` slash invocation will run it.

The web shell does **not** read this flag. `src/agent_shell/skill_loader.py` exposes all 4 skills as Anthropic SDK tools, and the SDK itself has no concept of `disable-model-invocation`. So in a web-shell session, Claude can decide to call `build-and-release` from a soft prompt like *"ship version 2.4.0"*.

Mitigations that are still in place:

- **Dry-run by default.** `build-and-release` runs with `no_dry_run=false` unless the schema field is explicitly set to true. So even when fired, it builds the artifact and computes a digest without pushing.
- **Schema hint in the tool definition.** The `no_dry_run` field's description is `"set to true ONLY when user explicitly asks to actually push"`, which gives Claude a prompt-layer hint to refuse implicit pushes.
- **Registry credentials are not present in the container by default.** Even if `no_dry_run=true` is set, `twine upload` / `npm publish` / `docker push` will fail without credentials, and the deploy guidance in this folder explicitly warns against putting registry tokens in the Zeabur env.

Net: a release will not silently happen via the web shell, but the human-gate boundary is one layer thinner than on native Claude Code. Worth knowing if you're doing the security walkthrough.

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

## Why a web shell at all?

The 4 skills already work natively inside Claude Code. The web shell exists for three reasons:

1. **No-install demo path.** An evaluator without Claude Code on their machine can still try the skills with just an Anthropic API key.
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
                                  │  - idempotency cache (5min)  │
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

- **Claude orchestrates.** Picks the skill from each `SKILL.md` description, summarises the JSON result for the user. Never wields the subprocess directly.
- **`tool_runner.py` is the security boundary.** Only `https://github.com/` URLs accepted (re-checks even though `_shared/git_fetch.py` also guards). Clones go into `/tmp/skill_sandbox_*`. Cleanup guaranteed via `try/finally`.
- **`scripts/run.py` is the deterministic actor.** One JSON object on stdout, never raises on tool failure. Token-shape redaction applied before output is emitted.

### Idempotency cache

`tool_runner.py` holds a process-local idempotency cache: identical `(skill, sorted_kwargs)` calls served from memory without re-cloning, with a 5-minute TTL.

- **Cache hit** sets `_cache_hit: true` on the result.
- **`build-and-release` with `--no-dry-run` is excluded.** Re-pushing on demand is sometimes the user's actual intent, not a redundant call.

The cache is per process. On a single-instance deployment that's effectively cluster-wide; on multi-worker / multi-instance setups, treat it as a per-worker optimisation rather than a shared store.

### Default model

`src/agent_shell/main.py` defaults to `claude-opus-4-7` (the strongest tool-routing + JSON summarisation in the lineup). Callers can override per request via the `model` field in the POST body.

## What's in this folder

| File | What it is |
|---|---|
| `index.html` | Chat panel + sidebar + API-key input |
| `app.js`     | SSE client. Key lives in `sessionStorage` and is sent as `X-Anthropic-Key`. |
| `styles.css` | Vanilla CSS, no framework |

Backend code (FastAPI app, tool runner, skill loader) is in [`../src/agent_shell/`](../src/agent_shell/).

## Deploy

The repo root ships with a `Dockerfile` that bundles the FastAPI app + the in-image scanner binaries (git, ruff, pytest, pip-audit, bandit, semgrep, gitleaks, python-build). `Node`, `Rust`, `Go`, `docker`, and `trivy` are intentionally skipped to keep the image small; the corresponding skill output gracefully reports `error: "binary not installed"` rather than crashing.

Any container platform that auto-detects Dockerfiles works. Zeabur is the path the manifests are tuned for:

1. Zeabur Dashboard → Connect Service → Git Repository → `Kevinweisl/claude-skills-cicd`, branch `main`.
2. Build type auto-detects Dockerfile.
3. `$PORT` is injected by Zeabur. The container binds `0.0.0.0:$PORT`.
4. Open the assigned `*.zeabur.app` URL, paste your `sk-ant-*` key, ask Claude something.

Same flow works on Render, Railway, Fly.io, or Cloud Run with no Dockerfile changes.

> **Operational note.** This deployment shape is intended for trusted single-user evaluation. Skills like `lint-and-test` and `build-and-release` execute target-repo code (build hooks, conftest.py, fixtures), which is arbitrary code execution against whatever URL the user pastes. Don't expose this publicly without an auth layer or skill scope reduction.

## Manual eval checklist

Full 8-prompt evaluator script (happy paths, URL guard, unsupported language, idempotent re-runs, `disable-model-invocation` gate) is in [`../evals/agent-shell-e2e/manual-checklist.md`](../evals/agent-shell-e2e/manual-checklist.md).
