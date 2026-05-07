# prompts/

Curated record of the Claude Code dialogues that shaped this repo. Not full transcripts; one entry per non-trivial decision, written as: **what I asked → options Claude surfaced → what we picked → why → outcome**. The brief explicitly says these will be read, so the goal is to make the design history navigable, not exhaustive.

## How to read this folder

Read in chronological order if you want the narrative arc. Read by topic if you want a specific decision.

| Date | Topic | Decision in one line |
|---|---|---|
| 2026-04-30 | [strategy-and-task-selection](2026-04-30-strategy-and-task-selection.md) | Drop the synthetic Task D; do 1 main + 1 platform + 1 supporting; integration narrative without forced coupling |
| 2026-05-01 | [skill-descriptions-and-trigger-eval](2026-05-01-skill-descriptions-and-trigger-eval.md) | Treat skill descriptions as production artifacts; build NIM K=3 vote eval harness with sister-skill traps |
| 2026-05-03 | [skills-as-feature-vs-skills-as-service](2026-05-03-skills-as-feature-vs-skills-as-service.md) | Two valid readings of "reusable Claude Skills"; align with the literal Anthropic feature so the description-trigger axis becomes measurable |
| 2026-05-05 | [plugin-marketplace-vs-symlink](2026-05-05-plugin-marketplace-vs-symlink.md) | Drop the `~/.claude/skills/` symlink install in favour of the `.claude-plugin/marketplace.json` Plugin Marketplace format |
| 2026-05-07 | [cwd-first-redesign](2026-05-07-cwd-first-redesign.md) | Skills default to `$PWD`, not a clone of a URL. Match how a developer actually invokes them. URL becomes opt-in override |
| 2026-05-07 | [zeabur-dockerfile-binary-tradeoffs](2026-05-07-zeabur-dockerfile-binary-tradeoffs.md) | Bake in Python scanners + gitleaks; skip Node/Rust/Go/Docker/trivy; rely on graceful degradation contract |
| 2026-05-07 | [claude-code-smoke-test](2026-05-07-claude-code-smoke-test.md) | Manual evaluator checklist for the 4 skills inside a real Claude Code session |

## What's NOT here

- Full LLM transcripts. The interesting part is the decision, not the rambling.
- Every minor edit. Tiny refactors / typo fixes don't get a prompt entry.
- Detailed code review back-and-forth. Those land in commit messages.

## Conventions

- Filename: `YYYY-MM-DD-topic-as-kebab.md`. Date when the decision was made. Topic-first (not "day-N").
- Each file has a `## Decision` line so you can scan-read.
- Quoted user prompts are paraphrased to compress; the actual prompts ran in Claude Code locally.
