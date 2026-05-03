"""Execute a skill's scripts/run.py given Anthropic tool_use input.

This is the bridge between the SDK's `tool_use` blocks and the deterministic
shell scripts that do the actual work. Responsibilities:

  - If `repo` is a GitHub URL, shallow-clone it into a sandbox; otherwise treat
    it as a local path.
  - Translate the JSON tool-use input into the script's CLI args.
  - Run the script in a subprocess and parse its stdout JSON.
  - Always clean up the sandbox.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills"))
from _shared.git_fetch import GitFetchError, fetch_repo  # noqa: E402
from _shared.subprocess_helper import run_subprocess  # noqa: E402


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


def _build_cli_args(name: str, input_args: dict, repo_path: Path) -> list[str]:
    """Translate {repo, ref, ...} dict → argparse flags."""
    cli: list[str] = ["--repo-path", str(repo_path)]
    for k, v in input_args.items():
        if k in ("repo", "ref"):
            continue
        flag = "--" + k.replace("_", "-")
        if isinstance(v, bool):
            if v:
                cli.append(flag)
            # False booleans pass nothing (argparse store_true semantics)
        elif isinstance(v, list):
            if v:
                cli.extend([flag, ",".join(map(str, v))])
        elif v == "" or v is None:
            continue
        else:
            cli.extend([flag, str(v)])
    return cli


def run_skill(name: str, input_args: dict) -> dict:
    """Execute the skill named `name` with the input dict from a tool_use block.

    Returns the parsed JSON result dict. On failure, returns
    {ok: false, error: ...} so the SDK gets a structured response.
    """
    script = SKILLS_DIR / name / "scripts" / "run.py"
    if not script.exists():
        return {"ok": False, "error": f"skill {name!r} has no scripts/run.py"}

    repo_arg = input_args.get("repo", "")
    sandbox: Path | None = None

    try:
        if repo_arg.startswith("https://github.com/"):
            sandbox = Path(tempfile.mkdtemp(prefix="skill_sandbox_"))
            try:
                fetch_repo(
                    repo_arg, input_args.get("ref", "main"), sandbox / "repo",
                )
            except GitFetchError as exc:
                return {"ok": False, "error": str(exc)}
            repo_path = sandbox / "repo"
        else:
            local = Path(repo_arg).resolve()
            if not local.exists():
                return {
                    "ok": False,
                    "error": f"repo path not found: {repo_arg}",
                }
            repo_path = local

        cli = [sys.executable, str(script)] + _build_cli_args(
            name, input_args, repo_path,
        )
        r = run_subprocess(cli, timeout_s=600.0)

        if r["exit_code"] != 0:
            return {
                "ok": False,
                "error": "script crashed",
                "exit_code": r["exit_code"],
                "stderr_tail": r["stderr"][-500:],
            }

        try:
            return json.loads(r["stdout"])
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "script did not emit JSON",
                "stdout_tail": r["stdout"][-500:],
            }
    finally:
        if sandbox and sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
