# Trigger Eval: Cost & Latency Analysis

## Latency

- per-query duration not captured in this run; total elapsed: 90.2s
- Re-run with the instrumented runner to populate per-query timing (`evals/skill-trigger/runner.py` records `duration_s` on each query as of 2026-05-03).

## Token / cost estimate (char-based)

- Voter count per query: 3 (K-vote)
- Prompt tokens (estimate): 37,107
- Output tokens (estimate): 900
- Total tokens (estimate): 38,007
- Estimated cost: ~$0.0165 USD
- Method: char-based estimate (~4 chars/token), output capped at 30 tok/query (order-of-magnitude only)

## Cross-domain ambiguity cases

- Strict (majority in allowed set): **10/10**
- Lenient (any voter in allowed set): **10/10**

| # | Query | Picked | Allowed | Strict | Lenient |
|---|---|---|---|---|---|
| 1 | `lint, test, then audit our deps for CVEs` | `lint-and-test` | `lint-and-test,dependency-audit` | PASS | 3/3 |
| 2 | `release this once lint passes` | `build-and-release` | `lint-and-test,build-and-release` | PASS | 3/3 |
| 3 | `before I publish, scan the source for hardcoded...` | `security-scan` | `security-scan,dependency-audit` | PASS | 2/3 |
| 4 | `is this repo safe to release, check vulns and ...` | `security-scan` | `security-scan,dependency-audit` | PASS | 2/3 |
| 5 | `make sure ruff passes and there's no leaked AWS...` | `lint-and-test` | `lint-and-test,security-scan` | PASS | 3/3 |
| 6 | `ship v2.4.0, but only if pip-audit comes back ...` | `dependency-audit` | `dependency-audit,build-and-release` | PASS | 3/3 |
| 7 | `run all the CI checks: lint, test, audit, scan` | `lint-and-test` | `lint-and-test,dependency-audit,security-scan` | PASS | 2/3 |
| 8 | `find SQL injection in our handlers and check if...` | `security-scan` | `security-scan,dependency-audit` | PASS | 3/3 |
| 9 | `do a complete pre-release check on the repo` | `lint-and-test` | `lint-and-test,dependency-audit,security-scan` | PASS | 2/3 |
| 10 | `I'm about to npm publish, is everything green` | `lint-and-test` | `lint-and-test,dependency-audit,security-scan` | PASS | 3/3 |
