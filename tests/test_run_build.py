"""Tests for skills/build-and-release/scripts/run.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills" / "build-and-release" / "scripts" / "run.py"
)


def test_invalid_target_returns_error(tmp_path: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-path", str(tmp_path),
         "--target", "tarball",
         "--version", "1.0.0"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert "target" in out["error"].lower()


def test_missing_version_returns_error(tmp_path: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-path", str(tmp_path),
         "--target", "wheel",
         "--version", ""],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert "version" in out["error"].lower()


def test_docker_target_requires_image_name(tmp_path: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-path", str(tmp_path),
         "--target", "docker",
         "--version", "1.0.0"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert "image_name" in out["error"].lower()


def test_dry_run_default_does_not_push(tmp_path: Path) -> None:
    """Even when build fails (no pyproject), pushed must be False."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-path", str(tmp_path),
         "--target", "wheel",
         "--version", "1.0.0"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out.get("pushed", False) is False
