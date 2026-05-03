# Agent Shell — Manual UI Checklist

> The 8 tool_runner-layer scenarios in `scripts/e2e_real_repos.py` proved
> the **clone → script → JSON parse** half of the demo works end-to-end on
> real repos. This checklist is the **other half**: did Claude pick the
> right skill from natural-language prompts?

This requires an Anthropic API key (you supply yours via the UI's
sessionStorage input). Run after starting the server:

```bash
$(conda info --base)/envs/hw/bin/python -m uvicorn agent_shell.main:app \
    --port 18765 --app-dir src
```

Open `http://localhost:18765/`, paste your `sk-ant-...` into the top bar,
then for each row below: paste the prompt, observe behavior, fill in
results.

| # | Prompt | Expected skill triggered | Pass? | Notes |
|---|---|---|---|---|
| 1 | `lint and test https://github.com/octocat/Hello-World at master` | `lint-and-test`, ok=false (no pyproject) | [ ] | |
| 2 | (Same prompt) | `lint-and-test` again, cache_key matches scenario 1 | [ ] | |
| 3 | `audit deps of https://github.com/psf/requests at main` | `dependency-audit`, ok=true, ecosystems_detected=["python"] | [ ] | |
| 4 | `run semgrep + gitleaks on https://github.com/psf/requests at main` | `security-scan`, ok=true, scan_types_run includes semgrep+gitleaks | [ ] | |
| 5 | `build a wheel for https://github.com/octocat/Hello-World, version 0.1.0, dry run` | `build-and-release` (gated; Claude should ask first) | [ ] | If Claude refuses to call this without explicit consent, that's correct — disable-model-invocation behavior |
| 6 | `lint and test https://gitlab.com/foo/bar` | `lint-and-test` chosen, but tool_result shows `error: "only https://github.com/ URLs allowed"` | [ ] | |
| 7 | `lint and test https://github.com/this-org-does-not-exist-12345/nope at main` | `lint-and-test`, tool_result has git stderr | [ ] | |
| 8 | `lint and test /Users/kevinwei/src/interview_hw` | `lint-and-test`, language=python | [ ] | |

## Pass criteria

Test 5 is the **disambiguation gate**. The other 7 test that Claude correctly
routes natural-language prompts to the right skill. Acceptable if Claude
asks for clarification before triggering test 5 — that's exactly what
`disable-model-invocation: true` is supposed to enforce.

## Fallback if Claude API not available

The `scripts/e2e_real_repos.py` runs already cover the deterministic half
of these scenarios (clone, script execution, JSON shape, idempotency,
URL guard). See `evals/agent-shell-e2e/scenario-*.json`. The natural-
language trigger validation is the remaining gap.
