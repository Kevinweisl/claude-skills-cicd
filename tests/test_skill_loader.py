"""Tests for src/agent_shell/skill_loader.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_shell.skill_loader import load_skills  # noqa: E402

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def test_load_skills_returns_4_ci_skills() -> None:
    tools = load_skills(SKILLS_DIR)
    names = {t["name"] for t in tools}
    assert {"lint-and-test", "build-and-release",
            "dependency-audit", "security-scan"} <= names


def test_each_tool_has_input_schema() -> None:
    tools = load_skills(SKILLS_DIR)
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"


def test_load_skills_skips_underscore_dirs() -> None:
    tools = load_skills(SKILLS_DIR)
    names = {t["name"] for t in tools}
    assert "_shared" not in names


def test_descriptions_nonempty() -> None:
    tools = load_skills(SKILLS_DIR)
    for t in tools:
        if t["name"] in {"lint-and-test", "build-and-release",
                          "dependency-audit", "security-scan"}:
            assert len(t["description"]) > 100
