# 2026-05-07: Cwd-first invocation, skills default to `$PWD`, URL becomes opt-in

## Context

Until 2026-05-07, every `scripts/run.py` required `--repo-path` and the SKILL.md playbooks instructed Claude to clone a `https://github.com/...` URL into a `/tmp/skill_sandbox_*` first. The whole flow was URL-based: paste a URL, skill clones, skill runs, skill cleans up.

This shape made sense when we were thinking about the web shell (a server has no concept of the user's working directory). It made less sense for native Claude Code use, where the user is already inside their own repo.

## What I asked

> 直接給一個 github url 感覺怪怪的. 我想像中應該是在自己要部署的那個 repo 用 / 觸發 skill, 而不是先 push 上 GitHub 再貼回 URL 給 AI

## The uncomfortable observation

Real workflow when you actually use this:

1. Open `~/work/my-app/` and start coding.
2. Make some changes (uncommitted).
3. Want to lint + test before committing.

URL-first flow forces you to:

1. Commit and push.
2. Paste the URL back into Claude.
3. Skill re-clones what you just pushed.
4. Lint + test runs against a clone, not your working tree.

That's backwards. You can't even check uncommitted code this way. **The URL flow is a side path, not the main path.**

## Options considered

1. **Keep URL-first.** Simplest, web shell works the same. But mismatches real use.
2. **Cwd-first, drop URL entirely.** Cleanest, but breaks the web shell (server has no `$PWD`).
3. **Cwd-first as default, URL as opt-in override.** Best of both. Native Claude Code reads `$PWD` by default; web shell always passes `--repo-url` since it has no other choice.

## Decision

**Option 3.** New `scripts/run.py` interface, applied uniformly to all 4 skills:

| Argument | Default | Meaning |
|---|---|---|
| `--repo-path PATH` | `os.getcwd()` | Local git checkout to operate on |
| `--repo-url URL` | `""` (unset) | If given, shallow-clone overrides `--repo-path` |
| `--ref REF` | `main` | Branch/tag/sha when `--repo-url` is given |

Resolution logic factored into `skills/_shared/repo_resolver.py`:

- If `repo_url_arg`: clone into a `/tmp/skill_sandbox_*`, return `(sandbox, cleanup_fn)` where `cleanup_fn` is `rmtree`. Skill runs `try/finally` so cleanup runs even on crash.
- Else: validate `path/.git` exists. If not: emit `{"ok": False, "error": "not a git repository: ..."}` and exit. Cleanup is no-op.

The `.git/` guard prevents accidentally scanning `~/Downloads/` or some non-repo directory. Forces an explicit error message rather than silent garbage.

## What stayed

- Web shell (`tool_runner.py`) was untouched. It already passes `--repo-url` because that's all it can do.
- All 4 skills' core logic unchanged. Only the argument resolution wraps the existing `do_actual_work(repo)` call.
- URL guard (`_shared/git_fetch.py`) untouched, still rejects non-`https://github.com/` URLs.

## What changed in user-facing docs

- README's worked example switched from `audit deps of https://github.com/psf/requests` to `audit my deps for known vulnerabilities`.
- 4 smoke test prompts changed from URL-bearing to natural cwd-style ("lint and test this repo", "audit my deps").
- "Optional: scan a third-party GitHub repo" was demoted to a footnote.

## Trade-offs we accepted

- The native vs web shell paths have a subtle behavioural difference now: native sees uncommitted changes; web shell never does. This is documented in `ui/README.md`'s **Differences from native Claude Code** section.
- `disable-model-invocation: true` (the write-skill safety gate) is checked by Claude Code natively but ignored by the Anthropic SDK on the web shell path. The web shell still has dry-run-by-default as a backstop, but the human gate is one layer thinner. Also documented.

## What this captures for the interviewer

The first design wasn't wrong; it solved the demo case. The cwd-first design solves the **actual usage** case. Asking "what does the developer actually do" surfaced the misalignment. The fix is small (one shared helper, four 5-line argparse changes) but meaningfully changes what the skills feel like to use.
