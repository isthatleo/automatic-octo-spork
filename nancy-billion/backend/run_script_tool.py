"""Real script pre-processing for scheduled jobs -- ported from Hermes's
cron/jobs.py design. A job can run a real, sandboxed script and either
deliver its stdout directly (a classic watchdog pattern: "check if X
happened, print a message only if it did") or have its output injected as
real collected data into an agent prompt, so the agent reasons over
genuinely fresh data instead of guessing at it. This is more general than
run_skill/agent_task because it separates deterministic data-collection
(a script, no LLM involved) from the LLM call that turns that data into a
response -- the same split Hermes's cron scripts use.

Scripts must live under SCRIPTS_DIR; the path is resolved and verified to
stay inside it before execution, refusing any `..` traversal attempt.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).parent / "scripts"
SCRIPT_TIMEOUT_S = 60.0
MAX_OUTPUT_CHARS = 4000
# The same "nothing genuinely new to report" convention already used in
# blueprint_catalog.py's prompt templates (news-digest, important-mail) --
# one sentinel, one meaning, everywhere in this codebase.
SILENT_SENTINEL = "[SILENT]"

_INTERPRETERS: Dict[str, list] = {
    ".py": ["python"],
    ".sh": ["bash"],
    ".bash": ["bash"],
    ".ps1": ["powershell", "-NoProfile", "-File"],
}

_SECRET_LINE_RE = re.compile(r"(?im)^([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS)[A-Z0-9_]*)\s*[=:]\s*.+$")
_SECRET_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)


def _redact(text: str) -> str:
    """Best-effort secret redaction on script output before it's ever
    injected into a prompt or delivered as a message -- a script's own
    debug/env output could easily contain a credential it needed to do its
    job (an API key it read to call some service, say)."""
    return _SECRET_LINE_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)


def resolve_script_path(script: str) -> Optional[Path]:
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    root = SCRIPTS_DIR.resolve()
    candidate = (SCRIPTS_DIR / script).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.suffix not in _INTERPRETERS or not candidate.is_file():
        return None
    return candidate


async def run_script(script: str, no_agent: bool = False) -> Dict[str, Any]:
    """Runs a real sandboxed script. `silent` is True when the script's own
    last non-empty stdout line is the [SILENT] sentinel -- a real "nothing
    to report this run" signal the caller should honor rather than
    delivering an empty/filler message."""
    path = resolve_script_path(script)
    if path is None:
        return {"success": False, "error": f"Script not found or outside the sandbox ({SCRIPTS_DIR}): {script!r}"}

    interpreter = _INTERPRETERS[path.suffix]
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV_RE.search(k)}

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *interpreter, str(path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=SCRIPT_TIMEOUT_S)
    except asyncio.TimeoutError:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return {"success": False, "error": f"Script exceeded {SCRIPT_TIMEOUT_S:.0f}s"}
    except Exception as e:
        return {"success": False, "error": f"Failed to run script: {e}"}

    stdout = _redact(stdout_bytes.decode("utf-8", errors="replace"))[:MAX_OUTPUT_CHARS]
    stderr = stderr_bytes.decode("utf-8", errors="replace")[:1000]

    if proc.returncode != 0:
        return {"success": False, "error": f"Script exited {proc.returncode}: {stderr.strip() or '(no stderr)'}"}

    lines = [l for l in stdout.strip().splitlines() if l.strip()]
    silent = bool(lines) and lines[-1].strip() == SILENT_SENTINEL
    return {"success": True, "stdout": stdout.strip(), "silent": silent}
