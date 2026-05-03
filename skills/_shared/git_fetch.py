"""Shallow-clone a GitHub repo into a sandbox.

Used by every CI/CD skill's tool-runner before invoking scripts/run.py.
Hard-rejects anything that is not an `https://github.com/...` URL so that
file://, ssh://, and other-host side-channels can't be used to read the
server's filesystem or push through arbitrary credentials.
"""

from __future__ import annotations

from pathlib import Path

from .subprocess_helper import run_subprocess


class GitFetchError(RuntimeError):
    pass


def fetch_repo(repo: str, ref: str, dest: Path, timeout_s: float = 120.0) -> Path:
    """Shallow-clone `repo`@`ref` into `dest`. Returns dest on success.

    Only accepts `https://github.com/` URLs. Uses `--depth=1` to skip history.
    Raises `GitFetchError` on URL rejection or clone failure.
    """
    if not repo.startswith("https://github.com/"):
        raise GitFetchError(
            f"only https://github.com/ URLs allowed (got: {repo!r})"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = run_subprocess(
        ["git", "clone", "--depth=1", "--branch", ref, repo, str(dest)],
        timeout_s=timeout_s,
    )
    if r["exit_code"] != 0:
        raise GitFetchError(
            f"git clone failed (exit={r['exit_code']}): {r['stderr'][-300:]}"
        )
    return dest
