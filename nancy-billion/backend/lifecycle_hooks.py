"""Real shell-script lifecycle hooks -- ported from Hermes' shell-hooks
subsystem (hermes_cli/subcommands/hooks.py, agent/shell_hooks.py). Lets the
user drop a real script under backend/hooks/<event>.{sh,py,ps1} that fires
whenever that lifecycle event happens (pre_write, pre_tool_call,
post_tool_call, subagent_stop) -- e.g. a pre_write hook that runs a linter,
or a post_tool_call hook that pings a personal webhook.

Consent-gated: the FIRST time a given hook script would run in this backend
process's lifetime, it requires a real Telegram yes/no (a hook script is
arbitrary code the user themselves dropped in, but it should still get one
explicit confirmation before Nancy starts actually executing it on live
events) -- every firing after that in the same process runs without
re-prompting, until a restart resets consent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

HOOKS_DIR = Path(__file__).parent / "hooks"
HOOK_TIMEOUT_S = 15.0
VALID_EVENTS = ("pre_tool_call", "post_tool_call", "pre_write", "subagent_stop")

_INTERPRETERS: Dict[str, list] = {
    ".sh": ["bash"],
    ".py": ["python"],
    ".ps1": ["powershell", "-NoProfile", "-File"],
}

# Per-process consent cache -- resets on restart, matching "first use per
# session" (a session here is this backend's own process lifetime, the same
# scope every other in-memory-only state in this codebase uses).
_consented: Dict[str, bool] = {}


def _find_hook_script(event: str) -> Optional[Path]:
    if event not in VALID_EVENTS:
        return None
    for ext, _ in _INTERPRETERS.items():
        candidate = HOOKS_DIR / f"{event}{ext}"
        if candidate.is_file():
            return candidate
    return None


async def _run_hook_script(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    interpreter = _INTERPRETERS[path.suffix]
    env = dict(os.environ)
    env["NANCY_HOOK_PAYLOAD"] = json.dumps(payload)
    try:
        proc = await asyncio.create_subprocess_exec(
            *interpreter, str(path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=HOOK_TIMEOUT_S)
        return {
            "success": proc.returncode == 0,
            "stdout": stdout_b.decode(errors="replace")[:2000],
            "stderr": stderr_b.decode(errors="replace")[:500],
            "exit_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": f"hook script timed out after {HOOK_TIMEOUT_S:.0f}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def fire_hook(event: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fires `event`'s hook script if one exists. Returns None (a true
    no-op, not an error) when no script is configured for this event --
    the overwhelmingly common case, since hooks are opt-in. Never raises --
    a broken hook script degrades to a logged warning, never breaks the
    real action it's observing."""
    path = _find_hook_script(event)
    if path is None:
        return None

    if not _consented.get(event):
        from telegram_bot import telegram_notifier
        approved = await telegram_notifier.request_approval(
            f"Nancy found a custom hook script for '{event}' ({path.name}). "
            f"Approve running it for the rest of this session?",
            timeout=120.0,
        )
        _consented[event] = approved
        if not approved:
            logger.info("lifecycle_hooks: %s hook not approved, skipping this and future firings this session", event)
            return {"success": False, "error": "hook not approved by user"}

    try:
        result = await _run_hook_script(path, payload)
        if not result.get("success"):
            logger.warning("lifecycle_hooks: %s hook failed: %s", event, result.get("error") or result.get("stderr"))
        return result
    except Exception as e:
        logger.warning("lifecycle_hooks: %s hook raised: %s", event, e)
        return {"success": False, "error": str(e)}


async def test_hook(event: str) -> Dict[str, Any]:
    """Real synthetic-payload tester -- matches Hermes' `hooks test <event>`
    CLI command, exposed here as a callable for a REST/tool wrapper instead
    of a separate CLI (Nancy has no CLI surface of its own)."""
    if event not in VALID_EVENTS:
        return {"success": False, "error": f"unknown event {event!r} -- valid: {', '.join(VALID_EVENTS)}"}
    result = await fire_hook(event, {"test": True, "event": event})
    if result is None:
        return {"success": False, "error": f"no hook script configured for {event} (looked in {HOOKS_DIR})"}
    return result


def list_hooks() -> Dict[str, Any]:
    return {
        "hooks_dir": str(HOOKS_DIR),
        "configured": {event: str(_find_hook_script(event)) for event in VALID_EVENTS if _find_hook_script(event)},
        "consented_this_session": dict(_consented),
    }
