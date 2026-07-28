"""Real minimal node-agent -- the companion service that runs on a SECOND,
paired machine (not this backend's own process) so node_host.py has a real
node to dispatch to. Ported from OpenClaw's node-host device-pairing model.

Run standalone on the node machine: `python node_agent_stub.py`
(reads NODE_SHARED_SECRET and NODE_AGENT_PORT from its own environment).
Every request must carry the shared secret in X-Node-Secret -- there is no
other auth here, so this should only ever be run on a private/trusted
network, matching how a paired device is expected to be used (LAN, VPN,
or an SSH tunnel), never exposed directly to the public internet.
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


@app.get("/health")
async def health():
    return {"success": True, "configured": bool(NODE_SHARED_SECRET)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("NODE_AGENT_PORT", "8100"))
    uvicorn.run(app, host="0.0.0.0", port=port)
