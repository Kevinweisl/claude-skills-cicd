#!/usr/bin/env python3
"""End-to-end verification of the tool_runner layer on real GitHub repos.

This is the half of Phase 1.10 we can do without an Anthropic API key:
it bypasses the SDK / natural-language layer and directly calls
tool_runner.run_skill with the inputs Claude *would* produce for each
scenario. Proves: clone works, script runs, JSON parses, sandbox
cleans up.

The other half (Claude actually picking the right skill from a natural-
language prompt) must be validated manually via the UI with your key.
That checklist lives at evals/agent-shell-e2e/manual-checklist.md.

Usage:
    python scripts/e2e_real_repos.py            # run all 8 scenarios
    python scripts/e2e_real_repos.py --scenario 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from agent_shell.tool_runner import run_skill  # noqa: E402


SCENARIOS = [
    {
        "n": 1,
        "name": "lint-and-test on a tiny real repo (Hello-World, no Python)",
        "skill": "lint-and-test",
        "input": {"repo": "https://github.com/octocat/Hello-World", "ref": "master"},
        "expect": "ok=false, language=unknown (no pyproject/package.json)",
    },
    {
        "n": 2,
        "name": "lint-and-test idempotency (same input → same cache_key)",
        "skill": "lint-and-test",
        "input": {"repo": "https://github.com/octocat/Hello-World", "ref": "master"},
        "expect": "cache_key matches scenario 1's cache_key",
    },
    {
        "n": 3,
        "name": "dependency-audit on psf/requests",
        "skill": "dependency-audit",
        "input": {"repo": "https://github.com/psf/requests", "ref": "main"},
        "expect": "ok=true, ecosystems_detected includes 'python'",
    },
    {
        "n": 4,
        "name": "security-scan on psf/requests",
        "skill": "security-scan",
        "input": {
            "repo": "https://github.com/psf/requests",
            "ref": "main",
            "scan_types": "sast,secrets",
        },
        "expect": "ok=true, secrets_redacted_in_output=true",
    },
    {
        "n": 5,
        "name": "build-and-release wheel on Hello-World (no pyproject → graceful fail)",
        "skill": "build-and-release",
        "input": {
            "repo": "https://github.com/octocat/Hello-World",
            "ref": "master",
            "target": "wheel",
            "version": "0.1.0",
        },
        "expect": "ok=false, error contains 'build failed' or similar",
    },
    {
        "n": 6,
        "name": "URL guard: gitlab.com rejected",
        "skill": "lint-and-test",
        "input": {"repo": "https://gitlab.com/foo/bar"},
        "expect": "ok=false, error mentions only https://github.com/",
    },
    {
        "n": 7,
        "name": "Nonexistent github repo",
        "skill": "lint-and-test",
        "input": {
            "repo": "https://github.com/this-org-does-not-exist-12345/nope",
            "ref": "main",
        },
        "expect": "ok=false, git clone failed",
    },
    {
        "n": 8,
        "name": "Local-path sanity (use this repo)",
        "skill": "lint-and-test",
        "input": {"repo": str(REPO_ROOT)},
        "expect": "ok depends on this repo's lint/test status; language=python",
    },
]


def run_scenario(scn: dict) -> dict:
    t0 = time.perf_counter()
    result = run_skill(scn["skill"], scn["input"])
    elapsed = round(time.perf_counter() - t0, 1)
    return {
        "n": scn["n"],
        "name": scn["name"],
        "skill": scn["skill"],
        "input": scn["input"],
        "expected": scn["expect"],
        "elapsed_s": elapsed,
        "result": result,
    }


def summarize(records: list[dict]) -> None:
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for r in records:
        ok = r["result"].get("ok")
        mark = "✓" if ok is True else ("✗" if ok is False else "?")
        print(f" {mark} #{r['n']:>2} {r['name']:<55} ({r['elapsed_s']}s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", type=int, default=0,
                    help="run only this scenario number (default: all)")
    ap.add_argument("--out", default="evals/agent-shell-e2e",
                    help="dir to write per-scenario JSON")
    args = ap.parse_args()

    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = (
        [s for s in SCENARIOS if s["n"] == args.scenario]
        if args.scenario else SCENARIOS
    )
    if not selected:
        print(f"no scenario #{args.scenario}", file=sys.stderr)
        return 1

    records = []
    for scn in selected:
        print(f"\n→ Scenario #{scn['n']}: {scn['name']}")
        print(f"  skill={scn['skill']} input={scn['input']}")
        record = run_scenario(scn)
        out_file = out_dir / f"scenario-{scn['n']:02d}.json"
        out_file.write_text(json.dumps(record, indent=2, default=str))
        ok = record["result"].get("ok")
        print(f"  → ok={ok} ({record['elapsed_s']}s) saved {out_file.name}")
        records.append(record)

    if not args.scenario:
        # Idempotency check between scenario 1 and 2
        s1 = next((r for r in records if r["n"] == 1), None)
        s2 = next((r for r in records if r["n"] == 2), None)
        if s1 and s2:
            k1 = s1["result"].get("cache_key")
            k2 = s2["result"].get("cache_key")
            print(f"\nIdempotency check: cache_key #1={k1[:16] if k1 else None}... "
                  f"#2={k2[:16] if k2 else None}... match={k1 == k2 and k1 is not None}")

    summarize(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
