"""Real ambient desktop/screen awareness -- opt-in, off by default.

When enabled, a background loop (see main_new.py's `_screen_context_loop`,
mirroring `_economic_calendar_loop`'s architecture) periodically captures a
real screenshot via `computer_use_tool.take_screenshot()` -- the same
read-only, ungated capability already exposed as a Claude tool -- and asks
Claude's vision API to describe what's actually on screen in one or two
factual sentences ("what app is focused, what the user appears to be
working on"). Only that derived text summary is kept; the raw screenshot
is discarded immediately after description, never written to disk or
memory -- this is ambient context for conversation, not a recording
feature.

The resulting summary feeds into main_new.py's per-turn system-prompt
assembly (`_live_system_context`) so Nancy can reference what's on screen
without the user first having to ask her to look. Architecture mirrors
economic_calendar.py: this module is pure capture/describe/state, with no
knowledge of the WebSocket manager or Telegram -- main_new.py owns the loop
and any notification, this module just answers "what's on screen right
now" honestly, including "nothing yet" or a real error.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import computer_use_tool

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CAPTURE_INTERVAL_S = 45.0

_enabled = False
_last_summary: Optional[str] = None
_last_at: Optional[float] = None
_last_error: Optional[str] = None


def is_enabled() -> bool:
    return _enabled


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = value
    if not value:
        _clear()


def _clear() -> None:
    global _last_summary, _last_at, _last_error
    _last_summary = None
    _last_at = None
    _last_error = None


def status() -> Dict[str, Any]:
    return {
        "enabled": _enabled,
        "last_summary": _last_summary,
        "last_at": _last_at,
        "error": _last_error,
        "configured": bool(ANTHROPIC_API_KEY),
    }


def context_line() -> str:
    """One line for _live_system_context() -- empty string (contributes
    nothing) unless screen awareness is actually on and has a real fix."""
    if not _enabled or not _last_summary:
        return ""
    age_s = time.time() - _last_at if _last_at else None
    age = f"{int(age_s)}s ago" if age_s is not None else "just now"
    return f"Live screen context (captured {age}): {_last_summary}"


async def _describe_screenshot(image_b64: str) -> Optional[str]:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                    {"type": "text", "text": (
                        "In 1-2 factual sentences, describe what application/window is focused and what "
                        "the user appears to be working on right now. Only describe what is actually "
                        "visible in the image -- no guessing beyond it, no commentary, no preamble."
                    )},
                ],
            }],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
        return text or None
    except Exception as e:
        logger.warning("screen_context: vision description failed: %s", e)
        return None


async def capture_now() -> Dict[str, Any]:
    """Real one-shot capture + describe -- used by both the background loop
    and an on-demand refresh from the frontend. Never fabricates a summary:
    a failed screenshot or an unconfigured vision key returns a real error,
    not a stale or guessed description."""
    global _last_summary, _last_at, _last_error
    result = computer_use_tool.take_screenshot()
    if not result.get("success"):
        _last_error = result.get("error", "screenshot failed")
        logger.warning("screen_context: capture failed: %s", _last_error)
        return {"success": False, "error": _last_error}

    image_b64 = result.get("_image_base64")
    summary = await _describe_screenshot(image_b64) if image_b64 else None
    if summary is None:
        _last_error = (
            "vision description unavailable -- ANTHROPIC_API_KEY not configured, "
            "or the vision call failed"
        )
        return {"success": False, "error": _last_error}

    _last_summary = summary
    _last_at = time.time()
    _last_error = None
    return {"success": True, "summary": summary, "at": _last_at}


def next_tick_interval_s() -> float:
    """Fast poll (2s) while disabled, so toggling it on takes effect almost
    immediately; the real capture cadence while enabled is CAPTURE_INTERVAL_S."""
    return 2.0 if not _enabled else CAPTURE_INTERVAL_S
