"""Real SuperMemory adapter -- semantic recall + full-session ingest, via
SuperMemory's documented REST API (https://api.supermemory.ai)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import MemoryProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

SUPERMEMORY_API_BASE = os.getenv("SUPERMEMORY_API_BASE", "https://api.supermemory.ai/v3")


class SuperMemoryProvider(MemoryProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("SUPERMEMORY_API_KEY")
        if not self.api_key:
            raise RuntimeError("SUPERMEMORY_API_KEY not set")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{SUPERMEMORY_API_BASE}/memories", json={"content": content, "metadata": metadata or {}}, headers=self._headers(),
                )
                resp.raise_for_status()
                return {"success": True, "id": resp.json().get("id")}
        except Exception as e:
            logger.warning("SuperMemoryProvider: add failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{SUPERMEMORY_API_BASE}/search", json={"q": query, "limit": top_k}, headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("SuperMemoryProvider: search failed: %s", e)
            return []
        return [
            {"content": r.get("content", ""), "score": r.get("similarity", 0.0), "metadata": r.get("metadata", {})}
            for r in data.get("results", [])[:top_k]
        ]


register_if_configured("memory", "supermemory", "SUPERMEMORY_API_KEY", SuperMemoryProvider)
