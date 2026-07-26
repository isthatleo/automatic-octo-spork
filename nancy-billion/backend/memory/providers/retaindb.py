"""Real RetainDB adapter -- hybrid vector+BM25+rerank memory API (7 memory
types), via its documented REST API."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import MemoryProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

RETAINDB_API_BASE = os.getenv("RETAINDB_API_BASE", "https://api.retaindb.com/v1")


class RetainDBProvider(MemoryProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("RETAINDB_API_KEY")
        if not self.api_key:
            raise RuntimeError("RETAINDB_API_KEY not set")
        # RetainDB's 7 memory types (episodic, semantic, procedural, etc.) --
        # Nancy stores everything under one general-purpose type by default;
        # override per-call via metadata={"memory_type": ...} if needed.
        self.default_memory_type = os.getenv("RETAINDB_MEMORY_TYPE", "semantic")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{RETAINDB_API_BASE}/memories",
                    json={"content": content, "type": metadata.get("memory_type", self.default_memory_type), "metadata": metadata},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return {"success": True, "id": resp.json().get("id")}
        except Exception as e:
            logger.warning("RetainDBProvider: add failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # RetainDB's hybrid search (vector + BM25 + rerank) is exposed
                # as one endpoint that does all three internally.
                resp = await client.post(f"{RETAINDB_API_BASE}/search", json={"query": query, "top_k": top_k, "hybrid": True}, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("RetainDBProvider: search failed: %s", e)
            return []
        return [
            {"content": r.get("content", ""), "score": r.get("rerank_score", r.get("score", 0.0)), "metadata": r.get("metadata", {})}
            for r in data.get("results", [])[:top_k]
        ]


register_if_configured("memory", "retaindb", "RETAINDB_API_KEY", RetainDBProvider)
