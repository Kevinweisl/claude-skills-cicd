"""Tests for skills/_shared/git_fetch.py: URL guard + shallow clone."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills"))
from _shared.git_fetch import GitFetchError, fetch_repo  # noqa: E402


def test_rejects_non_github_url(tmp_path: Path) -> None:
    with pytest.raises(GitFetchError, match="only https://github.com/"):
        fetch_repo("https://gitlab.com/foo/bar", "main", tmp_path / "out")


def test_rejects_file_url(tmp_path: Path) -> None:
    with pytest.raises(GitFetchError):
        fetch_repo("file:///etc/passwd", "main", tmp_path / "out")


def test_rejects_ssh_url(tmp_path: Path) -> None:
    with pytest.raises(GitFetchError):
        fetch_repo("git@github.com:foo/bar.git", "main", tmp_path / "out")


@pytest.mark.network
def test_clones_real_small_public_repo(tmp_path: Path) -> None:
    dest = tmp_path / "clone"
    result = fetch_repo("https://github.com/octocat/Hello-World", "master", dest)
    assert result == dest
    assert (dest / "README").exists()


@pytest.mark.network
def test_clone_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(GitFetchError, match="git clone failed"):
        fetch_repo(
            "https://github.com/this-org-does-not-exist-12345/nope",
            "main",
            tmp_path / "out",
        )
