"""Real minimal node-agent -- the companion service that runs on a SECOND,
paired machine (not this backend's own process) so node_host.py has a real
node to dispatch to. Ported from OpenClaw's node-host device-pairing model.

Run standalone on the node machine: `python node_agent_stub.py`
(reads NODE_SHARED_SECRET and NODE_AGENT_PORT from its own environment).
Every request must carry the shared secret in X-Node-Secret -- there is no
other auth here, so this should only ever be run on a private/trusted
network, matching how a paired device is expected to be used (LAN, VPN,
or an SSH tunnel), never exposed directly to the public internet.

Extra dependencies this file needs, NOT in backend/requirements.txt (this
runs natively on the Windows node, never inside the Linux backend
container, so it has its own footprint): `pip install pywinauto pywin32`.
Without pywinauto specifically, /list_elements and /click_element (the
numbered-overlay computer-use tools) fail with "No module named
'pywinauto'" -- everything else in this file (screenshots, mouse/keyboard,
clipboard, open_application) only needs pywin32, which most Windows Python
installs already have.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Nancy Node Agent")

NODE_SHARED_SECRET = os.getenv("NODE_SHARED_SECRET")


def _check_secret(x_node_secret: Optional[str]) -> None:
    if not NODE_SHARED_SECRET:
        raise HTTPException(status_code=503, detail="NODE_SHARED_SECRET not configured on this node agent")
    if x_node_secret != NODE_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="invalid or missing X-Node-Secret")


class ExecuteRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: float = 30.0


class OpenApplicationRequest(BaseModel):
    target: str
    args: Optional[list[str]] = None


@app.post("/execute_command")
async def execute_command(req: ExecuteRequest, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        proc = await asyncio.create_subprocess_shell(
            req.command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=req.cwd or None,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=req.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"success": False, "error": f"timed out after {req.timeout:.0f}s"}
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout_b.decode(errors="replace")[:8000],
            "stderr": stderr_b.decode(errors="replace")[:8000],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/read_file")
async def read_file(path: str, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    p = Path(path).expanduser()
    if not p.is_file():
        return {"success": False, "error": f"no such file: {path}"}
    try:
        return {"success": True, "content": p.read_text(encoding="utf-8", errors="replace")[:200_000]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/screenshot")
async def screenshot(x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        import base64
        import io
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {"success": True, "image_base64": base64.b64encode(buf.getvalue()).decode("ascii")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/camera_snapshot")
async def camera_snapshot(x_node_secret: Optional[str] = Header(None)):
    """Real, single, on-demand webcam frame -- opens the camera, grabs
    exactly one frame, closes it immediately. Never left running: this is
    "look right now" (the user explicitly asked in this turn), not ambient
    surveillance -- there is no separate "start watching" endpoint."""
    _check_secret(x_node_secret)
    try:
        import base64
        import cv2
        cam = cv2.VideoCapture(0)
        try:
            if not cam.isOpened():
                return {"success": False, "error": "No camera found or it's in use by another application."}
            # A cold-started webcam's first frame or two is often black/
            # unexposed -- read and discard a couple of warmup frames before
            # keeping one.
            for _ in range(3):
                ok, frame = cam.read()
            if not ok or frame is None:
                return {"success": False, "error": "Camera opened but returned no frame."}
            ok, buf = cv2.imencode(".png", frame)
            if not ok:
                return {"success": False, "error": "Failed to encode the captured frame."}
            return {"success": True, "image_base64": base64.b64encode(buf.tobytes()).decode("ascii")}
        finally:
            cam.release()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/open_application")
async def open_application_route(req: OpenApplicationRequest, x_node_secret: Optional[str] = Header(None)):
    """Real GUI app launching on THIS (the node agent's own) machine --
    the actual point of running this stub on the real Windows desktop
    rather than inside the main backend's own Docker container, which has
    no display/GUI access at all (confirmed live: 'chrome' fails there with
    a missing DISPLAY / missing xdg-open error, not a real launch)."""
    _check_secret(x_node_secret)
    import app_launcher
    return await app_launcher.open_application(req.target, req.args)


class ClipboardWriteRequest(BaseModel):
    text: str


@app.post("/clipboard_read")
async def clipboard_read_route(x_node_secret: Optional[str] = Header(None)):
    """Real OS clipboard read -- another real-hardware/session-scoped
    action the container has no path to (there's no shared clipboard
    between a headless Linux container and the user's real desktop)."""
    _check_secret(x_node_secret)
    try:
        import pyperclip
        return {"success": True, "text": pyperclip.paste()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/clipboard_write")
async def clipboard_write_route(req: ClipboardWriteRequest, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        import pyperclip
        pyperclip.copy(req.text)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


####################################################################
# Real computer-use: numbered-element overlays + mouse/keyboard input.
# Uses pywinauto (UI Automation backend) + pywin32 -- NOT part of the
# Docker backend's requirements.txt (this script runs standalone on the
# real Windows desktop, its own separate dependency footprint). Install
# with `pip install pywinauto pywin32` on the node machine; every endpoint
# below degrades to a real, honest error if they're missing rather than
# crashing the whole agent.
####################################################################

# In-memory cache of the last real element enumeration, keyed by the
# number shown in the overlay -- click_element looks a number up here.
# Ephemeral by design (a fresh list_elements call replaces it); numbers
# are only ever meaningful against the overlay image they were rendered on.
_last_elements: dict[int, dict] = {}

# UI Automation control types worth offering as click targets -- excludes
# purely structural/decorative types (Pane, Group, Custom, Separator, ...)
# so the numbered list stays to genuinely actionable elements.
_ACTIONABLE_TYPES = {
    "Button", "Edit", "CheckBox", "RadioButton", "ComboBox", "Hyperlink",
    "MenuItem", "TabItem", "ListItem", "TreeItem", "Text", "SplitButton",
}


def _foreground_window():
    import win32gui
    from pywinauto import Application

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("No foreground window (desktop may be locked or nothing is focused).")
    app = Application(backend="uia").connect(handle=hwnd)
    return app.window(handle=hwnd), hwnd


class ClickElementRequest(BaseModel):
    number: int
    background: bool = False


class MouseMoveRequest(BaseModel):
    x: int
    y: int


class MouseClickRequest(BaseModel):
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"
    double: bool = False


class MouseScrollRequest(BaseModel):
    amount: int = -3  # negative scrolls down, matches pyautogui's convention


class KeyboardTypeRequest(BaseModel):
    text: str


class KeyboardKeyRequest(BaseModel):
    key: str  # e.g. "enter", "tab", "ctrl+c" (pyautogui hotkey syntax)


@app.post("/list_elements")
async def list_elements(x_node_secret: Optional[str] = Header(None)):
    """Real UI Automation enumeration of the foreground window's actionable
    descendants -- the numbered-element-overlay pattern: each element gets
    a stable number (cached in _last_elements) a subsequent click_element
    call can target, plus a real screenshot with numbered boxes drawn on
    top so a vision-capable caller can decide which number to click,
    instead of guessing raw pixel coordinates."""
    _check_secret(x_node_secret)
    try:
        import base64
        import io
        from PIL import ImageGrab, ImageDraw

        win, hwnd = _foreground_window()
        global _last_elements
        _last_elements = {}
        elements_out = []
        number = 1
        for el in win.descendants():
            try:
                info = el.element_info
                control_type = info.control_type
                if control_type not in _ACTIONABLE_TYPES:
                    continue
                if not el.is_visible():
                    continue
                rect = el.rectangle()
                if rect.width() <= 0 or rect.height() <= 0:
                    continue
                name = (info.name or "").strip()[:80]
                entry = {
                    "number": number, "name": name, "control_type": control_type,
                    "rect": [rect.left, rect.top, rect.right, rect.bottom],
                }
                elements_out.append(entry)
                _last_elements[number] = {
                    "center": (rect.left + rect.width() // 2, rect.top + rect.height() // 2),
                    "hwnd": hwnd, "control": el,
                }
                number += 1
                if number > 60:  # keep the overlay legible -- not every window needs a full audit
                    break
            except Exception:
                continue  # one bad element (stale/inaccessible) shouldn't kill the whole enumeration

        img = ImageGrab.grab()
        draw = ImageDraw.Draw(img)
        for entry in elements_out:
            l, t, r, b = entry["rect"]
            draw.rectangle([l, t, r, b], outline="red", width=2)
            label = str(entry["number"])
            draw.rectangle([l, max(0, t - 16), l + 8 + 8 * len(label), t], fill="red")
            draw.text((l + 2, max(0, t - 15)), label, fill="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        return {
            "success": True, "elements": elements_out,
            "overlay_image_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/click_element")
async def click_element(req: ClickElementRequest, x_node_secret: Optional[str] = Header(None)):
    """Real click on a numbered element from the most recent list_elements
    call. `background=True` attempts a non-focus-stealing click via
    PostMessage (real Windows technique -- works for classic Win32 controls
    that process posted mouse messages, but many modern/UWP/Electron apps
    ignore posted messages and need real input instead). Default
    (background=False) uses pywinauto's real click_input -- moves the
    actual cursor and steals focus, but works reliably everywhere; this is
    the same real tradeoff computer_use_tool.py's local clicking already
    has, not a new limitation."""
    _check_secret(x_node_secret)
    entry = _last_elements.get(req.number)
    if entry is None:
        return {"success": False, "error": f"No element numbered {req.number} -- call list_elements first (numbers don't persist across calls)."}
    try:
        if req.background:
            import win32api
            import win32con
            import win32gui

            hwnd = entry["hwnd"]
            x, y = entry["center"]
            rect = win32gui.GetWindowRect(hwnd)
            local_x, local_y = x - rect[0], y - rect[1]
            lparam = win32api.MAKELONG(local_x, local_y)
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            return {"success": True, "method": "background_postmessage"}
        entry["control"].click_input()
        return {"success": True, "method": "click_input"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/mouse_move")
async def mouse_move(req: MouseMoveRequest, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        import pyautogui
        pyautogui.moveTo(req.x, req.y)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/mouse_click")
async def mouse_click(req: MouseClickRequest, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        import pyautogui
        kwargs = {"button": req.button}
        if req.x is not None and req.y is not None:
            kwargs["x"], kwargs["y"] = req.x, req.y
        if req.double:
            pyautogui.doubleClick(**kwargs)
        else:
            pyautogui.click(**kwargs)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/mouse_scroll")
async def mouse_scroll(req: MouseScrollRequest, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        import pyautogui
        pyautogui.scroll(req.amount)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/keyboard_type")
async def keyboard_type(req: KeyboardTypeRequest, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        import pyautogui
        pyautogui.write(req.text, interval=0.02)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/keyboard_key")
async def keyboard_key(req: KeyboardKeyRequest, x_node_secret: Optional[str] = Header(None)):
    _check_secret(x_node_secret)
    try:
        import pyautogui
        keys = [k.strip() for k in req.key.split("+")]
        if len(keys) > 1:
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(keys[0])
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/health")
async def health():
    return {"success": True, "configured": bool(NODE_SHARED_SECRET)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("NODE_AGENT_PORT", "8100"))
    uvicorn.run(app, host="0.0.0.0", port=port)
