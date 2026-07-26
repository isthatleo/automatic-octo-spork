"""Real Mem0 hosted-memory adapter -- the reference implementation for this
batch of 7 external memory providers (ported from Hermes' plugins/memory/*).
Uses Mem0's real documented REST API directly (https://api.mem0.ai) rather
than the mem0ai SDK, matching this codebase's existing convention of plain
httpx calls for every other vendor integration instead of per-vendor SDKs.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import MemoryProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

MEM0_API_BASE = "https://api.mem0.ai/v1"


class Mem0Provider(MemoryProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("MEM0_API_KEY")
        if not self.api_key:
            raise RuntimeError("MEM0_API_KEY not set")
        self.user_id = os.getenv("MEM0_USER_ID", "nancy-default")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Token {self.api_key}", "Content-Type": "application/json"}

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{MEM0_API_BASE}/memories/",
                    json={"messages": [{"role": "user", "content": content}], "user_id": self.user_id, "metadata": metadata or {}},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "id": data[0].get("id") if isinstance(data, list) and data else None}
        except Exception as e:
            logger.warning("Mem0Provider: add failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{MEM0_API_BASE}/memories/search/",
                    json={"query": query, "user_id": self.user_id, "limit": top_k},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("Mem0Provider: search failed: %s", e)
            return []

        return [
            {"content": item.get("memory", ""), "score": item.get("score", 0.0), "metadata": item.get("metadata", {})}
            for item in (data if isinstance(data, list) else data.get("results", []))
        ]


register_if_configured("memory", "mem0", "MEM0_API_KEY", Mem0Provider)
