"""Subprocess + hashing helpers used by every skill's run.py."""

from __future__ import annotations

import hashlib
import subprocess
import time


def run_subprocess(cmd: list[str], cwd: str | None = None,
                   timeout_s: float = 600.0) -> dict:
    """Run a subprocess synchronously.

    Returns dict with: exit_code, stdout, stderr, duration_ms, timed_out.
    Never raises on tool failure; only on missing binary.
    """
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": -1,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\n[timeout]",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "timed_out": True,
        }
    except FileNotFoundError as exc:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"binary not found: {exc.filename}",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "timed_out": False,
        }


def hash_inputs(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()
