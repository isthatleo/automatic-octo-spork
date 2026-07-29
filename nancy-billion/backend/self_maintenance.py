"""Real, periodic self-maintenance -- distinct from self_healing.py (which
watches RUNTIME health: CPU/memory/disk, the primary LLM backend). This
audits Billion's own codebase for real known dependency vulnerabilities
(via the free, keyless OSV.dev API -- no new pip dependency, avoiding the
exact pathological pip-resolver backtracking risk already hit once this
session with a heavier tool like pip-audit) and stale TODO/FIXME/XXX
markers -- proactive code hygiene, not operational monitoring.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).parent
REQUIREMENTS_PATH = BACKEND_ROOT / "requirements.txt"
NOTIFIED_VULNS_PATH = BACKEND_ROOT / "data" / "notified_vulns.json"

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"

_TODO_RE = re.compile(r"#\s*(TODO|FIXME|XXX)\b(.*)", re.IGNORECASE)
_SCAN_SKIP_DIRS = {"__pycache__", "data", "skills", ".git", "scripts"}
_REQ_LINE_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)")


def _parse_requirements() -> List[Tuple[str, str]]:
    """Exact-pinned (==) requirements only -- an unpinned/ranged line has no
    single version to check against OSV, so it's skipped rather than guessed."""
    if not REQUIREMENTS_PATH.exists():
        return []
    pkgs = []
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-e"):
            continue
        m = _REQ_LINE_RE.match(line)
        if m:
            pkgs.append((m.group(1), m.group(2)))
    return pkgs


async def check_dependency_vulnerabilities() -> Dict[str, Any]:
    """Real query against OSV.dev's public vulnerability database -- one
    batched request for every exact-pinned package in requirements.txt."""
    pkgs = _parse_requirements()
    if not pkgs:
        return {"success": True, "vulnerabilities": [], "packages_checked": 0}
    queries = [{"package": {"name": name, "ecosystem": "PyPI"}, "version": version} for name, version in pkgs]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(OSV_BATCH_URL, json={"queries": queries})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

    vulnerabilities = []
    for (name, version), result in zip(pkgs, data.get("results", [])):
        vulns = result.get("vulns") or []
        if vulns:
            vulnerabilities.append({
                "package": name, "version": version,
                "vuln_ids": [v.get("id") for v in vulns if v.get("id")],
            })
    return {"success": True, "vulnerabilities": vulnerabilities, "packages_checked": len(pkgs)}


def scan_stale_markers(max_results: int = 30) -> Dict[str, Any]:
    """Real filesystem sweep for TODO/FIXME/XXX comments across the backend
    source tree, skipping generated/data/vendored directories."""
    findings = []
    truncated = False
    for path in BACKEND_ROOT.rglob("*.py"):
        if any(part in _SCAN_SKIP_DIRS for part in path.parts):
            continue
        try:
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                m = _TODO_RE.search(line)
                if m:
                    findings.append({
                        "file": str(path.relative_to(BACKEND_ROOT)), "line": i,
                        "marker": m.group(1).upper(), "text": m.group(2).strip()[:150],
                    })
                    if len(findings) >= max_results:
                        truncated = True
                        return {"success": True, "findings": findings, "truncated": truncated}
        except Exception:
            continue
    return {"success": True, "findings": findings, "truncated": truncated}


def _load_notified_vulns() -> set:
    if not NOTIFIED_VULNS_PATH.exists():
        return set()
    try:
        return set(json.loads(NOTIFIED_VULNS_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_notified_vulns(vuln_ids: set) -> None:
    NOTIFIED_VULNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTIFIED_VULNS_PATH.write_text(json.dumps(sorted(vuln_ids)), encoding="utf-8")


async def run_periodic_check() -> List[str]:
    """Returns human-readable alert messages for real, NEW vulnerabilities
    only (never re-alerts on one already reported) -- the caller (main_new.py)
    handles actually notifying. Stale-marker findings aren't proactively
    pushed (too noisy for a background alert) -- available on demand via
    the run_self_maintenance_check tool instead."""
    result = await check_dependency_vulnerabilities()
    if not result.get("success"):
        logger.info("self_maintenance: vulnerability check failed: %s", result.get("error"))
        return []

    already_notified = _load_notified_vulns()
    new_messages = []
    all_seen = set(already_notified)
    for entry in result["vulnerabilities"]:
        new_ids = [v for v in entry["vuln_ids"] if v not in already_notified]
        if new_ids:
            new_messages.append(
                f"Security notice, Sir: {entry['package']}=={entry['version']} has a known "
                f"vulnerability ({', '.join(new_ids)}). Worth updating when you get a chance."
            )
        all_seen.update(entry["vuln_ids"])
    if all_seen != already_notified:
        _save_notified_vulns(all_seen)
    return new_messages
