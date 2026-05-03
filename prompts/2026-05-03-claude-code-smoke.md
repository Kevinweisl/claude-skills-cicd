# Claude Code Local Smoke Test — 4 CI/CD Skills

> Run by user manually: open a fresh Claude Code session in any scratch dir,
> verify the 4 skills are visible and trigger correctly. Skills are symlinked
> into `~/.claude/skills/` from `interview_hw/skills/`.

Date: 2026-05-03 · Skills: `lint-and-test`, `build-and-release`,
`dependency-audit`, `security-scan` · Symlinks: `~/.claude/skills/<name>`

## Pre-check

```
$ ls -la ~/.claude/skills/ | grep -E "lint-and-test|build-and-release|dependency-audit|security-scan"
lrwxr-xr-x  1 kevinwei  staff   53  5月  3 14:17 lint-and-test -> /Users/kevinwei/src/interview_hw/skills/lint-and-test
lrwxr-xr-x  1 kevinwei  staff   57  5月  3 14:17 build-and-release -> /Users/kevinwei/src/interview_hw/skills/build-and-release
lrwxr-xr-x  1 kevinwei  staff   56  5月  3 14:17 dependency-audit -> /Users/kevinwei/src/interview_hw/skills/dependency-audit
lrwxr-xr-x  1 kevinwei  staff   53  5月  3 14:17 security-scan -> /Users/kevinwei/src/interview_hw/skills/security-scan
```

## Test plan

For each row below, in a fresh Claude Code session, paste the prompt and
observe whether Claude (a) recognizes the matching skill, (b) clones the
repo, (c) executes `scripts/run.py`, (d) summarizes the JSON output for
the user.

| # | Prompt | Expected skill | Pass criteria |
|---|---|---|---|
| 1 | `lint and test https://github.com/octocat/Hello-World at master` | `lint-and-test` | Triggers; clones; runs script; reports `language=unknown` (Hello-World has no pyproject/package.json) and surfaces this honestly |
| 2 | `audit dependencies of https://github.com/psf/requests at main for CVEs` | `dependency-audit` | Triggers; clones; runs pip-audit; reports finding count |
| 3 | `run semgrep + gitleaks on https://github.com/octocat/Hello-World at master` | `security-scan` | Triggers; clones; runs scanners; reports findings or warning |
| 4 | `build a wheel for /Users/kevinwei/src/interview_hw, version 0.1.0, dry run` | `build-and-release` | **Should NOT auto-trigger** (`disable-model-invocation: true`); user must explicitly say "use build-and-release skill" |

## Results (fill in after running)

### Test 1 — lint-and-test

- Triggered: [ ] yes [ ] no
- Output summary:
- Notes:

### Test 2 — dependency-audit

- Triggered: [ ] yes [ ] no
- Output summary:
- Notes:

### Test 3 — security-scan

- Triggered: [ ] yes [ ] no
- Output summary:
- Notes:

### Test 4 — build-and-release

- Triggered without explicit ask: [ ] yes [ ] no (expected: no — gated)
- Triggered with explicit "use build-and-release": [ ] yes [ ] no
- Output summary:
- Notes:

## Cleanup

```bash
# To remove the symlinks afterwards (optional):
rm ~/.claude/skills/lint-and-test
rm ~/.claude/skills/build-and-release
rm ~/.claude/skills/dependency-audit
rm ~/.claude/skills/security-scan
```
