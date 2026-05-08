# 2026-05-05: Plugin Marketplace format vs `~/.claude/skills/` symlink

## Context

Once the skills had `SKILL.md` + `scripts/run.py` shape, the natural install path was symlinking each folder into `~/.claude/skills/`:

```bash
mkdir -p ~/.claude/skills
for skill in lint-and-test build-and-release dependency-audit security-scan; do
  ln -sfn $(pwd)/skills/$skill ~/.claude/skills/$skill
done
```

This works. Claude Code picks up each `SKILL.md`, descriptions trigger correctly, the smoke test passed. We were ready to ship.

## What I asked

> 我覺得現在我們設定的安裝方式怪怪的, 用 symlink 不太像生產環境會做的事. claude 官方有建議的 skill 安裝方式嗎?

## What the research surfaced

Anthropic Claude Code has a **Plugin Marketplace** mechanism. A repo with `.claude-plugin/marketplace.json` + `.claude-plugin/plugin.json` at root becomes installable via:

```
/plugin marketplace add Kevinweisl/claude-skills-cicd
/plugin install claude-skills-cicd@cicd-skills
```

Properties of the plugin path:

- **Namespacing**: skills appear as `claude-skills-cicd:lint-and-test`, not bare `lint-and-test`. Avoids collisions with other plugins / personal skills.
- **Versioning**: `/plugin update` for upgrades; pinning via release tags possible.
- **No symlink hygiene**: nothing manually placed in `~/.claude/skills/`.
- **Standard distribution**: same shape as anyone else's published Claude Code plugin.

Properties of the symlink path:

- **No namespace** (skill name is the bare folder name).
- **No update mechanism** (you `git pull` and the symlink picks it up automatically).
- **Manual setup** with a per-skill `ln -sfn` loop.
- **Non-standard**: doesn't match how published plugins are normally consumed.

## Options considered

1. **Keep symlink**: zero new code. Works. But non-standard.
2. **Add Plugin Marketplace manifests**: small (~20 lines of JSON), gets us the standard distribution path.
3. **Both**: support symlink AND plugin install. README gets cluttered.

## Decision

**Option 2.** Promote plugin marketplace to the primary install path. Keep symlink documented in FAQ as a fallback for older Claude Code versions or for users who want bare names.

Specific manifests:

```json
// .claude-plugin/plugin.json
{
  "name": "claude-skills-cicd",
  "description": "4 reusable Claude Code skills for GitHub CI/CD",
  "version": "1.0.0",
  ...
}

// .claude-plugin/marketplace.json
{
  "name": "cicd-skills",
  "plugins": [{
    "name": "claude-skills-cicd",
    "source": "./",
    ...
  }]
}
```

The same repo is both the marketplace and the only plugin in it. `source: "./"` (note the `./` prefix; `.` alone fails marketplace validation per Anthropic docs) points to repo root.

## Subtlety: validation

`claude plugin validate /path/to/repo` is the official CLI to confirm manifests parse. First attempt failed with `plugins.0.source: Invalid input` because `source: "."` doesn't match the schema. Changed to `"./"` and it passed.

This is the kind of detail that's only documented in the schema reference, not in tutorials. Worth keeping note of.

## What this captures for the interviewer

The first working install path (symlink) was good enough to demo. We didn't stop there. The plugin marketplace path makes the deliverable look like a real product distribution, not a one-off setup script. It also unlocks `/plugin update`, which is the right primitive if anyone (including the interviewer) wants to track changes after install.

## Outcome

`Kevinweisl/claude-skills-cicd` is now installable in 2 commands inside any Claude Code session. README's Quick start leads with the plugin marketplace path; symlink approach moved to FAQ Q1.
