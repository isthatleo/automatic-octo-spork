"""Real Crabbox cloud-sandbox adapter -- ported from OpenClaw's Crabbox
extension. An optional remote execution backend for terminal_tool.py's
execute_command when the user wants isolation beyond the local
safe-command-allowlist-or-approval gate -- the command runs on Crabbox's
own remote worker instead of this machine, via its real REST API.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

from providers.base import SandboxProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

CRABBOX_API_BASE_DEFAULT = "https://api.crabbox.dev/v1"


class CrabboxSandboxProvider(SandboxProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("CRABBOX_API_KEY")
        if not self.api_key:
            raise RuntimeError("CRABBOX_API_KEY not set")
        self.endpoint = os.getenv("CRABBOX_ENDPOINT", CRABBOX_API_BASE_DEFAULT)

    async def execute(self, command: str, **kw: Any) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=kw.get("timeout", 60.0)) as client:
                resp = await client.post(
                    f"{self.endpoint}/exec",
                    json={"command": command, "cwd": kw.get("cwd")},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": data.get("exit_code", 1) == 0,
                    "stdout": data.get("stdout", ""),
                    "stderr": data.get("stderr", ""),
                    "exit_code": data.get("exit_code"),
                }
        except Exception as e:
            logger.warning("CrabboxSandboxProvider: execute failed: %s", e)
            return {"success": False, "error": str(e)}


register_if_configured("sandbox", "crabbox", "CRABBOX_API_KEY", CrabboxSandboxProvider)
