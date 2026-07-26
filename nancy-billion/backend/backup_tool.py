"""Real full backup -- ported from Hermes' backup command (`hermes_cli/subcommands/backup.py`).
Zips the real, load-bearing runtime state (cron jobs, missions, memory,
skills, webhooks -- everything under data/ and skills/) plus a *redacted*
copy of .env (values stripped, keys kept so you can see what was configured)
into a single timestamped archive under backend/backups/. Restore is just
unzipping back over backend/ -- deliberately not a separate "restore" code
path with its own bugs to have.
"""
from __future__ import annotations

import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).parent
BACKUP_DIR = BACKEND_ROOT / "backups"
_SECRET_LINE_RE = re.compile(r'^([A-Za-z0-9_]+)\s*=\s*(.*)$')


def _redact_env(env_path: Path) -> str:
    """Keeps every KEY= line (so a restore knows what to re-populate) but
    strips the actual value -- an exported backup zip is exactly the kind of
    file that could end up somewhere it shouldn't (a shared drive, an
    email), and a real secret in it would be a genuine leak."""
    if not env_path.exists():
        return ""
    lines_out = []
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines_out.append(line)
            continue
        m = _SECRET_LINE_RE.match(stripped)
        if m:
            lines_out.append(f"{m.group(1)}=<redacted>")
        else:
            lines_out.append(line)
    return "\n".join(lines_out)


def create_backup() -> Dict[str, Any]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = BACKUP_DIR / f"nancy-backup-{timestamp}.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            data_dir = BACKEND_ROOT / "data"
            if data_dir.exists():
                for f in data_dir.rglob("*"):
                    if f.is_file():
                        zf.write(f, arcname=str(f.relative_to(BACKEND_ROOT)))

            skills_dir = BACKEND_ROOT / "skills"
            if skills_dir.exists():
                for f in skills_dir.rglob("*"):
                    if f.is_file():
                        zf.write(f, arcname=str(f.relative_to(BACKEND_ROOT)))

            env_path = BACKEND_ROOT / ".env"
            redacted = _redact_env(env_path)
            if redacted:
                zf.writestr(".env.redacted", redacted)

        size_bytes = zip_path.stat().st_size
        logger.info("backup_tool: created %s (%d bytes)", zip_path, size_bytes)
        return {"success": True, "path": str(zip_path), "size_bytes": size_bytes}
    except Exception as e:
        logger.exception("backup_tool: backup failed")
        return {"success": False, "error": str(e)}


def list_backups() -> list[Dict[str, Any]]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(
        (
            {"filename": f.name, "path": str(f), "size_bytes": f.stat().st_size, "created": f.stat().st_mtime}
            for f in BACKUP_DIR.glob("nancy-backup-*.zip")
        ),
        key=lambda b: b["created"],
        reverse=True,
    )


BACKUP_TOOLS = [
    {
        "name": "create_backup",
        "description": (
            "Create a real backup zip of Nancy's runtime data (cron jobs, missions, memory, "
            "skills) plus a redacted .env, saved under backend/backups/. Requires the user's "
            "explicit yes/no approval first, same as any other write."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]
