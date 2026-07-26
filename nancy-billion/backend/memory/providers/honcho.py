"""Real Honcho adapter -- cross-session user modeling ("dialectic reasoning"),
via Honcho's documented REST API (https://api.honcho.dev). Honcho models
memory as messages within a (workspace, peer, session) hierarchy rather than
flat add/search calls; this adapter maps Nancy's flat MemoryProvider
interface onto that shape using one fixed session per Nancy user.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import MemoryProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

HONCHO_API_BASE = os.getenv("HONCHO_API_BASE", "https://api.honcho.dev/v2")


class HonchoProvider(MemoryProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("HONCHO_API_KEY")
        if not self.api_key:
            raise RuntimeError("HONCHO_API_KEY not set")
        self.workspace_id = os.getenv("HONCHO_WORKSPACE_ID", "nancy")
        self.peer_id = os.getenv("HONCHO_PEER_ID", "nancy-user")
        self.session_id = os.getenv("HONCHO_SESSION_ID", "nancy-default-session")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{HONCHO_API_BASE}/workspaces/{self.workspace_id}/sessions/{self.session_id}/messages"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url, json={"peer_id": self.peer_id, "content": content, "metadata": metadata or {}}, headers=self._headers(),
                )
                resp.raise_for_status()
                return {"success": True, "id": resp.json().get("id")}
        except Exception as e:
            logger.warning("HonchoProvider: add failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        url = f"{HONCHO_API_BASE}/workspaces/{self.workspace_id}/peers/{self.peer_id}/search"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json={"query": query, "limit": top_k}, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("HonchoProvider: search failed: %s", e)
            return []
        items = data.get("items", data) if isinstance(data, dict) else data
        return [
            {"content": r.get("content", ""), "score": r.get("score", 0.0), "metadata": r.get("metadata", {})}
            for r in (items or [])[:top_k]
        ]


register_if_configured("memory", "honcho", "HONCHO_API_KEY", HonchoProvider)
