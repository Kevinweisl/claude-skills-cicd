# Trigger Eval: Cost & Latency Analysis

## Per-skill TPR / FPR (recap)

| Skill | TPR | FPR |
|---|---|---|
| browser-task | 1.00 | 0.00 |
| build-and-release | 1.00 | 0.00 |
| dependency-audit | 1.00 | 0.00 |
| hello | 1.00 | 0.00 |
| lint-and-test | 1.00 | 0.00 |
| sec-extract-10k | 1.00 | 0.00 |
| security-scan | 1.00 | 0.00 |

## Latency

- per-query duration not captured in this run; total elapsed: 1232.5s
- Re-run with the instrumented runner to populate per-query timing (`evals/skill-trigger/runner.py` records `duration_s` on each query as of 2026-05-03).

## Token / cost estimate (char-based)

- Voter count per query: 2 (K-vote)
- Prompt tokens (estimate): 369,785
- Output tokens (estimate): 8,400
- Total tokens (estimate): 378,185
- Estimated cost: ~$0.1702 USD
- Method: char-based estimate (~4 chars/token), output capped at 30 tok/query (order-of-magnitude only)

## K-voter agreement

- Queries: 140
- Unanimous (all voters agreed): 139 (99.3%)
- Split decisions: 1
