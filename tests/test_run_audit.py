"""Tests for skills/dependency-audit/scripts/run.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills" / "dependency-audit" / "scripts" / "run.py"
)


def test_repo_with_no_manifests_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "README").write_text("hi")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-path", str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert out["ecosystems_detected"] == []
    assert out["summary"]["total"] == 0


def test_python_manifest_detected(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = []\n'
    )
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-path", str(tmp_path)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert "python" in out["ecosystems_detected"]


def test_ecosystem_filter(tmp_path: Path) -> None:
    """Even if multiple manifests exist, --ecosystems filter should narrow it."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\n'
    )
    (tmp_path / "package-lock.json").write_text('{"name": "x", "version": "0"}')
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-path", str(tmp_path),
         "--ecosystems", "python"],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ecosystems_detected"] == ["python"]
