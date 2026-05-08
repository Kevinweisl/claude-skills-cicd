"""Subprocess + hashing helpers used by every skill's run.py."""

from __future__ import annotations

import hashlib
import subprocess
import time


# Install hints for the external scanner / build / package binaries that
# the skills shell out to. Marketplace install ships SKILL.md + scripts;
# the underlying tools are user-installed. When a binary is missing,
# the skill output includes an `install_hint` so Claude can suggest the
# exact command back to the user instead of a bare "command not found".
INSTALL_HINTS = {
    "ruff":         "pip install ruff",
    "pytest":       "pip install pytest",
    "pip-audit":    "pip install pip-audit",
    "semgrep":      "pip install semgrep   # or: brew install semgrep",
    "bandit":       "pip install bandit",
    "build":        "pip install build     # for `python -m build`",
    "twine":        "pip install twine",
    "gitleaks":     "brew install gitleaks (https://github.com/gitleaks/gitleaks#installing)",
    "trivy":        "brew install aquasecurity/trivy/trivy (https://aquasecurity.github.io/trivy/)",
    "npm":          "install Node.js: https://nodejs.org",
    "npx":          "install Node.js: https://nodejs.org",
    "cargo":        "install Rust: https://rustup.rs",
    "cargo-audit":  "cargo install cargo-audit",
    "govulncheck":  "go install golang.org/x/vuln/cmd/govulncheck@latest",
    "go":           "install Go: https://go.dev/dl/",
    "docker":       "install Docker Desktop: https://docker.com",
    "python":       "install Python 3.12+: https://www.python.org/downloads/",
}


def install_hint_for(binary: str) -> str:
    """Return the install hint for a binary name, or a generic fallback."""
    return INSTALL_HINTS.get(
        binary,
        f"`{binary}` is not in PATH; see the project README's Prerequisites "
        "section for the scanner toolchain.",
    )


def run_subprocess(cmd: list[str], cwd: str | None = None,
                   timeout_s: float = 600.0) -> dict:
    """Run a subprocess synchronously.

    Returns dict with: exit_code, stdout, stderr, duration_ms, timed_out.
    On a missing binary, additionally sets `missing_binary` and
    `install_hint` so callers can surface a hint without re-deriving it.
    Never raises on tool failure; only on programmer error (e.g. bad cwd).
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
        binary = exc.filename or (cmd[0] if cmd else "?")
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"binary not found: {binary}",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "timed_out": False,
            "missing_binary": binary,
            "install_hint": install_hint_for(binary),
        }


def hash_inputs(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()
