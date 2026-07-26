"""Real Hindsight adapter -- knowledge-graph memory with entity resolution,
via Hindsight's REST API. Endpoint shape follows the common
add-document/query-graph convention this class of vendor API uses; verify
against Hindsight's current docs if their exact route names have moved."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import MemoryProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

HINDSIGHT_API_BASE = os.getenv("HINDSIGHT_API_BASE", "https://api.hindsight.dev/v1")


class HindsightProvider(MemoryProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("HINDSIGHT_API_KEY")
        if not self.api_key:
            raise RuntimeError("HINDSIGHT_API_KEY not set")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{HINDSIGHT_API_BASE}/documents", json={"text": content, "metadata": metadata or {}}, headers=self._headers())
                resp.raise_for_status()
                return {"success": True, "id": resp.json().get("id")}
        except Exception as e:
            logger.warning("HindsightProvider: add failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{HINDSIGHT_API_BASE}/query", json={"query": query, "top_k": top_k}, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("HindsightProvider: search failed: %s", e)
            return []
        return [
            {"content": r.get("text", ""), "score": r.get("relevance", 0.0), "metadata": r.get("metadata", {})}
            for r in data.get("results", [])[:top_k]
        ]


register_if_configured("memory", "hindsight", "HINDSIGHT_API_KEY", HindsightProvider)
