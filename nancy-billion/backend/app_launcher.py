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
import platform
from typing import Any, Dict, List, Optional


async def open_application(target: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
    target = target.strip()
    if not target:
        return {"success": False, "error": "target is required"}
    args = args or []
    system = platform.system()

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
