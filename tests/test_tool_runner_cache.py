"""Tests for tool_runner's process-local idempotency cache.

Idempotency at the runner layer means: identical (skill, input_args) calls
within the TTL window return the prior result without re-running the script
or re-cloning the repo. We mock subprocess to count invocations so we can
prove the second call really did short-circuit.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_shell import tool_runner  # noqa: E402


def _fake_run_subprocess_factory(stdout: str, exit_code: int = 0):
    """Each call increments the counter so a test can assert exactly N runs."""
    counter = {"n": 0}

    def fake(cmd, cwd=None, timeout_s=600.0):
        counter["n"] += 1
        return {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": "",
            "duration_ms": 1,
            "timed_out": False,
        }

    return fake, counter


def test_identical_calls_short_circuit_via_cache(tmp_path: Path):
    tool_runner.cache_clear()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n")

    fake_sub, counter = _fake_run_subprocess_factory(
        '{"ok": true, "language": "python", "lint": {}, "test": {}}'
    )

    with patch("agent_shell.tool_runner.run_subprocess", side_effect=fake_sub):
        first = tool_runner.run_skill(
            "lint-and-test", {"repo": str(repo), "language": "python"}
        )
        second = tool_runner.run_skill(
            "lint-and-test", {"repo": str(repo), "language": "python"}
        )

    assert first.get("ok") is True
    assert "_cache_hit" not in first
    assert second.get("_cache_hit") is True
    assert counter["n"] == 1, "second call must not re-run the subprocess"


def test_failed_runs_are_not_cached(tmp_path: Path):
    """Transient failure should be retryable — don't freeze ok=false for 5 minutes."""
    tool_runner.cache_clear()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n")

    fake_sub, counter = _fake_run_subprocess_factory(
        '{"ok": false, "error": "transient"}'
    )

    with patch("agent_shell.tool_runner.run_subprocess", side_effect=fake_sub):
        tool_runner.run_skill("lint-and-test", {"repo": str(repo)})
        tool_runner.run_skill("lint-and-test", {"repo": str(repo)})

    assert counter["n"] == 2, "ok=false must be re-attempted, not cached"


def test_different_inputs_do_not_share_cache(tmp_path: Path):
    tool_runner.cache_clear()
    repo_a = tmp_path / "a"; repo_a.mkdir(); (repo_a / "pyproject.toml").write_text("x")
    repo_b = tmp_path / "b"; repo_b.mkdir(); (repo_b / "pyproject.toml").write_text("y")

    fake_sub, counter = _fake_run_subprocess_factory('{"ok": true}')
    with patch("agent_shell.tool_runner.run_subprocess", side_effect=fake_sub):
        tool_runner.run_skill("lint-and-test", {"repo": str(repo_a)})
        tool_runner.run_skill("lint-and-test", {"repo": str(repo_b)})

    assert counter["n"] == 2


def test_build_and_release_no_dry_run_is_never_cached(tmp_path: Path):
    """Side-effecting writes must always re-execute on explicit re-invocation."""
    tool_runner.cache_clear()
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n")

    fake_sub, counter = _fake_run_subprocess_factory(
        '{"ok": true, "target": "wheel", "pushed": true, "dry_run": false}'
    )

    with patch("agent_shell.tool_runner.run_subprocess", side_effect=fake_sub):
        tool_runner.run_skill("build-and-release", {
            "repo": str(repo), "target": "wheel", "version": "0.1.0",
            "no_dry_run": True,
        })
        tool_runner.run_skill("build-and-release", {
            "repo": str(repo), "target": "wheel", "version": "0.1.0",
            "no_dry_run": True,
        })

    assert counter["n"] == 2, "no_dry_run publishes must re-execute"


def test_build_and_release_dry_run_is_cached(tmp_path: Path):
    """Dry-run is read-only; caching is fine."""
    tool_runner.cache_clear()
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n")

    fake_sub, counter = _fake_run_subprocess_factory(
        '{"ok": true, "target": "wheel", "pushed": false, "dry_run": true}'
    )

    with patch("agent_shell.tool_runner.run_subprocess", side_effect=fake_sub):
        tool_runner.run_skill("build-and-release", {
            "repo": str(repo), "target": "wheel", "version": "0.1.0",
        })
        second = tool_runner.run_skill("build-and-release", {
            "repo": str(repo), "target": "wheel", "version": "0.1.0",
        })

    assert counter["n"] == 1
    assert second.get("_cache_hit") is True


def test_ttl_expiry_forces_re_execution(tmp_path: Path):
    tool_runner.cache_clear()
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n")

    fake_sub, counter = _fake_run_subprocess_factory('{"ok": true}')

    with patch("agent_shell.tool_runner.run_subprocess", side_effect=fake_sub), \
         patch("agent_shell.tool_runner._CACHE_TTL_S", 0.05):
        tool_runner.run_skill("lint-and-test", {"repo": str(repo)})
        time.sleep(0.1)
        tool_runner.run_skill("lint-and-test", {"repo": str(repo)})

    assert counter["n"] == 2


def test_cache_hit_marker_is_visible_to_caller(tmp_path: Path):
    tool_runner.cache_clear()
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n")

    fake_sub, _ = _fake_run_subprocess_factory(
        '{"ok": true, "language": "python", "lint": {}, "test": {}}'
    )
    with patch("agent_shell.tool_runner.run_subprocess", side_effect=fake_sub):
        first = tool_runner.run_skill("lint-and-test", {"repo": str(repo)})
        second = tool_runner.run_skill("lint-and-test", {"repo": str(repo)})

    assert first.get("ok") is True and "_cache_hit" not in first
    assert second.get("ok") is True and second["_cache_hit"] is True
