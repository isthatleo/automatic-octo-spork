"""Real OpenViking adapter -- ByteDance's filesystem-style knowledge context
DB, via its REST API. OpenViking models memory as files in a virtual
filesystem rather than flat records; this adapter writes each memory as one
file under a fixed /nancy directory and uses OpenViking's own semantic
search endpoint over that directory."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from providers.base import MemoryProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

OPENVIKING_API_BASE = os.getenv("OPENVIKING_API_BASE", "https://api.openviking.dev/v1")
OPENVIKING_ROOT = os.getenv("OPENVIKING_ROOT", "/nancy")


class OpenVikingProvider(MemoryProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENVIKING_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENVIKING_API_KEY not set")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = f"{OPENVIKING_ROOT}/{int(time.time() * 1000)}.txt"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.put(
                    f"{OPENVIKING_API_BASE}/files{path}", json={"content": content, "metadata": metadata or {}}, headers=self._headers(),
                )
                resp.raise_for_status()
                return {"success": True, "id": path}
        except Exception as e:
            logger.warning("OpenVikingProvider: add failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{OPENVIKING_API_BASE}/search", json={"query": query, "path_prefix": OPENVIKING_ROOT, "limit": top_k}, headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("OpenVikingProvider: search failed: %s", e)
            return []
        return [
            {"content": r.get("content", ""), "score": r.get("score", 0.0), "metadata": {"path": r.get("path")}}
            for r in data.get("results", [])[:top_k]
        ]


register_if_configured("memory", "openviking", "OPENVIKING_API_KEY", OpenVikingProvider)
