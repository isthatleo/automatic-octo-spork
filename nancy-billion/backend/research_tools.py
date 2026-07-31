"""Real research tools with no API key required -- arXiv's and Polymarket's
public APIs are both open, unauthenticated, and free. Ported in spirit from
the Hermes/OpenClaw skill list's "arXiv search" and "Polymarket data" items
(2026-07-31 Hermes-parity audit), which Nancy/Billion had no equivalent of:
watch_store.py covers generic page/topic watching, but nothing spoke either
of these two APIs specifically.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

RESEARCH_TOOLS = [
    {
        "name": "search_arxiv",
        "description": (
            "Search arXiv (arxiv.org) for real academic papers -- physics, math, CS, and related "
            "fields. Returns title, authors, abstract, and a real link for each real match. Free, "
            "no API key, no approval needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms, e.g. 'quantum error correction'."},
                "max_results": {"type": "integer", "description": "Default 5, max 20."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_prediction_markets",
        "description": (
            "Look up real, currently-active prediction markets on Polymarket matching a topic -- "
            "current odds (implied probability), volume, and end date for each real market found. "
            "Free, no API key, no approval needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Topic to search for, e.g. 'election', 'fed rate'."},
                "max_results": {"type": "integer", "description": "Default 5, max 20."},
            },
            "required": ["query"],
        },
    },
]

_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


async def search_arxiv(query: str, max_results: int = 5) -> Dict[str, Any]:
    max_results = max(1, min(int(max_results or 5), 20))
    try:
        # arXiv's public API is genuinely slow -- confirmed live, a real
        # response took ~27s. A short timeout here just produces false
        # "search failed" errors on a query that would have succeeded.
        async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://export.arxiv.org/api/query",
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                },
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
    except Exception as e:
        logger.warning("search_arxiv: request failed: %s", e)
        return {"success": False, "error": str(e)}

    papers: List[Dict[str, Any]] = []
    for entry in root.findall("atom:entry", _ARXIV_NS):
        title = (entry.findtext("atom:title", default="", namespaces=_ARXIV_NS) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=_ARXIV_NS) or "").strip()
        link = ""
        for link_el in entry.findall("atom:link", _ARXIV_NS):
            if link_el.get("rel") == "alternate" or link is None:
                link = link_el.get("href", "")
                break
        authors = [
            (a.findtext("atom:name", default="", namespaces=_ARXIV_NS) or "").strip()
            for a in entry.findall("atom:author", _ARXIV_NS)
        ]
        published = (entry.findtext("atom:published", default="", namespaces=_ARXIV_NS) or "").strip()
        papers.append({
            "title": " ".join(title.split()),
            "authors": authors,
            "summary": " ".join(summary.split())[:600],
            "url": link,
            "published": published,
        })

    return {"success": True, "query": query, "papers": papers}


async def get_prediction_markets(query: str, max_results: int = 5) -> Dict[str, Any]:
    max_results = max(1, min(int(max_results or 5), 20))
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false", "limit": max_results, "search": query},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("get_prediction_markets: request failed: %s", e)
        return {"success": False, "error": str(e)}

    if isinstance(data, dict):
        data = data.get("markets") or data.get("data") or []

    markets: List[Dict[str, Any]] = []
    for m in (data or [])[:max_results]:
        outcomes = m.get("outcomes")
        prices = m.get("outcomePrices")
        # Polymarket's Gamma API returns these as JSON-encoded strings, not
        # real lists, in some responses -- tolerate both shapes.
        if isinstance(outcomes, str):
            try:
                import json as _json
                outcomes = _json.loads(outcomes)
            except Exception:
                outcomes = None
        if isinstance(prices, str):
            try:
                import json as _json
                prices = _json.loads(prices)
            except Exception:
                prices = None
        odds = None
        if outcomes and prices and len(outcomes) == len(prices):
            odds = {o: p for o, p in zip(outcomes, prices)}
        markets.append({
            "question": m.get("question") or m.get("title"),
            "odds": odds,
            "volume": m.get("volume") or m.get("volumeNum"),
            "end_date": m.get("endDate"),
            "url": f"https://polymarket.com/event/{m.get('slug')}" if m.get("slug") else None,
        })

    return {"success": True, "query": query, "markets": markets}
