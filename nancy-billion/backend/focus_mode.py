"""Real focus mode / notification triage. While active, informational
Telegram pushes (self-healing status changes, watch alerts, scheduled
telegram_message cron jobs) are queued instead of sent immediately -- see
main_new.py's _send_or_queue, the one shared chokepoint every informational
push routes through. Approval requests are NEVER queued here (they're
genuinely blocking work, not ambient noise). Queued messages are delivered
as a single consolidated digest the moment focus mode ends, whether that's
a manual disable or its own expiry.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "focus_mode.json"

DEFAULT_FOCUS_SECONDS = 3600.0  # 1 hour
MAX_FOCUS_SECONDS = 28800.0  # 8 hours -- bounded, same reasoning as arm_switch


def _load() -> Dict[str, Any]:
    if not STORE_PATH.exists():
        return {"active_until": None, "queue": []}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        data.setdefault("queue", [])
        return data
    except Exception:
        return {"active_until": None, "queue": []}


def _save(data: Dict[str, Any]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data), encoding="utf-8")


def enable(duration_s: float = DEFAULT_FOCUS_SECONDS) -> Dict[str, Any]:
    duration_s = max(1.0, min(duration_s, MAX_FOCUS_SECONDS))
    active_until = time.time() + duration_s
    data = _load()
    data["active_until"] = active_until
    _save(data)
    logger.info("focus_mode: enabled for %.0fs", duration_s)
    return {"active": True, "active_until": active_until, "duration_s": duration_s}


def is_active() -> bool:
    data = _load()
    active_until = data.get("active_until")
    if active_until is None:
        return False
    return time.time() < active_until


def queue_message(text: str) -> None:
    data = _load()
    data.setdefault("queue", []).append({"text": text, "at": time.time()})
    _save(data)
    logger.info("focus_mode: queued a message (%d total)", len(data["queue"]))


def disable_and_flush() -> List[Dict[str, Any]]:
    """Turns focus mode off and returns whatever was queued while it was
    active -- caller is responsible for actually sending the real digest."""
    data = _load()
    queued = data.get("queue", [])
    _save({"active_until": None, "queue": []})
    logger.info("focus_mode: disabled, flushing %d queued message(s)", len(queued))
    return queued


def check_and_flush_if_expired() -> Optional[List[Dict[str, Any]]]:
    """Called periodically by main_new.py's background loop. Returns the
    queued messages (and clears state) the first time this is called after
    active_until has passed; None if still active or already inactive."""
    data = _load()
    active_until = data.get("active_until")
    if active_until is None or time.time() < active_until:
        return None
    return disable_and_flush()


def status() -> Dict[str, Any]:
    data = _load()
    active_until = data.get("active_until")
    active = active_until is not None and time.time() < active_until
    return {
        "active": active,
        "active_until": active_until if active else None,
        "remaining_s": max(0.0, active_until - time.time()) if active else 0.0,
        "queued_count": len(data.get("queue", [])),
    }
