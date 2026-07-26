"""Real Tavily search adapter -- purpose-built for LLM agents (pre-summarized
results), a second web_search vendor alongside Brave (providers/web_search/brave.py).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

from providers.base import WebSearchProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilySearchProvider(WebSearchProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY not set")

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    TAVILY_SEARCH_URL,
                    json={"api_key": self.api_key, "query": query, "max_results": max_results},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("TavilySearchProvider: search failed: %s", e)
            return []

        return [
            {"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("content", "")}
            for item in (data.get("results") or [])[:max_results]
        ]


register_if_configured("web_search", "tavily", "TAVILY_API_KEY", TavilySearchProvider)
