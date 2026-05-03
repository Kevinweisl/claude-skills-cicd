"""Tests for skills/lint-and-test/scripts/run.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills" / "lint-and-test" / "scripts" / "run.py"
)


def test_unsupported_language_returns_ok_false(tmp_path: Path) -> None:
    """Repo without pyproject.toml or package.json -> ok=false, no crash."""
    (tmp_path / "README").write_text("hi")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-path", str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert "unsupported" in out["error"].lower()
    assert out["language"] == "unknown"
    assert "cache_key" in out


def test_python_repo_runs_ruff_and_pytest(tmp_path: Path) -> None:
    """Trivial python project with passing test -> ok=true."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\n'
    )
    (tmp_path / "test_x.py").write_text("def test_ok():\n    assert 1 == 1\n")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-path", str(tmp_path)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["language"] == "python"
    assert out["test"]["passed"] is True
    assert out["lint"]["tool"] == "ruff"


def test_explicit_language_override(tmp_path: Path) -> None:
    """--language unknown still emits structured error, not crash."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-path", str(tmp_path),
         "--language", "auto"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "language" in out
