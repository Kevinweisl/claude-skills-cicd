"""Scan skills/ → list of Anthropic tool definitions for the SDK.

We hardcode JSON-Schema input shapes here (not derived from SKILL.md body)
because the Anthropic SDK requires JSON Schema, not free-form Markdown. The
description is read from SKILL.md frontmatter so that any tweak to the
trigger-tuned prose flows into the SDK without code changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


_INPUT_SCHEMAS: dict[str, dict] = {
    "lint-and-test": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "https://github.com/owner/name URL or absolute local path",
            },
            "ref": {
                "type": "string",
                "description": "branch / tag / commit SHA (only for GitHub URLs)",
                "default": "main",
            },
            "language": {
                "type": "string",
                "enum": ["auto", "python", "node"],
                "default": "auto",
            },
        },
        "required": ["repo"],
    },
    "build-and-release": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "ref": {"type": "string", "default": "main"},
            "target": {"type": "string", "enum": ["wheel", "npm", "docker"]},
            "version": {"type": "string", "description": "semver, e.g. 1.2.3"},
            "image_name": {
                "type": "string",
                "description": "owner/name (required when target=docker)",
            },
            "no_dry_run": {
                "type": "boolean",
                "default": False,
                "description": "set to true ONLY when user explicitly asks to actually push",
            },
        },
        "required": ["repo", "target", "version"],
    },
    "dependency-audit": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "ref": {"type": "string", "default": "main"},
            "ecosystems": {
                "type": "string",
                "description": "comma-separated subset of python,node,rust,go (default: auto)",
                "default": "",
            },
        },
        "required": ["repo"],
    },
    "security-scan": {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "ref": {"type": "string", "default": "main"},
            "scan_types": {
                "type": "string",
                "description": "comma-separated subset of sast,secrets,container",
                "default": "sast,secrets",
            },
            "image_name": {
                "type": "string",
                "description": "required only when scan_types includes container",
            },
        },
        "required": ["repo"],
    },
}


def _read_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def load_skills(skills_dir: Path) -> list[dict]:
    """Return list of Anthropic tool definitions, one per skill folder.

    Skips underscore-prefixed dirs (e.g. `_shared`). Only includes skills
    that have an `input_schema` defined here; others are silently dropped
    because we can't surface them to the SDK without a schema.
    """
    tools: list[dict] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = _read_frontmatter(skill_md)
        name = fm.get("name", child.name)
        if name not in _INPUT_SCHEMAS:
            continue
        tools.append({
            "name": name,
            "description": fm.get("description", ""),
            "input_schema": _INPUT_SCHEMAS[name],
        })
    return tools
