"""Resolve which repository a skill should operate on.

A skill can be invoked two ways:

1. Default: run on the user's current repository. The skill's `scripts/run.py`
   reads `--repo-path` (defaulting to `$PWD`) and validates that the path is
   a git checkout. No clone, no network.

2. Remote override: the user supplies `--repo-url` (and optionally `--ref`).
   The skill shallow-clones into `/tmp/skill_sandbox_*`, runs against the
   clone, and removes the sandbox in a `finally` block.

This module hides the dance behind one helper so all 4 CI/CD skills agree
on the resolution rules and the URL guard. On any error it emits a single
JSON object to stdout and exits 0 (skills never raise on user input).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from .git_fetch import GitFetchError, fetch_repo


def resolve_repo(
    repo_path_arg: str,
    repo_url_arg: str,
    ref_arg: str = "main",
) -> tuple[Path, Callable[[], None]]:
    """Return (resolved_repo_path, cleanup_callback).

    `cleanup()` is always safe to call. It rmtree's the sandbox iff one was
    created (URL flow); it's a no-op for the cwd flow.

    On error (URL rejected, clone failed, path not a git repo) this function
    prints a JSON error envelope to stdout and `sys.exit(0)` so the caller
    never sees a stack trace.
    """
    if repo_url_arg:
        sandbox = Path(tempfile.mkdtemp(prefix="skill_sandbox_"))
        try:
            fetch_repo(repo_url_arg, ref_arg, sandbox)
        except GitFetchError as exc:
            shutil.rmtree(sandbox, ignore_errors=True)
            _emit_error(str(exc))
        return sandbox, lambda: shutil.rmtree(sandbox, ignore_errors=True)

    path = Path(repo_path_arg).resolve()
    if not path.exists():
        _emit_error(f"repo path not found: {path}")
    if not (path / ".git").exists():
        _emit_error(
            f"not a git repository: {path}. "
            "Pass --repo-url <github-url> to scan a remote, "
            "or cd into a git checkout first."
        )
    return path, lambda: None


def _emit_error(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, indent=2))
    sys.exit(0)
