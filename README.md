# claude-skills-cicd

## Live demo

**https://claude-skills-cicd-kevin.zeabur.app**

Bring your own `sk-ant-*` Anthropic key (browser-side, never persisted server-side; see [`ui/README.md`](ui/README.md) for the BYOK threat model). Type a request like "audit deps of https://github.com/psf/requests at main" and the matching skill streams output token-by-token over SSE.

---

Pre-release sanity-checking a repo today usually looks like this:

```bash
ruff check . && pytest          # lint + test
pip-audit                       # CVE check
semgrep --config=auto .         # SAST
gitleaks detect                 # secret scan
python -m build                 # try a wheel build
```

Five tools, five output formats, no common schema. With Claude Code and the 4 skills in this repo loaded, the same workflow becomes one sentence:

```text
You     : audit my deps for known vulnerabilities
Claude  : (picks `dependency-audit`, reads $PWD, detects Python, runs pip-audit)
Claude  : Found 0 known CVEs in the Python deps.
```

The 4 skills cover **lint + test**, **build + release**, **dependency audit**, and **SAST + secret scan**. They install natively in Claude Code via the plugin marketplace (see [Quick start](#quick-start)). The same 4 skills are also exposed through a small Anthropic Agent SDK web shell in [`ui/`](ui/README.md) (FastAPI + vanilla JS, SSE streaming): a fully functional alternative path for trying them in a browser without Claude Code, or as a reference for deploying skills as a web service. The two paths share the same `scripts/run.py` actors but have a few intentional behavioural differences documented in [`ui/README.md`](ui/README.md#differences-from-native-claude-code).

## How you'd actually use this

Two scenarios. The first is the primary path; the second is occasionally useful.

**Scenario A: you're working in your own repo.**

```text
~/work/my-app$ claude
> lint and test this codebase
> audit my deps
> scan our handlers for SQL injection
```

The skills default to `$PWD`. No clone, no network. They validate that the directory is a git checkout and run scanners directly against the working tree, including any uncommitted changes.

**Scenario B: you want to inspect a third-party repo without cloning it yourself.**

```text
> audit deps of https://github.com/psf/requests at main
```

Pass a `https://github.com/...` URL. The skill shallow-clones into `/tmp/skill_sandbox_*`, runs the scanner, and removes the sandbox in a `finally` block.

> **Web shell exception:** the [`ui/`](ui/README.md) demo has no concept of `$PWD` (the FastAPI server is somewhere else), so it always uses the URL flow. Web shell is for evaluators or "try without installing Claude Code" scenarios.

## The 4 skills

Each skill is a deliberate design study, not just a different scanner.

| Skill | What it does | Design highlight |
|---|---|---|
| `lint-and-test`     | ruff + pytest (Python) or npm lint + npm test (Node) on the repo. | Multi-tool pipeline. Lint and test share install/cache state, so they sit under one skill. |
| `build-and-release` | wheel / npm tarball / docker image. Dry-run by default; never pushes unless `--no-dry-run` is set. | Side-effecting write skill. Frontmatter sets `disable-model-invocation: true`, so Claude won't fire it from a soft natural-language ask. Human gate is the safety boundary. |
| `dependency-audit`  | CVE scan via pip-audit / npm audit / cargo audit / govulncheck. Auto-detects ecosystem from lock files. | Multi-ecosystem auto-routing with one normalised output schema. Caller doesn't need to know the repo's language. |
| `security-scan`     | Parallel SAST + secret scan: semgrep + bandit + gitleaks + (optional) trivy. | Parallel ensemble with severity-weighted dedup. Token-shape redaction (PAT, AWS, JWT, ...) applied to every output before it reaches Claude. |

## Quick start

This repo ships as a [Claude Code plugin marketplace](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces). Inside any Claude Code session:

```text
/plugin marketplace add Kevinweisl/claude-skills-cicd
/plugin install claude-skills-cicd@cicd-skills
```

Then run `/reload-plugins` (or restart the session). The 4 skills are now usable two ways:

1. **Plain English.** Claude picks the right skill from each `SKILL.md` description. Example: `audit my deps`
2. **Namespaced slash form** (bypass description routing):
   - `/claude-skills-cicd:lint-and-test`
   - `/claude-skills-cicd:build-and-release`
   - `/claude-skills-cicd:dependency-audit`
   - `/claude-skills-cicd:security-scan`

What you'll need installed:

| Requirement | Why |
|---|---|
| Python 3.12+, `git` | The skill scripts are Python; clones use git. Both already present in most dev environments. |
| Scanner binaries (`ruff`, `pip-audit`, `semgrep`, ...) | Install only what you'll actually use. Missing ones don't crash; the skill output includes an `install_hint` field naming the exact command (e.g. `pip install pip-audit`, `brew install gitleaks`) so Claude can suggest it back to you. Per-skill list in [FAQ Q4](#q4-which-scanner-binaries-do-i-need-to-install). |

> Other install paths (manual file copy, local `--plugin-dir` for hacking on a skill) and other gotchas live in the [FAQ](#faq) at the bottom.

## Smoke test

`cd` into any Python or Node git checkout (the skills default to `$PWD`). Open Claude Code there, then paste each prompt below.

### 1. Lint + test the current repo

```text
lint and test this repo
```

- **Triggers**: `lint-and-test`
- **Reads**: `$PWD` (no clone, no network)
- **Returns**: `ok=true, language="python", lint.passed=true/false, test.summary="..."` (or `language="unknown"` if neither `pyproject.toml` nor `package.json` exist)
- **Proves**: cwd resolution, `.git/` guard, graceful unsupported-language path

### 2. CVE audit on the current repo

```text
audit my deps for known vulnerabilities
```

- **Triggers**: `dependency-audit`
- **Reads**: `$PWD` manifests (`pyproject.toml`, `package-lock.json`, `Cargo.lock`, `go.sum`)
- **Returns**: `ok=true, ecosystems_detected=[...]` plus `findings_by_ecosystem.<eco>.vulnerabilities`. If a scanner binary is missing, that ecosystem reports `error: "binary not installed"` and an empty list (graceful degradation).
- **Proves**: multi-ecosystem auto-detect, OSV/GHSA lookup, honest reporting when scanners are missing

### 3. SAST + secrets on the current repo

```text
scan this codebase for SAST findings and leaked secrets
```

- **Triggers**: `security-scan`
- **Reads**: `$PWD` source files
- **Returns**: `ok=true, scan_types_run=["semgrep","gitleaks"], secrets_redacted_in_output=true, tokens_redacted_count=N` plus a `findings` array
- **Proves**: parallel scanners + token-shape redaction. Any leaked credential is replaced by `<redacted-N>` before reaching Claude.

### 4. Write skill stays gated

```text
build a wheel and ship version 1.2.3
```

- **Expected**: Claude should NOT fire the skill. `build-and-release` ships with `disable-model-invocation: true`, so Claude either declines, asks for explicit confirmation, or tells you to invoke it manually with `/claude-skills-cicd:build-and-release`.
- **Proves**: the headline design choice. A side-effecting write skill is human-gated. If Claude fires it without asking, the safety boundary is broken.

### Optional: scan a third-party GitHub repo without cloning yourself

```text
audit deps of https://github.com/psf/requests at main
```

The same skill picks up the `https://github.com/...` URL, shallow-clones into `/tmp/skill_sandbox_*`, runs the audit, and cleans the sandbox up. URL guard rejects anything not `https://github.com/`.

> Repeating any prompt within 5 minutes returns `_cache_hit: true` from the in-memory idempotency cache. No re-clone, no re-run.

## Skill internals

Every skill is the same two-piece shape:

- `SKILL.md`: YAML frontmatter (description, allowed-tools, gates) + playbook prose. This is what Claude reads at routing time.
- `scripts/run.py`: a small Python script. This is what actually executes when Claude invokes the skill.

Three contracts hold regardless of how a skill is invoked (Claude Code native, the [web shell](ui/README.md), or a plain `python` call):

1. **Repo resolution is uniform.** Each `scripts/run.py` accepts `--repo-path` (default: `$PWD`) or `--repo-url`. The shared `_shared/repo_resolver.py` handles both: cwd flow validates `.git/` exists; URL flow shallow-clones into a `/tmp/skill_sandbox_*` and returns a cleanup callback that the skill calls in `finally`.
2. **Deterministic JSON output.** `scripts/run.py` emits exactly one JSON object on stdout. It never raises on tool failure. Claude can rely on parsing the result.
3. **Universal guardrails in `skills/_shared/`.** Clones restricted to `https://github.com/`. Secret-shaped tokens (GitHub PAT, AWS key, Anthropic key, NIM key, JWT) replaced with `<redacted-N>` before any output reaches Claude.

For the web-shell-specific architecture (FastAPI + `tool_runner.py` sandbox + idempotency cache), see [`ui/README.md`](ui/README.md#architecture).

## Security boundaries

Layered defense. No single guard carries the whole load.

| Boundary | Where it lives | What it prevents |
|---|---|---|
| URL guard (primary) | `skills/_shared/git_fetch.py` rejects anything not `https://github.com/` | SSRF, `file://` exfiltration, ssh-keyless host pivots |
| URL guard (secondary) | `src/agent_shell/tool_runner.py` re-checks before calling the script | Defense in depth; web shell layer that can't be bypassed by editing a skill script |
| `.git/` guard | `skills/_shared/repo_resolver.py` checks the resolved cwd path | Stops accidental scans of `~/Downloads/` and similar non-repo directories |
| Sandbox isolation | URL flow uses `tempfile.mkdtemp(prefix="skill_sandbox_")` + `try/finally` cleanup | Per-invocation isolation; cleanup guaranteed even if the script crashes |
| Token-shape redaction | `skills/_shared/redact.py`, applied before any output is emitted | Prevents secret-scan output from leaking the secrets it just found back into LLM context |
| Write-skill gate | `build-and-release/SKILL.md` sets `disable-model-invocation: true` | Side-effecting operations cannot be auto-fired by Claude from a soft natural-language ask |
| Dry-run default | `build-and-release/scripts/run.py` requires explicit `--no-dry-run` to push | Even on explicit invocation, the default is build-without-push |
| BYOK in browser | `ui/app.js` keeps `sk-ant-*` in `sessionStorage`, sends as `X-Anthropic-Key` header | Web-shell server never persists, logs, or sees the key in storage |

## Evaluation

Three layers, from cheap and deterministic to slow and realistic.

### 1. Per-skill trigger eval (NIM K=3 vote, 140 queries)

Quantifies whether each skill's `description` makes Claude pick it correctly. Scope is 7 skills (the 4 here + 3 sibling skills from the original mono-repo) and tests **disambiguation**: does Claude correctly pick `dependency-audit` for *"scan my deps for CVEs"* vs. `security-scan` for *"find SQL injection in our handlers"*? Semantically adjacent, different scanners.

**Last run: TPR=1.0, FPR=0.0** on all 7 skills after 5 rounds of description tuning. See `evals/skill-trigger/last_run.json`.

### 2. Cross-domain ambiguity (NIM K=3 vote, 10 queries)

The trigger eval scores per-skill clarity. The ambiguity layer scores **decomposition**: when a prompt genuinely spans 2+ skills (`"lint, test, then audit our deps"`), does Claude pick *one* defensible first call?

**Last run: 10/10 strict majority pass, 10/10 lenient (any-voter) pass.** See `evals/skill-trigger/last_ambiguity_run.json` and `cost_report_ambiguity.md`.

### 3. End-to-end on real repos (no LLM, deterministic)

`evals/agent-shell-e2e/` contains 8 real-repo scenarios covering happy paths, URL guard, nonexistent repo, idempotent re-runs, and unsupported language. All 8 behave per spec; see `scenario-*.json`.

### Cost / latency

Aggregated by `evals/skill-trigger/analyze_last_run.py` from saved runs (no live LLM calls):

| Run | Queries | Tokens (est.) | Cost (est.) | K-voter unanimity |
|---|---|---|---|---|
| Per-skill eval | 140 | ~378K | ~$0.17 USD | 99.3% |
| Ambiguity eval |  10 | ~38K  | ~$0.017 USD | 100% |

Reports: `cost_report_140q.md` / `cost_report_ambiguity.md`.

### What's left as manual

Claude actually picking the right skill from natural-language prompts in the UI cannot be automated. It needs an Anthropic API key, which by design lives only in the evaluator's browser sessionStorage, never on the server. The 8-prompt checklist is in `evals/agent-shell-e2e/manual-checklist.md`.

## What's in here

| Path | What it is |
|---|---|
| `.claude-plugin/plugin.json`     | Plugin manifest. Makes this repo a Claude Code plugin. |
| `.claude-plugin/marketplace.json` | Marketplace catalog. Makes this repo addable via `/plugin marketplace add`. |
| `skills/lint-and-test/`     | `SKILL.md` + `scripts/run.py` for the lint + test skill |
| `skills/build-and-release/` | `SKILL.md` + `scripts/run.py` for the build skill (write-gated) |
| `skills/dependency-audit/`  | `SKILL.md` + `scripts/run.py` for the CVE audit skill |
| `skills/security-scan/`     | `SKILL.md` + `scripts/run.py` for the SAST + secret scan skill |
| `skills/_shared/`           | Helpers reused by all 4 skills (subprocess wrapper, token-shape redaction, github-only git fetch, cwd-or-URL repo resolver) |
| `src/agent_shell/`          | FastAPI backend that exposes the skills to Claude via the Anthropic SDK (powers the `ui/` web demo) |
| `ui/`                       | Vanilla-JS chat UI for the web demo. See [`ui/README.md`](ui/README.md). |
| `evals/skill-trigger/`      | Trigger-eval harness (NIM K=3 vote) |
| `evals/agent-shell-e2e/`    | 8 real-repo end-to-end scenarios (clone → script → JSON parse) |
| `Dockerfile`, `.dockerignore` | Container build for the web shell. Ready to deploy on Zeabur, Render, Fly.io, or any platform that auto-detects Dockerfiles. |

## AI collaboration notes

This repo was built with Claude Code. Major prompts and design decisions are preserved in [`prompts/`](prompts/README.md): one file per non-trivial decision, written as *what was asked → options surfaced → what we picked → why → outcome*.

## FAQ

### Q1. How do I install without the plugin marketplace?

Copy the skill folders directly into your local skills directory:

```bash
git clone https://github.com/Kevinweisl/claude-skills-cicd
cd claude-skills-cicd
mkdir -p ~/.claude/skills
cp -r skills/lint-and-test skills/build-and-release skills/dependency-audit skills/security-scan ~/.claude/skills/
ls ~/.claude/skills/      # should list the 4 skill folders
```

Skills installed this way are not namespaced. They're just `lint-and-test`, `build-and-release`, etc. Trade-off: shorter names, but no version pinning, no `/plugin update`, and no isolation from other plugins that might use the same skill name.

### Q2. How do I hack on a skill locally without (re)installing every time?

Use Claude Code's `--plugin-dir` flag:

```bash
git clone https://github.com/Kevinweisl/claude-skills-cicd
cd claude-skills-cicd
claude --plugin-dir .
```

Run `/reload-plugins` after each edit and the changes pick up immediately.

### Q3. Why doesn't `build-and-release` fire when I ask Claude to "ship a wheel"?

By design. `build-and-release` ships with `disable-model-invocation: true` in its `SKILL.md` frontmatter, so Claude is told *not* to call it from a soft natural-language prompt. To actually run it:

- Invoke `/claude-skills-cicd:build-and-release` explicitly, or
- Be very explicit in chat (e.g. *"run the build-and-release skill on this repo"*). Claude will still typically ask for confirmation.

See [The 4 skills](#the-4-skills) and [Security boundaries](#security-boundaries) for the rationale.

### Q4. Which scanner binaries do I need to install?

Only the ones for the skills you'll actually use. Each skill detects its tools at runtime; if a binary is missing, the skill returns an `install_hint` field with the exact install command instead of crashing. Claude reads it and suggests the command back to you in chat.

| Skill | Required binaries | Install hint |
|---|---|---|
| `lint-and-test`     | `ruff` + `pytest` (Python repos), or `npm` (Node repos) | `pip install ruff pytest` / install Node.js |
| `build-and-release` | `python -m build` (wheels), `npm pack` (npm), `docker` (images) | `pip install build twine` / `brew install --cask docker` |
| `dependency-audit`  | any of `pip-audit` / `npm` / `cargo audit` / `govulncheck` | `pip install pip-audit` / `cargo install cargo-audit` / `go install golang.org/x/vuln/cmd/govulncheck@latest` |
| `security-scan`     | any of `semgrep` / `bandit` / `gitleaks` / `trivy`         | `pip install semgrep bandit` / `brew install gitleaks aquasecurity/trivy/trivy` |

The skill scripts themselves need Python 3.12+ and `git`, both usually already present.

The full hint table lives in `skills/_shared/subprocess_helper.py::INSTALL_HINTS`. Why a `/setup` skill isn't included: cross-platform package management (brew vs apt vs scoop, conda vs venv vs system Python) is brittle to automate; surfacing per-tool install hints in the skill output gives Claude enough context to suggest the right command without a fragile installer skill.

### Q5. I don't have Claude Code installed at all. Can I still demo this?

Yes. The same 4 skills are also exposed through a small Anthropic Agent SDK web shell. Bring your own `sk-ant-*` key and try them in a browser. See [`ui/README.md`](ui/README.md) for setup, or deploy the bundled `Dockerfile` to any container platform.

### Q6. What gets scanned: my whole working tree, or only committed code?

Whatever is on disk in `$PWD`. The skills do not consult `git status` or filter by HEAD. Local edits, untracked files, and `.gitignore`'d artifacts are all visible to scanners. This is intentional: when you ask Claude to "scan this codebase", you usually mean "what I'm working on right now", not "what I've already committed". Use the `--repo-url` flow if you specifically want to inspect a clean ref.

## License

MIT. See `LICENSE`.
