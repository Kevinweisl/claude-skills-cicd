# Task 1 — Skills Platform + CI/CD Skills

> Status: Day 1 platform foundation complete. CI/CD skill content + trigger eval harness queued for Day 4-5. Zeabur deploy queued for Day 4.

## What this delivers (per the interview brief)

The brief asks for "几个 reusable Claude Skills (e.g. lint-and-test, build-and-release, dependency-audit, security-scan)" + a Zeabur-deployed demo, evaluated on:
1. **Skill 邊界 (boundary design)**
2. **認證與安全 (auth & safety)**
3. **Idempotency**
4. **Description 能否被 Claude 精準 trigger** (quantified)

## Architectural answer

Rather than 4 standalone skill scripts, we built a **Skills Platform** that hosts skills as production services — and Tasks 2 & 3 are also implemented as skills running on this same platform. The platform's design is therefore dogfooded, not just imagined.

See `docs/design/2026-04-30-interview-hw-design.md` § 2 for full architecture and §3 for Task 1 specifics.

## Design Patterns Demonstrated

Each skill in the platform is deliberately chosen to demonstrate a distinct design pattern. Evaluators looking at "Skill 邊界切得好" should be able to point to each skill and identify a specific decision.

| Skill | Worker | Design Pattern Demonstrated | Read/Write | Idempotency Strategy |
|---|---|---|---|---|
| **`lint-and-test`** | ci | **Multi-tool pipeline with shared install/cache** — combining lint + test under one boundary because they share dep install + lockfile cache + same runner; splitting would force consumers to dedupe install steps. | Read | Cache key = `commit_sha + lockfile_hash` |
| **`build-and-release`** | ci | **Side-effecting write + content-addressed safety** — adds `disable-model-invocation: true` so Claude won't auto-invoke; idempotent by `image_digest` so re-pushing the same artifact is a no-op. | Write (registry) | Content-addressed by `image_digest`; tag immutability |
| **`dependency-audit`** | ci | **Read-only, multi-ecosystem routing** — single skill that detects npm/pip/cargo/go from manifest, fans out to per-ecosystem auditors, normalizes output to SARIF. Demonstrates "one skill, polymorphic input". | Read | Cache key = `lockfile_hash + advisory_db_date` |
| **`security-scan`** | ci | **Multi-tool orchestration with severity-weighted aggregation** — runs Semgrep + gitleaks + trivy in parallel, deduplicates findings by `(file, line, rule_id)`, weights severity. Demonstrates ensemble pattern. | Read | Cache key = `commit_sha + scan_types`; output secret-redacted |
| **`browser-task`** | browser | **LLM-driven agent skill** — long-running (minutes), stateful (cookies/selector cache), with built-in self-correction. The platform's queue + SSE + selector_cache table support this without extra infra. | Read (mostly) | Idempotency-Key + cached `(url_template, intent)` selectors |
| **`sec-extract-10k`** | extractor | **Hybrid rules+LLM pipeline** — Phase 1 rules (free, fast), Phase 2 LLM only on edge cases, Phase 3 XBRL cross-validation. Demonstrates cost discipline. | Read | Cache key = `cik + accession`; deterministic output |
| **`hello`** | ci | **Smoke / liveness skill** — verifies the platform pipeline end-to-end without external dependencies. | Read | Stateless |

## Auth & Safety Boundaries (cross-cutting)

| Concern | Implementation |
|---|---|
| API auth | Bearer `API_KEY` env var; rotated via env, never in SKILL.md |
| GitHub auth | Fine-grained PAT, single-repo scope, `contents:read` + `checks:write` only |
| `allowed-tools` | Each skill explicitly enumerates allowed Bash patterns (e.g., `Bash(git *) Bash(pytest *)`); `Bash(*)` is never used |
| Output secret redaction | All worker output passes a regex filter for common token patterns (GitHub `ghp_…`, AWS `AKIA…`, JWT) before persisting |
| Worker isolation | Each worker is a separate process; queue routes by `worker_target` |
| Audit log | `audit_events` table records replan reasons, retry decisions, secret-redaction events |

## Idempotency Layers

| Layer | Mechanism |
|---|---|
| API | `Idempotency-Key` HTTP header → Postgres `UNIQUE (skill_name, idempotency_key)` partial index |
| Skill-internal | Per-skill cache key (see table above) |
| Side-effect skills | Content-addressed (digest, SHA, tag); re-pushing same content = no-op |

## Trigger Eval (Day 5 deliverable)

Quantified test of whether each skill's `description` triggers Claude precisely.

- **Scope**: All 7 skills above (not just the 4 CI/CD), so disambiguation is tested in the real "many skills coexist" scenario.
- **Per skill**: ≥20 `should_trigger` queries + ≥20 `should_not_trigger` queries; ≥3 of the should-not queries must be queries that *plausibly* belong to a sibling skill (e.g., `dependency-audit`'s should-not includes "scan my deps for CVEs" which is a `security-scan` query).
- **Run**: each query × 3 runs, majority vote.
- **Iteration**: 5 rounds — each round identifies the worst-performing skill, modifies its `description`, retests that skill only.
- **Model**: `${TRIGGER_EVAL_MODEL}` (provided by user, must match the production Claude model — not Haiku).
- **Report**: per-skill TPR/FPR before vs after, plus a confusion matrix showing which skill pairs get conflated.

## Status by day

- **Day 1**: ✅ Platform foundation (gateway, queue, worker pool, manifest scanner, auth, idempotency, hello smoke)
- **Day 4**: ⏳ Implement `lint-and-test` + `dependency-audit` + first Zeabur deploy
- **Day 5**: ⏳ Implement `build-and-release` + `security-scan` + run full 7-skill trigger eval (5 iterations) + deploy
- **Day 7**: ⏳ Add minimal Web UI to demo skill invocation visually

## Files involved

- `src/gateway/` — FastAPI app
- `src/workers/ci/` — handlers for the 4 CI/CD skills
- `src/workers/base.py` — shared `WorkerPool` poll-and-lock pattern
- `skills/*/SKILL.md` — manifest source of truth
- `evals/skill-trigger/` — per-skill eval JSON + runner
- `migrations/001_init.sql` — schema
- `scripts/run_skill_eval.py` — eval harness (TBD Day 5)
