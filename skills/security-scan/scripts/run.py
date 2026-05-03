#!/usr/bin/env python3
"""security-scan skill — SAST + secrets + (optional) container CVE scan.

Runs Semgrep + Bandit (SAST) and gitleaks (secrets) in parallel, and
optionally trivy (container CVE) when --scan-types includes "container"
and --image-name is given.

Findings are deduplicated by (file, line, rule_id) keeping the highest
severity, and all messages pass through token-shape redaction so secret
material can't leak through skill output.

Usage:
    python skills/security-scan/scripts/run.py \\
        --repo-path PATH [--scan-types sast,secrets,container] \\
        [--image-name OWNER/NAME]

Output: single JSON object on stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _shared.redact import redact_tokens  # noqa: E402
from _shared.subprocess_helper import hash_inputs  # noqa: E402


_SEV_RANK = {
    "info": 0, "informational": 0,
    "low": 1,
    "medium": 2, "moderate": 2, "warning": 2,
    "high": 3, "error": 3,
    "critical": 4,
}


async def _run_async(cmd: list[str], cwd: str | None = None,
                     timeout_s: float = 300.0) -> dict:
    """Async subprocess runner — security-scan needs parallelism."""
    import time
    t0 = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s,
            )
            timed_out = False
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = b"", b"timeout"
            timed_out = True
    except FileNotFoundError as exc:
        return {
            "exit_code": -1, "stdout": "",
            "stderr": f"binary not found: {exc.filename}",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "timed_out": False,
        }
    return {
        "exit_code": proc.returncode if not timed_out else -1,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "timed_out": timed_out,
    }


async def _run_scanners(repo: Path, scan_types: set[str],
                         image_name: str) -> tuple[list[dict], list[str]]:
    tasks: list[tuple[str, asyncio.Task]] = []
    if "sast" in scan_types and shutil.which("semgrep"):
        tasks.append(("semgrep", asyncio.create_task(_run_async(
            ["semgrep", "--config=auto", "--json", "--quiet"], cwd=str(repo),
        ))))
    if "sast" in scan_types and shutil.which("bandit"):
        tasks.append(("bandit", asyncio.create_task(_run_async(
            ["bandit", "-r", str(repo), "-f", "json", "-q"],
        ))))
    if "secrets" in scan_types and shutil.which("gitleaks"):
        tasks.append(("gitleaks", asyncio.create_task(_run_async(
            ["gitleaks", "detect", "--no-banner",
             "--report-format=json", "--report-path=-"],
            cwd=str(repo),
        ))))
    if "container" in scan_types and image_name and shutil.which("trivy"):
        tasks.append(("trivy", asyncio.create_task(_run_async(
            ["trivy", "image", "--quiet", "--format=json", image_name],
        ))))

    findings: list[dict] = []
    tools_run: list[str] = []
    if not tasks:
        return findings, tools_run

    for tool, task in tasks:
        res = await task
        tools_run.append(tool)
        if not res.get("stdout"):
            continue
        try:
            data = json.loads(res["stdout"])
        except json.JSONDecodeError:
            continue

        if tool == "semgrep":
            for r in data.get("results", []):
                findings.append({
                    "tool": "semgrep",
                    "rule_id": r.get("check_id"),
                    "file": r.get("path"),
                    "line": r.get("start", {}).get("line"),
                    "severity": (r.get("extra", {}).get("severity") or "info").lower(),
                    "message": r.get("extra", {}).get("message", ""),
                })
        elif tool == "bandit":
            for r in data.get("results", []):
                findings.append({
                    "tool": "bandit",
                    "rule_id": r.get("test_id"),
                    "file": r.get("filename"),
                    "line": r.get("line_number"),
                    "severity": (r.get("issue_severity") or "low").lower(),
                    "message": r.get("issue_text", ""),
                })
        elif tool == "gitleaks":
            items = data if isinstance(data, list) else []
            for r in items:
                findings.append({
                    "tool": "gitleaks",
                    "rule_id": r.get("RuleID"),
                    "file": r.get("File"),
                    "line": r.get("StartLine"),
                    "severity": "critical",
                    "message": "secret leak: " + (r.get("Description") or "")[:80],
                })
        elif tool == "trivy":
            for res_item in data.get("Results", []):
                for v in res_item.get("Vulnerabilities") or []:
                    findings.append({
                        "tool": "trivy",
                        "rule_id": v.get("VulnerabilityID"),
                        "file": v.get("PkgName"),
                        "line": None,
                        "severity": (v.get("Severity") or "unknown").lower(),
                        "message": (v.get("Title") or "")[:120],
                    })

    return findings, tools_run


def _dedup(findings: list[dict]) -> list[dict]:
    deduped: dict[tuple, dict] = {}
    for f in findings:
        key = (f.get("file"), f.get("line"), f.get("rule_id"))
        existing = deduped.get(key)
        if not existing or _SEV_RANK.get(f["severity"], 0) > _SEV_RANK.get(
            existing["severity"], 0
        ):
            deduped[key] = f
    return list(deduped.values())


async def main_async() -> int:
    ap = argparse.ArgumentParser(description="security-scan skill")
    ap.add_argument("--repo-path", required=True)
    ap.add_argument(
        "--scan-types", default="sast,secrets",
        help="comma-separated subset of sast,secrets,container",
    )
    ap.add_argument("--image-name", default="")
    args = ap.parse_args()

    repo = Path(args.repo_path).resolve()
    if not repo.exists():
        print(json.dumps({"ok": False, "error": f"repo not found: {repo}"}))
        return 1

    scan_types = {s.strip() for s in args.scan_types.split(",") if s.strip()}
    findings, tools_run = await _run_scanners(repo, scan_types, args.image_name)

    if not tools_run:
        warning = (
            "no scan tools available — install semgrep / gitleaks / "
            "bandit / trivy (or scan_types omits all available tools)"
        )
        print(json.dumps({
            "ok": True, "findings": [], "by_severity": {},
            "scan_types_run": [], "secrets_redacted_in_output": True,
            "tokens_redacted_count": 0,
            "warnings": [warning],
            "cache_key": hash_inputs([*sorted(scan_types)]),
        }, indent=2))
        return 0

    deduped = _dedup(findings)
    redactions = 0
    by_severity: dict[str, int] = {}
    for f in deduped:
        msg, n = redact_tokens(f.get("message", ""))
        f["message"] = msg
        redactions += n
        sev = f["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    output = {
        "ok": True,
        "findings": deduped[:200],
        "by_severity": by_severity,
        "scan_types_run": tools_run,
        "secrets_redacted_in_output": True,
        "tokens_redacted_count": redactions,
        "cache_key": hash_inputs([*sorted(scan_types)]),
    }
    print(json.dumps(output, indent=2))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
