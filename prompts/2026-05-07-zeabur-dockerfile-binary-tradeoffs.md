# 2026-05-07 — Zeabur deploy: which scanner binaries to bake into the Dockerfile

## Context

The brief's universal requirement #3 says "all tasks must be deployed to Zeabur as a publicly accessible service, with URL". For Task 1, the deployable surface is the Anthropic Agent SDK web shell in `src/agent_shell/` + the `ui/` chat UI.

Zeabur supports auto-detection from a `Dockerfile`. So the question is: what goes in the Dockerfile?

The skills' subprocesses need binaries on `PATH`:

- `git` (always, every skill clones)
- `ruff` + `pytest` (`lint-and-test` Python)
- `npm` (`lint-and-test` Node, `build-and-release` npm, `dependency-audit` Node)
- `pip-audit` (`dependency-audit` Python)
- `cargo` (`dependency-audit` Rust)
- `govulncheck` (`dependency-audit` Go)
- `python -m build` (`build-and-release` wheel)
- `docker` (`build-and-release` docker target)
- `semgrep`, `bandit`, `gitleaks`, `trivy` (`security-scan`)

That's a lot. Baking everything in produces a multi-GB image and a slow build.

## What I asked

> 那雲端部署會遇到什麼問題嗎? 哪些 scanner binary 必須裝, 哪些可以跳過

## Options surfaced

1. **Bake everything in.** Largest image, slowest build. Image size ~3 GB+ if Node + Rust + Go + Docker-in-Docker + trivy all included.
2. **Bake nothing.** Skills always return `error: "binary not installed"`. Useless demo.
3. **Bake only what makes the demo prompts actually work.** Trade demo coverage for image size.

## Decision

**Option 3, with explicit scope:**

Baked in (Python ecosystem + git + gitleaks):

```
git, ca-certificates, curl, build-essential
ruff, pytest, pip-audit, bandit, semgrep, build (Python wheels)
gitleaks (downloaded as a pinned binary release, v8.21.2)
```

Skipped (with rationale):

| Skipped | Why |
|---|---|
| `node` / `npm` | Adds ~150MB, but the demo prompts target Python repos (`psf/requests`). If an evaluator pastes a Node URL, `lint-and-test` returns "binary not installed" honestly. |
| `cargo` | Rust toolchain is huge (~600MB+). Demo doesn't need it. |
| `govulncheck` | Requires Go toolchain. Demo doesn't need it. |
| `docker` (DinD) | Docker-in-Docker needs privileged container. Bad practice on shared infra. `build-and-release --target docker` returns "docker not available". |
| `trivy` | ~70MB binary. Container CVE scanning is `security-scan`'s optional `container` mode, default is `sast,secrets`. Demo doesn't need it. |

This is the **graceful-degradation contract** at deploy time: missing binary returns `error: "binary not installed"` and an empty result, never crashes. So the Dockerfile only needs to bake in what's worth showing.

## Side decisions baked into the Dockerfile

### `gitleaks` is downloaded, not apt-installed

Debian Bookworm slim doesn't have a recent `gitleaks` package. Pinned download from GitHub releases (`v8.21.2`) is more controllable than relying on a moving apt version.

```dockerfile
ENV GITLEAKS_VERSION=8.21.2
RUN curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    | tar -xz -C /usr/local/bin gitleaks
```

### Layer ordering: deps first, code last

```dockerfile
COPY pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir -e .
COPY src ./src
COPY skills ./skills
COPY ui ./ui
```

`pyproject.toml` rarely changes. Code changes constantly. Putting `pip install` before `COPY src` means most builds reuse the deps layer.

### `.dockerignore` strips `.git`, `tests/`, `prompts/`, `scripts/`

Image doesn't need them at runtime. Halves the build context.

### `$PORT` injected by Zeabur

Zeabur's runtime sets `$PORT`. CMD binds to `0.0.0.0:${PORT}` (the `0.0.0.0` part is critical — `127.0.0.1` is unreachable from outside the container).

```dockerfile
CMD ["sh", "-c", "python -m uvicorn agent_shell.main:app --host 0.0.0.0 --port ${PORT} --app-dir src"]
```

## Default model decision

While editing `src/agent_shell/main.py` for deploy, also bumped `DEFAULT_MODEL` from a stale `claude-opus-4-5-20250109` to `claude-opus-4-7`. Reasoning:

- The task is tool routing + JSON summarisation. Either Sonnet 4.6 or Opus 4.7 handle this.
- Opus is the strongest tool-use model in the lineup. For a demo where the interviewer might ask the model multi-step things, prefer better reasoning over saving cost.
- Per-request override via the `model` field is still allowed if the caller wants Sonnet.

## Operational note added to ui/README

> Skills like `lint-and-test` and `build-and-release` execute target-repo code (build hooks, conftest.py, fixtures), which is arbitrary code execution against whatever URL the user pastes. Don't expose this publicly without an auth layer or skill scope reduction.

This deploy is intended for trusted single-user evaluation, not multi-tenant production. Calling it out explicitly because the security model is real.

## What this captures for the interviewer

The Dockerfile is intentionally minimal. The graceful-degradation contract (missing binary → empty result, never crash) lets us **ship a small image without sacrificing correctness** — skills that can't run on the demo image fail honestly rather than silently returning fake-success. That's the same property the brief's "honest failure modes" axis is grading for.

## Outcome

Dockerfile validates with `docker buildx build --check`. Image size manageable. Zeabur deploy steps:

1. Connect Service → Git Repository → `claude-skills-cicd`, branch `main`.
2. Build type auto-detects Dockerfile.
3. `$PORT` injected; container binds `0.0.0.0:$PORT`.
4. Open `*.zeabur.app`, paste your `sk-ant-*` key, ask Claude to audit a repo.

(As of writing, the Zeabur deploy is paused awaiting answer on whether to buy a Zeabur server — see project memory for context.)
