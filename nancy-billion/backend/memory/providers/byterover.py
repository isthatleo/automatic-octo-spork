"""Real ByteRover adapter -- hierarchical knowledge-tree memory. ByteRover's
primary interface is the `brv` CLI (per Hermes' own integration); this
adapter uses ByteRover's REST API directly instead of shelling out to a CLI,
matching this codebase's httpx-everywhere convention for vendor calls."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import MemoryProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

BYTEROVER_API_BASE = os.getenv("BYTEROVER_API_BASE", "https://api.byterover.dev/v1")


class ByteRoverProvider(MemoryProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("BYTEROVER_API_KEY")
        if not self.api_key:
            raise RuntimeError("BYTEROVER_API_KEY not set")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{BYTEROVER_API_BASE}/knowledge", json={"content": content, "metadata": metadata or {}}, headers=self._headers())
                resp.raise_for_status()
                return {"success": True, "id": resp.json().get("id")}
        except Exception as e:
            logger.warning("ByteRoverProvider: add failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{BYTEROVER_API_BASE}/knowledge/search", params={"q": query, "limit": top_k}, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("ByteRoverProvider: search failed: %s", e)
            return []
        return [
            {"content": r.get("content", ""), "score": r.get("score", 0.0), "metadata": r.get("metadata", {})}
            for r in data.get("items", [])[:top_k]
        ]


register_if_configured("memory", "byterover", "BYTEROVER_API_KEY", ByteRoverProvider)
