#!/usr/bin/env python3
"""dependency-audit skill — scan dependency manifests for known CVEs.

Detects ecosystems (python / node / rust / go) from manifest files and
fans out to the appropriate auditor (pip-audit, npm audit, cargo audit,
govulncheck). Output normalized into a uniform vulnerability list.

Usage:
    python skills/dependency-audit/scripts/run.py \\
        --repo-path PATH [--ecosystems python,node,...]

Output: single JSON object on stdout.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _shared.subprocess_helper import hash_inputs, run_subprocess  # noqa: E402

import hashlib


def _manifest_hash(repo: Path) -> str:
    """Hash of all manifest files combined — used in cache_key."""
    h = hashlib.sha256()
    for f in ("pyproject.toml", "requirements.txt", "package-lock.json",
              "yarn.lock", "Cargo.lock", "go.sum"):
        p = repo / f
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:32]


def _detect_ecosystems(repo: Path) -> list[str]:
    detected = []
    if (repo / "pyproject.toml").exists() or (repo / "requirements.txt").exists():
        detected.append("python")
    if (repo / "package-lock.json").exists() or (repo / "yarn.lock").exists():
        detected.append("node")
    if (repo / "Cargo.lock").exists():
        detected.append("rust")
    if (repo / "go.sum").exists():
        detected.append("go")
    return detected


def _audit_python(repo: Path) -> dict:
    if not shutil.which("pip-audit"):
        return {"tool": "pip-audit", "error": "binary not installed",
                "vulnerabilities": []}
    r = run_subprocess(["pip-audit", "-f", "json"], cwd=str(repo))
    try:
        data = json.loads(r["stdout"]) if r["stdout"] else {"dependencies": []}
    except json.JSONDecodeError:
        return {"tool": "pip-audit", "error": "JSON parse failed",
                "stderr_tail": r["stderr"][-200:], "vulnerabilities": []}
    vulns = []
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            vulns.append({
                "package": dep.get("name"),
                "id": v.get("id"),
                "severity": v.get("severity") or "unknown",
                "fix_versions": v.get("fix_versions", []),
            })
    return {"tool": "pip-audit", "vulnerabilities": vulns}


def _audit_node(repo: Path) -> dict:
    if not shutil.which("npm"):
        return {"tool": "npm-audit", "error": "npm not installed",
                "vulnerabilities": []}
    r = run_subprocess(["npm", "audit", "--json"], cwd=str(repo))
    try:
        data = json.loads(r["stdout"]) if r["stdout"] else {}
    except json.JSONDecodeError:
        return {"tool": "npm-audit", "error": "JSON parse failed",
                "vulnerabilities": []}
    vulns_obj = data.get("vulnerabilities", {})
    vulns = [
        {
            "package": k,
            "severity": v.get("severity", "unknown"),
            "via": v.get("via", []),
            "range": v.get("range", ""),
        }
        for k, v in vulns_obj.items()
    ]
    out = {"tool": "npm-audit", "vulnerabilities": vulns}
    meta = data.get("metadata", {}).get("vulnerabilities", {})
    if meta:
        out["counts"] = meta
    return out


def _audit_rust(repo: Path) -> dict:
    if not shutil.which("cargo"):
        return {"tool": "cargo-audit", "error": "cargo not installed",
                "vulnerabilities": []}
    r = run_subprocess(
        ["cargo", "audit", "--json", "--no-fetch"], cwd=str(repo),
    )
    try:
        data = json.loads(r["stdout"]) if r["stdout"] else {}
    except json.JSONDecodeError:
        return {"tool": "cargo-audit", "error": "JSON parse failed",
                "vulnerabilities": []}
    vulns = [
        {
            "package": v.get("package", {}).get("name"),
            "id": v.get("advisory", {}).get("id"),
            "severity": "unknown",
        }
        for v in data.get("vulnerabilities", {}).get("list", [])
    ]
    return {"tool": "cargo-audit", "vulnerabilities": vulns}


def _audit_go(repo: Path) -> dict:
    if not shutil.which("govulncheck"):
        return {"tool": "govulncheck", "error": "binary not installed",
                "vulnerabilities": []}
    r = run_subprocess(["govulncheck", "-json", "./..."], cwd=str(repo))
    vulns = []
    for line in r["stdout"].splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "vuln" in obj:
            vulns.append({
                "package": obj["vuln"].get("modulepath"),
                "id": obj["vuln"].get("osv"),
                "severity": "unknown",
            })
    return {"tool": "govulncheck", "vulnerabilities": vulns}


_AUDITORS = {
    "python": _audit_python,
    "node": _audit_node,
    "rust": _audit_rust,
    "go": _audit_go,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="dependency-audit skill")
    ap.add_argument("--repo-path", required=True)
    ap.add_argument(
        "--ecosystems", default="",
        help="comma-separated subset of python,node,rust,go (default: auto)",
    )
    args = ap.parse_args()

    repo = Path(args.repo_path).resolve()
    if not repo.exists():
        print(json.dumps({"ok": False, "error": f"repo not found: {repo}"}))
        return 1

    detected = _detect_ecosystems(repo)
    if args.ecosystems:
        requested = {e.strip() for e in args.ecosystems.split(",") if e.strip()}
        detected = [e for e in detected if e in requested]

    findings_by_ecosystem: dict[str, dict] = {}
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}

    for eco in detected:
        result = _AUDITORS[eco](repo)
        findings_by_ecosystem[eco] = result
        for v in result.get("vulnerabilities", []):
            summary["total"] += 1
            sev = (v.get("severity") or "unknown").lower()
            if sev == "moderate":
                sev = "medium"
            if sev in summary:
                summary[sev] += 1

    output = {
        "ok": True,
        "findings_by_ecosystem": findings_by_ecosystem,
        "summary": summary,
        "ecosystems_detected": detected,
        # cache_key is content-based: ecosystem set + manifest hashes.
        "cache_key": hash_inputs([*sorted(detected), _manifest_hash(repo)]),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
