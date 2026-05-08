# 2026-05-01: Skill descriptions as production artifacts; trigger eval framework

## Context

The brief grades Task 1 on four axes, and the last one is explicit:

> Skill description 能否被 Claude 精準 trigger

The judges will inspect descriptions for trigger correctness. So descriptions are not throwaway prose; they're production artifacts that need an eval harness.

## What I asked

> 我們現在 4 個 skill 的 description 都是憑感覺寫的, 怎麼證明它們真的會被 Claude 在自然語言 prompt 下精準 trigger?

## Options Claude surfaced

1. **Vibes-driven iteration**: write description, eyeball, edit. Cheap but indefensible at the interview.
2. **Manual A/B testing**: paste prompts into Claude Code, see what triggers. Slow, doesn't scale.
3. **Programmatic eval with majority vote across multiple LLMs**: build a harness that scores descriptions on a corpus of `should_trigger` / `should_not_trigger` queries. Following Anthropic's own `skill-creator` methodology.

## Decision

Option 3. Specifically:

- **Scope**: 7 skills (4 CI/CD + 3 sibling skills `browser-task` / `sec-extract-10k` / `hello`) so disambiguation is tested in a "many skills coexist" world, not a single-skill bubble.
- **Per skill**: ≥10 `should_trigger` + ≥10 `should_not_trigger` queries. The `should_not_trigger` set must include **sister-skill traps**: queries that plausibly belong to a sibling, to test description boundary clarity.
- **K=3 vote** on NIM-hosted models (nemotron + mistral + qwen). Majority decides; unanimity becomes a description-clarity proxy.
- **5-round iteration**: each round identifies the worst-performing skill, edits its description, re-tests just that skill. Stop when TPR=1.0 / FPR=0.0 (or after 5 rounds, whichever first).
- **Test set held out 40%**: prevent overfitting description language to the training queries.

## Research delta: what we learned by rechecking conventions

The first-pass research was 1 day old when we started Day 5. A focused subagent re-checked currency before we finalised descriptions:

### 1. Imperative redirect beats noun-only redirect

Marc Bara's 650-trial study (Medium, 2026-03) reports **~20× higher trigger rate** when sister-skill disambiguation uses an imperative verb pointing to a named target.

| Bad (noun-only) | Good (imperative + named target) |
|---|---|
| `Do NOT use for: dependency CVEs (use sister-skill).` | `For dependency CVE checks, use dependency-audit instead.` |

We did NOT blanket-apply "ALWAYS invoke" across siblings. That recreates the jeremylongshore CI/CD identical-description disaster (anti-pattern A3 in prior research). What we adopted is the imperative-redirect pattern for sister-skill clauses only.

### 2. Front-load decisive keyword ≤ 30 chars from start

Measured first-decisive-keyword position across 10 real skills. Median: ~9 chars. Even Anthropic's own `pdf` (56) and `docx` (60) skills fail this metric. Trail of Bits and superpowers consistently hit ≤9. Our 4 CI/CD skills land at 4-8 chars, **better than Anthropic's own examples on this axis**.

### 3. The kaochenlong tutorial cited in the brief is the FLOOR, not the ceiling

Direct quotes from the cited reference:

> 好的 description 會明確列出這個 Skills 能做什麼事, 什麼情況下該被啟用.

> description 要寫得像在跟 Agent 解釋什麼時候該用這個技能.

The brief implies the tutorial is a baseline, but the real bar (per recent industry research) is higher: imperative verbs + sister-skill traps + front-loading + length budget compliance.

## Outcome

After 5 rounds of iteration:

- All 7 skills hit **TPR=1.0, FPR=0.0**
- All descriptions stay within the 1024-char budget (276 to 888 chars)
- Cross-domain ambiguity layer (10 queries that span 2+ skills): 10/10 strict pass

Reports: `evals/skill-trigger/last_run.json`, `cost_report_140q.md`, `cost_report_ambiguity.md`.

Total cost: ~$0.17 USD for the per-skill 140q eval, ~$0.017 USD for the 10q ambiguity eval. Reproducible: `evals/skill-trigger/analyze_last_run.py` regenerates reports from saved runs without further LLM calls.
