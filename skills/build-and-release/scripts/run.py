#!/usr/bin/env python3
"""build-and-release skill — build wheel / npm tarball / docker image.

Side-effecting: pushes to a registry only when --no-dry-run is passed AND
the build succeeded. Idempotent by content digest (re-pushing the same
artifact is a no-op at the registry level).

Usage:
    python skills/build-and-release/scripts/run.py [--repo-path PATH] \\
        --target wheel|npm|docker --version SEMVER \\
        [--image-name OWNER/NAME] [--no-dry-run]
    python skills/build-and-release/scripts/run.py --repo-url URL [--ref REF] \\
        --target wheel ...

Repo resolution:
    --repo-path PATH    local git checkout (default: $PWD)
    --repo-url URL      shallow-clone this GitHub URL (overrides --repo-path)
    --ref REF           branch/tag/sha when --repo-url is given (default: main)

Output: single JSON object on stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _shared.repo_resolver import resolve_repo  # noqa: E402
from _shared.subprocess_helper import run_subprocess  # noqa: E402


def _build_wheel(repo: Path, version: str, dry_run: bool) -> dict:
    build = run_subprocess(["python", "-m", "build", "--wheel"], cwd=str(repo))
    if build["exit_code"] != 0:
        return {
            "ok": False,
            "target": "wheel",
            "error": "build failed",
            "stderr_tail": build["stderr"][-500:],
        }
    dist = repo / "dist"
    wheels = sorted(
        dist.glob(f"*-{version}-*.whl"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not wheels:
        return {"ok": False, "target": "wheel", "error": "no wheel produced"}
    digest = "sha256:" + hashlib.sha256(wheels[0].read_bytes()).hexdigest()
    pushed = False
    push_log = ""
    if not dry_run:
        twine = run_subprocess(["twine", "upload", str(wheels[0])], cwd=str(repo))
        pushed = twine["exit_code"] == 0
        push_log = (twine["stdout"][-500:] + twine["stderr"][-500:])
    return {
        "ok": True,
        "target": "wheel",
        "artifact": str(wheels[0].name),
        "digest": digest,
        "pushed": pushed,
        "push_log_tail": push_log if pushed else None,
    }


def _build_npm(repo: Path, dry_run: bool) -> dict:
    build = run_subprocess(["npm", "run", "build"], cwd=str(repo))
    if build["exit_code"] != 0:
        return {
            "ok": False, "target": "npm", "error": "build failed",
            "stderr_tail": build["stderr"][-500:],
        }
    pack = run_subprocess(["npm", "pack", "--quiet"], cwd=str(repo))
    tarball_name = (
        pack["stdout"].strip().splitlines()[-1] if pack["stdout"] else ""
    )
    digest = ""
    if tarball_name:
        tar_path = repo / tarball_name
        if tar_path.exists():
            digest = "sha256:" + hashlib.sha256(tar_path.read_bytes()).hexdigest()
    pushed = False
    push_log = ""
    if not dry_run:
        publish = run_subprocess(
            ["npm", "publish", "--access=public"], cwd=str(repo),
        )
        pushed = publish["exit_code"] == 0
        push_log = publish["stdout"][-500:]
    return {
        "ok": True,
        "target": "npm",
        "artifact": tarball_name,
        "digest": digest,
        "pushed": pushed,
        "push_log_tail": push_log if pushed else None,
    }


def _build_docker(repo: Path, version: str, image_name: str, dry_run: bool) -> dict:
    if not image_name:
        return {
            "ok": False, "target": "docker",
            "error": "image_name required for docker target",
        }
    tag = f"{image_name}:{version}"
    build = run_subprocess(["docker", "build", "-t", tag, "."], cwd=str(repo))
    if build["exit_code"] != 0:
        return {
            "ok": False, "target": "docker", "error": "docker build failed",
            "stderr_tail": build["stderr"][-500:],
        }
    inspect = run_subprocess(
        ["docker", "inspect", "--format={{index .RepoDigests 0}}", tag],
    )
    digest = inspect["stdout"].strip() or (
        f"sha256:{hashlib.sha256(tag.encode()).hexdigest()[:64]}"
    )
    pushed = False
    push_log = ""
    if not dry_run:
        push = run_subprocess(["docker", "push", tag])
        pushed = push["exit_code"] == 0
        push_log = push["stdout"][-500:]
    return {
        "ok": True,
        "target": "docker",
        "artifact": tag,
        "digest": digest,
        "pushed": pushed,
        "push_log_tail": push_log if pushed else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="build-and-release skill")
    ap.add_argument("--repo-path", default=os.getcwd(),
                    help="local git checkout (default: current directory)")
    ap.add_argument("--repo-url", default="",
                    help="GitHub URL to shallow-clone (overrides --repo-path)")
    ap.add_argument("--ref", default="main",
                    help="branch/tag/sha when --repo-url is given")
    ap.add_argument("--target", default="", help="wheel|npm|docker")
    ap.add_argument("--version", default="")
    ap.add_argument("--image-name", default="")
    ap.add_argument(
        "--no-dry-run", action="store_true",
        help="actually push to registry; default is dry_run=true",
    )
    args = ap.parse_args()

    if args.target not in {"wheel", "npm", "docker"}:
        print(json.dumps({
            "ok": False,
            "error": f"target must be wheel|npm|docker, got {args.target!r}",
        }))
        return 0
    if not args.version:
        print(json.dumps({
            "ok": False,
            "error": "version is required (semver)",
        }))
        return 0

    repo, cleanup = resolve_repo(args.repo_path, args.repo_url, args.ref)
    try:
        dry_run = not args.no_dry_run

        if args.target == "wheel":
            result = _build_wheel(repo, args.version, dry_run)
        elif args.target == "npm":
            result = _build_npm(repo, dry_run)
        else:
            result = _build_docker(repo, args.version, args.image_name, dry_run)

        result.setdefault("version", args.version)
        result.setdefault("dry_run", dry_run)
        print(json.dumps(result, indent=2))
        return 0
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
