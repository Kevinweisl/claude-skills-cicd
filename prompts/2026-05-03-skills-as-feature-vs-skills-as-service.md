# 2026-05-03 — Skills as a Claude Code feature vs Skills as an HTTP service

The brief says "把常見的 GitHub CI/CD 工作流程封裝為幾個可重用的 Claude Skills" and links to `kaochenlong.com/claude-code-skills`. There are two defensible readings of that sentence, and the trade-off between them is the most consequential design decision in this project.

## Two readings

### Reading 1 — Skills as an HTTP service

Build a server (FastAPI gateway, Postgres queue, worker pool) that hosts each skill as a slug-keyed endpoint. Routing is `POST /skills/<name>/invoke` with an `Idempotency-Key` header. The "skill manifest" is the YAML schema that the gateway parses to authorise calls and dispatch to the right worker.

Strengths:

- Maps cleanly to the brief's grading axes: Skill 邊界 = REST resource boundaries; 認證與安全 = bearer auth + GitHub PAT; idempotency = HTTP idempotency-key; description trigger = ... well, this one is harder.
- Productisable shape. Looks like a real service.
- Hosts Tasks 2 and 3 as skills on the same platform. Dogfood signal.

Weakness (the one that ended up mattering):

- The "trigger" axis means *which skill Claude picks given a natural-language prompt*. That's a model-side property of the `description` field. An HTTP gateway has no opinion about which slug to call — the caller already chose. So "Skill description 能否被 Claude 精準 trigger" doesn't have a clean test surface in this reading.

### Reading 2 — Skills as an Anthropic Claude Code feature

Build skills as `SKILL.md` (YAML frontmatter + playbook) plus `scripts/run.py`. Claude Code ingests these from `~/.claude/skills/` (or via Plugin Marketplace), reads the `description` to decide which one to call from a natural-language ask, and runs the script. The "platform" is Claude Code itself.

Strengths:

- Maps directly to the literal feature the brief's reference link describes.
- The trigger axis becomes objectively measurable: feed a corpus of `should_trigger` / `should_not_trigger` queries to a model, see what it picks. That's the eval harness we built.
- Distribution via `/plugin install` is standard, not bespoke.

Weakness:

- The "deployable demo" requirement (universal req #3) is less obvious. It's solved by adding a thin Anthropic Agent SDK web shell on top, but that's a second deliverable rather than the primary surface.

## What we picked, and when

For Days 1–2 we built Reading 1 (the HTTP platform). It worked: gateway, queue, worker pool, hello smoke test, manifest scanner — all running on local Postgres with end-to-end idempotency proven by curl.

On the morning of 2026-05-03, before continuing implementation, I re-read the brief and the linked `kaochenlong.com/claude-code-skills` tutorial. The tutorial is unambiguously about the literal Anthropic feature: `SKILL.md` files, `description` triggers, the things Claude Code reads. Reading 2 is what the brief is asking for.

We shifted the implementation shape that day.

## Why Reading 2 is the better fit for *this* brief

Three concrete reasons:

1. **The reference link.** A brief that cites a tutorial about feature X is unlikely to be asking for a custom platform that resembles feature X. Easier to be wrong about the latter than the former.
2. **The grading axis on trigger.** "Skill description 能否被 Claude 精準 trigger" by **Claude** — Claude is the model, not our router. Reading 1 has no Claude-in-the-loop on routing; Reading 2 puts the model on the routing critical path, where the eval can grade it.
3. **Held-out testability.** The brief says graders will run held-out queries against the deployed system. For Reading 1, that's curl-driven and tests the platform. For Reading 2, that's natural-language and tests the descriptions — a more demanding bar that aligns with the explicit grading text.

## What carried over from Reading 1

The Reading 1 work was not throwaway. The shipped skills directly inherit:

- **Per-skill subprocess + JSON parsing logic** in `skills/<name>/scripts/run.py`. Lifted, not rewritten.
- **`skills/_shared/redact.py`** — token-shape redaction. Used unchanged.
- **`skills/_shared/git_fetch.py`** — URL guard + shallow clone. Used unchanged.
- **All 4 skill descriptions** — already trigger-eval-tuned. Carried over verbatim, then iterated further.
- **Trigger eval harness methodology** (NIM K=3 vote + sister-skill traps + 5-round iteration). Designed for Reading 2 from day one because it's description-only.

The platform-specific scaffolding (Postgres queue, gateway routes, worker pool, migrations) was archived under `archive/platform-prototype/` for git-history transparency. None of it runs at deploy time.

## What this captures for the interviewer

The choice between "skills as a service" and "skills as a feature" is not obvious from the brief in isolation; both are honest readings. We built the first, then found the linked tutorial described the second, and realigned. The handler logic transferred cleanly because both shapes need a deterministic subprocess + parser + redactor at the bottom of the stack — only the dispatcher above it is different.

The Plugin Marketplace install path described in [`2026-05-05-plugin-marketplace-vs-symlink.md`](2026-05-05-plugin-marketplace-vs-symlink.md), and the cwd-first invocation in [`2026-05-07-cwd-first-redesign.md`](2026-05-07-cwd-first-redesign.md), are both refinements of Reading 2.
