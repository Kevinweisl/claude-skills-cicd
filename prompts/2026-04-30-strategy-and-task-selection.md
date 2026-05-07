# 2026-04-30 — Strategy and task selection

The strategic dialogue with Claude Code before any code was written. Compressed; the actual session was longer.

## Context

The brief contains 3 tasks (CI/CD Skills, Browser Agent, SEC 10-K Extractor). At least one is required, more is "a significant plus". Time budget: 7 days × 8-12h ≈ 70h.

## What I asked

> 我在準備一個面試, 現在有兩個 'AI-Coding-Test' 開頭的 md 檔, 內容是完全相同只是題目不同. 你幫我仔細閱讀之後, 我想要先跟你討論該如何開始

## Options Claude surfaced

1. **Do all three tasks** — most "complete" looking, but ~75-115h at A-level depth. Exceeds budget.
2. **Do all three + invent a Task D that integrates them** — my initial preference, to demonstrate "synthesis ability".
3. **Do 2 deeply + 1 lightly + integration narrative** — middle ground.
4. **Do 1 main + 1 supporting + 1 platform layer** — Claude's pushback proposal.

## Decision

Option 4. Specifically:

- **Task 3 (SEC 10-K extraction) = the depth anchor.** Aligns with my strongest area (NLP / structured extraction). Most likely to differentiate.
- **Task 1 (Skills Platform) = platform layer.** Tasks 2 + 3 ship as production skills running on top. Dogfood signal.
- **Task 2 (Browser Agent) = generalised agent + finance-domain task pack.** Independent deliverable; finance pack proves transferability without forcing coupling.

## Why Claude pushed back on Task D

- A-grade signals per the brief are **eval depth, honest failure modes, tradeoff quality, prompt quality**. None of those scale with task count.
- 7-day budget at A-level: Task 2 alone is 30-40h, Task 3 is 25-35h, Task 1 is 15-25h. Adding a synthetic Task D is extra 5-15h with no scoring benefit.
- The brief literally doesn't ask for a Task D. Adding one risks being read as "doesn't understand priorities".
- Held-out testing punishes happy-path-only work. Better to do fewer tasks deeper than more tasks shallower.

## Why the first integration narrative was rejected

First proposal: **"SEC AI Analysis Platform"** — Task 2 fetches DEF 14A for incorporated-by-reference resolution in Task 3.

A research subagent dispatched on Browser Agent feasibility came back with: **DEF 14A is a standard EDGAR form, pure-API access works, no browser needed**. Forcing a browser into a SEC narrative would have been transparent.

Revised narrative (kept):

> Task 1 (Skills Platform) is the dogfood layer; Tasks 2 + 3 ship as production skills on top. Task 3 is the depth anchor. Task 2 stays generalised but ships a finance-domain task pack. Each task is still independently deployable for held-out testing.

## What this captures for the interviewer

The decision NOT to do Task D is a more interesting signal than doing it would have been. We rejected an integration we couldn't honestly defend. Held-out testing rewards depth, not synthesis theatre.

## Outcome

7-day plan locked: Task 1 foundation Day 1, Task 3 Days 2-4, Task 1 skills Days 4-5, Task 2 Days 5-6, finalise Day 7. The Task 1 implementation shape (skills as a Claude Code feature vs skills as an HTTP service) was decided separately on 2026-05-03 — see [skills-as-feature-vs-skills-as-service](2026-05-03-skills-as-feature-vs-skills-as-service.md).
