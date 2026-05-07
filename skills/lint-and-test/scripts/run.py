#!/usr/bin/env python3
"""lint-and-test skill — execute ruff + pytest (Python) or npm lint+test (Node).

Usage (called by Claude via Bash, or directly):
    python skills/lint-and-test/scripts/run.py [--repo-path PATH] [options]
    python skills/lint-and-test/scripts/run.py --repo-url URL [--ref REF]

Repo resolution:
    --repo-path PATH    local path to a git checkout (default: $PWD)
    --repo-url URL      shallow-clone this GitHub URL instead (overrides --repo-path)
    --ref REF           branch/tag/sha when --repo-url is used (default: main)

Other options:
    --commit-sha SHA    used for cache key only (optional)
    --language LANG     auto | python | node (default: auto)

Output: single JSON object on stdout. Never raises on tool-level failure;
always exits 0 with `ok=false` if work was done but the tool reported an
issue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _shared.repo_resolver import resolve_repo  # noqa: E402
from _shared.subprocess_helper import hash_inputs, run_subprocess  # noqa: E402


def detect_language(repo: Path) -> str:
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        return "python"
    if (repo / "package.json").exists():
        return "node"
    return "unknown"


def run_python(repo: Path) -> dict:
    ruff = run_subprocess(["ruff", "check", "."], cwd=str(repo))
    lint_passed = ruff["exit_code"] == 0
    pytest_run = run_subprocess(
        ["pytest", "-q", "--no-header"], cwd=str(repo), timeout_s=300.0,
    )
    test_passed = pytest_run["exit_code"] == 0
    summary_match = re.search(
        r"(\d+ passed|\d+ failed|\d+ error)", pytest_run["stdout"]
    )
    test_summary = (
        summary_match.group(0) if summary_match else pytest_run["stdout"][-200:]
    )
    return {
        "lint": {
            "tool": "ruff",
            "passed": lint_passed,
            "exit_code": ruff["exit_code"],
            "issues": ruff["stdout"].splitlines()[:50] if not lint_passed else [],
            "duration_ms": ruff["duration_ms"],
        },
        "test": {
            "tool": "pytest",
            "passed": test_passed,
            "exit_code": pytest_run["exit_code"],
            "summary": test_summary,
            "duration_ms": pytest_run["duration_ms"],
            "timed_out": pytest_run.get("timed_out", False),
        },
        "language": "python",
        "ok": lint_passed and test_passed,
    }


def run_node(repo: Path) -> dict:
    lint = run_subprocess(["npm", "run", "lint", "--silent"], cwd=str(repo))
    test = run_subprocess(["npm", "test", "--silent"], cwd=str(repo))
    return {
        "lint": {
            "tool": "npm-run-lint",
            "passed": lint["exit_code"] == 0,
            "exit_code": lint["exit_code"],
            "issues": lint["stdout"].splitlines()[-30:],
            "duration_ms": lint["duration_ms"],
        },
        "test": {
            "tool": "npm-test",
            "passed": test["exit_code"] == 0,
            "exit_code": test["exit_code"],
            "summary": test["stdout"][-200:],
            "duration_ms": test["duration_ms"],
        },
        "language": "node",
        "ok": lint["exit_code"] == 0 and test["exit_code"] == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="lint-and-test skill")
    ap.add_argument("--repo-path", default=os.getcwd(),
                    help="local git checkout (default: current directory)")
    ap.add_argument("--repo-url", default="",
                    help="GitHub URL to shallow-clone (overrides --repo-path)")
    ap.add_argument("--ref", default="main",
                    help="branch/tag/sha when --repo-url is given")
    ap.add_argument("--commit-sha", default="")
    ap.add_argument(
        "--language", default="auto", choices=["auto", "python", "node"],
    )
    args = ap.parse_args()

    repo, cleanup = resolve_repo(args.repo_path, args.repo_url, args.ref)
    try:
        language = args.language
        if language == "auto":
            language = detect_language(repo)

        lockfile_h = ""
        for f in ("pyproject.toml", "uv.lock", "package-lock.json", "yarn.lock"):
            p = repo / f
            if p.exists():
                lockfile_h += hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        # cache_key is content-based on purpose: same lockfile + same ref + same
        # language => same key, regardless of where the repo is checked out.
        cache_key = hash_inputs([args.commit_sha, language, lockfile_h])

        if language == "python":
            result = run_python(repo)
        elif language == "node":
            result = run_node(repo)
        else:
            result = {
                "ok": False,
                "error": f"unsupported language: {language} (no pyproject.toml or package.json found)",
                "language": language,
            }

        result["cache_key"] = cache_key
        print(json.dumps(result, indent=2))
        return 0
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
