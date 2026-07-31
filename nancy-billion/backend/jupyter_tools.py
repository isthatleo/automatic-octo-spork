"""Real stateful Python execution via a genuine, persistent IPython kernel
(jupyter_client + ipykernel) -- variables, imports, and function definitions
survive between calls, unlike terminal_tool.py's execute_command which
spawns a fresh subprocess every time. Ported in spirit from Hermes'
"Jupyter Live Kernel for interactive Python" skill (2026-07-31 Hermes-parity
audit): Nancy already had notebook_tools.py (read/edit .ipynb files) and
arbitrary code execution via execute_command, but nothing that actually
kept a live kernel's state across a conversation the way a real Jupyter
session does.

One kernel per process (module-level singleton) -- matches the rest of this
codebase's "one shared resource, not one per request" pattern (llm_backend,
tts_backend). A conversation that wants a truly separate kernel can
`restart_python_kernel` first.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

JUPYTER_TOOLS = [
    {
        "name": "run_python_kernel",
        "description": (
            "Run real Python code in a persistent IPython kernel -- variables, imports, and "
            "function/class definitions from earlier calls in this same conversation are still "
            "there. Returns stdout, the repr of the last expression's value (like a real Jupyter "
            "cell), and any real matplotlib/PIL image output as an image. Prefer this over "
            "execute_command for anything that benefits from keeping state between steps (building "
            "up a dataframe, iterating on a plot, etc.) -- use execute_command instead for shell "
            "commands or one-shot scripts where state carrying over would be surprising."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    {
        "name": "restart_python_kernel",
        "description": "Restart the persistent Python kernel, clearing all its variables/imports. Use when state has gotten into a bad way or a genuinely fresh start is wanted.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_lock = threading.Lock()
_km = None
_kc = None


def _ensure_kernel():
    global _km, _kc
    if _kc is not None:
        return
    from jupyter_client import KernelManager

    _km = KernelManager()
    _km.start_kernel()
    _kc = _km.client()
    _kc.start_channels()
    _kc.wait_for_ready(timeout=60)


def restart_python_kernel() -> Dict[str, Any]:
    global _km, _kc
    with _lock:
        try:
            if _km is not None:
                _km.restart_kernel(now=True)
                _kc = _km.client()
                _kc.start_channels()
                _kc.wait_for_ready(timeout=60)
            else:
                _ensure_kernel()
            return {"success": True}
        except Exception as e:
            logger.warning("restart_python_kernel: failed: %s", e)
            return {"success": False, "error": str(e)}


def run_python_kernel(code: str) -> Dict[str, Any]:
    try:
        with _lock:
            _ensure_kernel()
            msg_id = _kc.execute(code)

            stdout_parts: List[str] = []
            stderr_parts: List[str] = []
            result_text: Optional[str] = None
            image_base64: Optional[str] = None
            error: Optional[str] = None

            while True:
                try:
                    msg = _kc.get_iopub_msg(timeout=60)
                except Exception:
                    break
                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                msg_type = msg.get("msg_type")
                content = msg.get("content", {})

                if msg_type == "stream":
                    (stdout_parts if content.get("name") == "stdout" else stderr_parts).append(content.get("text", ""))
                elif msg_type in ("execute_result", "display_data"):
                    data = content.get("data", {})
                    if "image/png" in data:
                        image_base64 = data["image/png"]
                    elif "text/plain" in data:
                        result_text = data["text/plain"]
                elif msg_type == "error":
                    error = "\n".join(content.get("traceback", []) or [content.get("evalue", "")])
                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break

        if error:
            return {"success": False, "error": error, "stdout": "".join(stdout_parts)}

        result: Dict[str, Any] = {
            "success": True,
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "result": result_text,
        }
        if image_base64:
            result["_image_base64"] = image_base64
        return result
    except Exception as e:
        logger.warning("run_python_kernel: failed: %s", e)
        return {"success": False, "error": str(e)}
