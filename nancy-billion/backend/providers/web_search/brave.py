"""Real Brave Search API adapter -- the reference/proof-of-concept vendor for
the providers/ registry pattern (see providers/registry.py). Every later
vendor across every capability (image/video/TTS/transcription/etc.) follows
this exact shape: implement the ABC, self-register at import time only if the
vendor's env var is present.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

from providers.base import WebSearchProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider(WebSearchProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("BRAVE_API_KEY")
        if not self.api_key:
            raise RuntimeError("BRAVE_API_KEY not set")

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    BRAVE_SEARCH_URL,
                    params={"q": query, "count": min(max_results, 20)},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("BraveSearchProvider: search failed: %s", e)
            return []

        results = []
        for item in (data.get("web", {}).get("results") or [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })
        return results


register_if_configured("web_search", "brave", "BRAVE_API_KEY", BraveSearchProvider)
