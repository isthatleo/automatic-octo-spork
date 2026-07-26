"""Real local computer-use: screenshot + mouse/keyboard control of this
machine, via `pyautogui` (no cloud computer-use API, no extra account).
This is the highest-risk capability in this codebase -- unlike a terminal
command (bounded to what a shell command can do) or a file write (bounded to
one file), mouse/keyboard control can do literally anything a human sitting
at this machine could do. Every ACTION (click/type/keypress/scroll/move) is
therefore gated by a real Telegram yes/no approval with no exceptions, no
allowlist of "safe" actions the way terminal_tool.py has one for read-only
shell commands -- there is no analogous safe subset here. take_screenshot()
and get_screen_size() are the only read-only, ungated operations (same tier
as read_file).
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# pyautogui imports Xlib/tkinter at import time on Linux and can fail in a
# headless environment -- deferred import so the rest of the backend still
# starts even where a display isn't available, matching the lazy-import
# pattern already used for fury/neucodec/other optional heavy deps.
_pyautogui = None
_pyautogui_error: str | None = None


def _get_pyautogui():
    global _pyautogui, _pyautogui_error
    if _pyautogui is not None:
        return _pyautogui
    if _pyautogui_error is not None:
        raise RuntimeError(_pyautogui_error)
    try:
        import pyautogui
        pyautogui.FAILSAFE = True  # moving the mouse to a screen corner aborts -- a real physical kill switch
        _pyautogui = pyautogui
        return pyautogui
    except Exception as e:
        _pyautogui_error = f"pyautogui unavailable: {e}"
        raise RuntimeError(_pyautogui_error)


COMPUTER_USE_TOOLS = [
    {
        "name": "take_screenshot",
        "description": "Capture a real screenshot of this machine's screen. Read-only, no approval needed.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_screen_size",
        "description": "Get this machine's real screen resolution. Read-only, no approval needed.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "click_screen",
        "description": (
            "Click at real screen coordinates (from a prior take_screenshot's pixel dimensions). "
            "Requires the user's explicit yes/no approval (sent to their phone) before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"}, "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
                "double": {"type": "boolean"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "move_mouse",
        "description": (
            "Move the mouse cursor to real screen coordinates without clicking. "
            "Requires the user's explicit yes/no approval before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["x", "y"],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Type real text at the current keyboard focus (whatever field/window is active). "
            "Requires the user's explicit yes/no approval before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "press_key",
        "description": (
            "Press a single real keyboard key (e.g. 'enter', 'esc', 'tab', 'f5'). "
            "Requires the user's explicit yes/no approval before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "scroll_screen",
        "description": (
            "Real vertical scroll at the current mouse position (positive = up, negative = down). "
            "Requires the user's explicit yes/no approval before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"amount": {"type": "integer"}},
            "required": ["amount"],
        },
    },
]

# Every action tool needs approval -- there is no safe-by-default subset
# the way terminal_tool.py has for read-only shell commands.
ACTION_TOOLS = {"click_screen", "move_mouse", "type_text", "press_key", "scroll_screen"}


def take_screenshot() -> Dict[str, Any]:
    try:
        pyautogui = _get_pyautogui()
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {
            "success": True,
            "_image_base64": base64.b64encode(buf.getvalue()).decode(),
            "width": img.width,
            "height": img.height,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_screen_size() -> Dict[str, Any]:
    try:
        pyautogui = _get_pyautogui()
        size = pyautogui.size()
        return {"success": True, "width": size.width, "height": size.height}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click_screen(x: int, y: int, button: str = "left", double: bool = False) -> Dict[str, Any]:
    try:
        pyautogui = _get_pyautogui()
        if double:
            pyautogui.doubleClick(x, y, button=button)
        else:
            pyautogui.click(x, y, button=button)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_mouse(x: int, y: int) -> Dict[str, Any]:
    try:
        pyautogui = _get_pyautogui()
        pyautogui.moveTo(x, y)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_text(text: str) -> Dict[str, Any]:
    try:
        pyautogui = _get_pyautogui()
        pyautogui.write(text, interval=0.02)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_key(key: str) -> Dict[str, Any]:
    try:
        pyautogui = _get_pyautogui()
        pyautogui.press(key)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def scroll_screen(amount: int) -> Dict[str, Any]:
    try:
        pyautogui = _get_pyautogui()
        pyautogui.scroll(amount)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
