"""Real time-boxed lockdown mode -- the inverse of arm_switch.py. Where
arming REDUCES friction for a batch of legitimate actions, lockdown
INCREASES it: while active, main_new.py's _voice_mismatch() treats anything
that isn't a real, matching voice sample (including plain typed text, which
has no voice at all to check) as suspicious enough to force a Telegram
approval prompt for any sensitive tool call -- overriding arm_switch, which
would otherwise skip it. Auto-expires back to normal rather than needing to
be remembered and manually turned off.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "lockdown_switch.json"

DEFAULT_LOCKDOWN_SECONDS = 3600.0  # 1 hour
MAX_LOCKDOWN_SECONDS = 86400.0  # 24 hours -- bounded, same reasoning as arm_switch


def _load() -> dict:
    if not STORE_PATH.exists():
        return {"locked_until": None, "reason": None}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"locked_until": None, "reason": None}


def _save(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data), encoding="utf-8")


def enable(duration_s: float = DEFAULT_LOCKDOWN_SECONDS, reason: Optional[str] = None) -> dict:
    duration_s = max(1.0, min(duration_s, MAX_LOCKDOWN_SECONDS))
    locked_until = time.time() + duration_s
    _save({"locked_until": locked_until, "reason": reason})
    logger.info("lockdown_switch: enabled for %.0fs (reason=%s)", duration_s, reason)
    return {"locked_down": True, "locked_until": locked_until, "duration_s": duration_s}


def disable() -> dict:
    _save({"locked_until": None, "reason": None})
    logger.info("lockdown_switch: disabled")
    return {"locked_down": False}


def is_active() -> bool:
    data = _load()
    locked_until = data.get("locked_until")
    if locked_until is None:
        return False
    return time.time() < locked_until


def status() -> dict:
    data = _load()
    locked_until = data.get("locked_until")
    active = locked_until is not None and time.time() < locked_until
    return {
        "locked_down": active,
        "locked_until": locked_until if active else None,
        "remaining_s": max(0.0, locked_until - time.time()) if active else 0.0,
        "reason": data.get("reason") if active else None,
    }
