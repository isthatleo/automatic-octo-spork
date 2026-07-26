"""Real time-boxed arm/disarm safety switch -- ported from OpenClaw's
phone-control extension. An alternative to a one-off Telegram approval for
risky actions: the user "arms" high-risk operations for a bounded window
(e.g. 10 minutes) so a batch of them can run without a separate approval
prompt each time, then it auto-expires back to requiring approval -- rather
than either always prompting (slow for a real batch of legitimate actions)
or a permanent global toggle (easy to forget was left on).

Persisted so an arm state survives a backend restart within its window.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "arm_switch.json"

DEFAULT_ARM_SECONDS = 600.0  # 10 minutes
MAX_ARM_SECONDS = 3600.0  # 1 hour -- no unbounded/forever arming


def _load() -> dict:
    if not STORE_PATH.exists():
        return {"armed_until": None, "reason": None}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"armed_until": None, "reason": None}


def _save(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data), encoding="utf-8")


def arm(duration_s: float = DEFAULT_ARM_SECONDS, reason: Optional[str] = None) -> dict:
    duration_s = max(1.0, min(duration_s, MAX_ARM_SECONDS))
    armed_until = time.time() + duration_s
    _save({"armed_until": armed_until, "reason": reason})
    logger.info("arm_switch: armed for %.0fs (reason=%s)", duration_s, reason)
    return {"armed": True, "armed_until": armed_until, "duration_s": duration_s}


def disarm() -> dict:
    _save({"armed_until": None, "reason": None})
    logger.info("arm_switch: disarmed")
    return {"armed": False}


def is_armed() -> bool:
    data = _load()
    armed_until = data.get("armed_until")
    if armed_until is None:
        return False
    return time.time() < armed_until


def status() -> dict:
    data = _load()
    armed_until = data.get("armed_until")
    armed = armed_until is not None and time.time() < armed_until
    return {
        "armed": armed,
        "armed_until": armed_until if armed else None,
        "remaining_s": max(0.0, armed_until - time.time()) if armed else 0.0,
        "reason": data.get("reason") if armed else None,
    }
