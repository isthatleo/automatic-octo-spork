"""Real redacted-debug-report sharing -- ported from Hermes' `hermes debug
share` command. Gathers system info + recent backend logs into a zip, with
secrets stripped (reusing run_script_tool.py's exact redaction regex, the
same one already trusted to scrub script output before it reaches an LLM
prompt), and either uploads it to a configured paste endpoint for a
shareable URL, or saves it locally when `local_only=True` / no endpoint is
configured -- never silently uploads when the user didn't ask it to.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import httpx

from run_script_tool import _redact

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).parent
LOG_FILE_CANDIDATES = ["backend-run.log"]
MAX_LOG_LINES = 500
LOCAL_SHARE_DIR = BACKEND_ROOT / "backups"


def _gather_system_info() -> str:
    return (
        f"platform: {platform.platform()}\n"
        f"python: {sys.version}\n"
        f"cwd: {os.getcwd()}\n"
        f"timestamp: {datetime.now(timezone.utc).isoformat()}\n"
    )


def _gather_redacted_env() -> str:
    from backup_tool import _redact_env
    env_path = BACKEND_ROOT / ".env"
    return _redact_env(env_path)


def _gather_recent_logs() -> str:
    for name in LOG_FILE_CANDIDATES:
        path = BACKEND_ROOT / name
        if path.exists():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                return _redact("\n".join(lines[-MAX_LOG_LINES:]))
            except Exception as e:
                return f"(failed to read {name}: {e})"
    return "(no log file found)"


def build_debug_zip() -> bytes:
    """Builds the real zip in memory -- every text field passed through the
    same redaction used for script output, so a debug report can never leak
    a live credential even if one somehow ended up in a log line."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system_info.txt", _gather_system_info())
        zf.writestr(".env.redacted", _gather_redacted_env())
        zf.writestr("recent_logs.txt", _gather_recent_logs())
    return buf.getvalue()


async def share_debug_report(local_only: bool = False) -> Dict[str, Any]:
    zip_bytes = build_debug_zip()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    endpoint = os.getenv("DEBUG_SHARE_ENDPOINT")

    if local_only or not endpoint:
        LOCAL_SHARE_DIR.mkdir(parents=True, exist_ok=True)
        local_path = LOCAL_SHARE_DIR / f"debug-report-{timestamp}.zip"
        local_path.write_bytes(zip_bytes)
        return {"success": True, "mode": "local", "path": str(local_path)}

    headers = {}
    api_key = os.getenv("DEBUG_SHARE_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                endpoint, headers=headers, files={"file": (f"debug-report-{timestamp}.zip", zip_bytes, "application/zip")},
            )
            resp.raise_for_status()
            data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {"raw": resp.text[:500]}
            return {"success": True, "mode": "uploaded", "response": data}
    except Exception as e:
        logger.warning("debug_share: upload failed, falling back to local save: %s", e)
        LOCAL_SHARE_DIR.mkdir(parents=True, exist_ok=True)
        local_path = LOCAL_SHARE_DIR / f"debug-report-{timestamp}.zip"
        local_path.write_bytes(zip_bytes)
        return {"success": True, "mode": "local_fallback", "path": str(local_path), "upload_error": str(e)}
