"""Shared pytest fixtures for the skill scripts/run.py test suites.

The skills' `_shared/repo_resolver.py` validates that `--repo-path` points
at a git checkout (it checks for a `.git/` directory). The tests use
pytest's `tmp_path` fixture to simulate small repos; this conftest adds a
`.git/` marker so those temp paths satisfy the guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(tmp_path: Path) -> Path:
    """Same as pytest's built-in tmp_path, but pre-marked as a git repo.

    The skills' repo_resolver requires `.git/` to exist before it accepts
    a path. Creating an empty `.git/` directory is enough — the skills
    don't actually shell out to git for cwd-flow operations.
    """
    (tmp_path / ".git").mkdir()
    return tmp_path
