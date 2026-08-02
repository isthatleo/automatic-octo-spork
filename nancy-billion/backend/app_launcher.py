"""Real GUI application launching -- the equivalent of double-clicking an
app icon or a file, distinct from execute_command (terminal_tool.py), which
runs an arbitrary shell command line and requires the model to already know
OS-specific launch syntax itself.

Windows uses `start` (via cmd), which resolves common app names through
Windows' own registered "App Paths" (so 'chrome', 'notepad', 'code',
'explorer' etc. all work without a hardcoded name -> executable-path table
here); macOS uses `open -a`; Linux uses `xdg-open`.
"""

from __future__ import annotations

import asyncio
import os
import platform
from typing import Any, Dict, List, Optional

# Real, confirmed-live ambiguity: "docker" resolves via PATH/App Paths to the
# Docker CLI (docker.exe), not the GUI app -- running it bare just prints
# help text and exits almost instantly, which `start ""` reports as a clean
# success (exit code 0) even though nothing was actually launched. The real
# GUI app is "Docker Desktop.exe", which has no short PATH alias at all, so
# generic name resolution can never find it on its own. Checked at call time
# (not import time) since Docker may be installed after this module loads.
_WINDOWS_APP_OVERRIDES = {
    "docker": [
        r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
        r"C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe",
    ],
}


async def open_application(target: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
    target = target.strip()
    if not target:
        return {"success": False, "error": "target is required"}
    args = args or []
    system = platform.system()

    if system == "Windows":
        for candidate in _WINDOWS_APP_OVERRIDES.get(target.lower(), []):
            if os.path.isfile(candidate):
                target = candidate
                break

    if system == "Windows":
        # The empty "" after `start` is a deliberate placeholder for the
        # window-title argument `start` expects first -- without it, `start`
        # can misinterpret a quoted target as the title instead of the thing
        # to open.
        cmd = ["cmd", "/c", "start", "", target, *args]
    elif system == "Darwin":
        is_url_or_path = target.startswith(("http://", "https://", "/"))
        cmd = ["open", target, *args] if is_url_or_path else ["open", "-a", target, *args]
    else:
        cmd = ["xdg-open", target, *args]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            # Real GUI apps commonly don't exit promptly (they detach and
            # keep running) -- not finishing within 5s isn't itself a
            # failure signal, unlike execute_command's real shell commands.
            return {"success": True, "target": target, "note": "launched (still running)"}
        if proc.returncode not in (0, None):
            return {"success": False, "error": stderr.decode(errors="replace").strip() or f"exit code {proc.returncode}"}
        return {"success": True, "target": target}
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}
