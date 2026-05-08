"""Tests for the install-hint plumbing in subprocess_helper + skills.

When a scanner binary is missing, the skill output must include an
`install_hint` so Claude can suggest the exact install command back to
the user. These tests pin both halves: the helper produces the field,
and the skills surface it correctly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills"))

from _shared.subprocess_helper import (  # noqa: E402
    INSTALL_HINTS,
    install_hint_for,
    run_subprocess,
)


def test_run_subprocess_sets_missing_binary_and_hint(tmp_path: Path):
    r = run_subprocess(["definitely-not-a-real-binary-zzz", "--help"])
    assert r["exit_code"] == -1
    assert r["missing_binary"] == "definitely-not-a-real-binary-zzz"
    assert "Prerequisites" in r["install_hint"] or r["install_hint"]


def test_install_hint_for_known_tool():
    assert "pip install pip-audit" in install_hint_for("pip-audit")
    assert "pip install semgrep" in install_hint_for("semgrep")
    assert "rustup" in install_hint_for("cargo")


def test_install_hint_for_unknown_tool_falls_back():
    hint = install_hint_for("not-a-real-tool")
    assert "not-a-real-tool" in hint
    assert "Prerequisites" in hint


def test_known_hints_cover_skills_actual_dependencies():
    """The skills shell out to a fixed set of binaries; ensure each has a hint."""
    expected = {"ruff", "pytest", "pip-audit", "semgrep", "bandit",
                "gitleaks", "npm", "cargo", "govulncheck", "docker", "build"}
    missing = expected - set(INSTALL_HINTS.keys())
    assert not missing, f"hints missing for: {missing}"


def test_lint_skill_surfaces_install_hint_on_missing_binary(tmp_path: Path):
    """Integration: when ruff and pytest aren't on PATH, the skill output
    names them and includes install commands. We run the script as a
    subprocess with PATH=empty so the binaries genuinely cannot be found."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n")
    # resolve_repo requires a git checkout. Init one explicitly.
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)

    # Keep `git` resolvable so resolve_repo's --git-dir check passes;
    # PATH points only at /usr/bin where git typically lives. ruff and
    # pytest aren't there, so they hit the missing-binary path.
    import shutil as _sh
    git_dir = str(Path(_sh.which("git")).parent)
    proc = subprocess.run(
        [sys.executable,
         str(ROOT / "skills/lint-and-test/scripts/run.py"),
         "--repo-path", str(repo)],
        capture_output=True, text=True, timeout=60,
        env={"PATH": git_dir},
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["lint"].get("install_hint", "").startswith("pip install ruff")
    assert out["test"].get("install_hint", "").startswith("pip install pytest")
    tools = {t["tool"] for t in out.get("missing_tools", [])}
    assert tools == {"ruff", "pytest"}
