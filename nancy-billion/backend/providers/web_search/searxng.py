"""Real SearXNG adapter -- a self-hosted metasearch instance, no API key/
account needed at all, just a base URL. Third web_search vendor."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

from providers.base import WebSearchProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)


class SearXNGProvider(WebSearchProvider):
    def __init__(self) -> None:
        self.base_url = os.getenv("SEARXNG_BASE_URL", "").rstrip("/")
        if not self.base_url:
            raise RuntimeError("SEARXNG_BASE_URL not set")

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.base_url}/search", params={"q": query, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("SearXNGProvider: search failed: %s", e)
            return []

        return [
            {"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("content", "")}
            for item in (data.get("results") or [])[:max_results]
        ]


register_if_configured("web_search", "searxng", "SEARXNG_BASE_URL", SearXNGProvider)
