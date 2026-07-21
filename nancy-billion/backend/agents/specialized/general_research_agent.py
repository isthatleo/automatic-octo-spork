"""
General Research Agent for Nancy/Billion Backend
Broad, open-domain fact-finding: research briefs, topic comparisons, and
related-topic discovery grounded in real Wikipedia sources.

Distinct from:
  - ResearchAgent (research_agent.py): academic methodology, citation
    parsing, hypothesis generation -- built for scholarly literature.
  - GeneralPurposeAgent (llm_utility_agents.py): pure LLM chain with no
    external grounding at all.
This agent sits between the two: any everyday topic (not just academic
ones), but every factual claim traces back to a real fetched source rather
than the model's own recollection. Never fabricates a source or "finding"
when a real fetch comes back empty.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple
from collections import Counter

from .base_specialized_agent import SpecializedAgent
from ..real_compute import tfidf_scores, cosine_similarity

logger = logging.getLogger(__name__)

_STOPWORDS = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
              "by", "from", "as", "is", "was", "are", "were", "be", "been", "being", "have",
              "has", "had", "do", "does", "did", "will", "would", "could", "should", "this",
              "that", "these", "those", "it", "its", "they", "them", "their", "we", "our",
              "you", "your", "he", "she", "his", "her", "not", "no", "so", "if", "then"}


class GeneralResearchAgent(SpecializedAgent):
    """Broad open-domain research agent -- fact-finding briefs grounded in real sources"""

    def __init__(self, settings):
        super().__init__(settings, "General Research Agent", "general-research")
        self.capabilities.update({
            "description": (
                "Open-domain fact-finding agent: research briefs, topic comparisons, and related-topic "
                "discovery, grounded in real fetched sources rather than the model's own recollection. "
                "Not limited to academic subjects -- covers any everyday topic."
            ),
            "confidence": 0.82,
            "specializations": [
                "research-briefs",
                "topic-comparison",
                "related-topic-discovery",
                "source-grounded-summaries",
            ],
            "tools": ["wikipedia-search-api", "wikipedia-summary-api"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "brief")
        try:
            if task_type == "brief":
                return await self._research_brief(task_data)
            elif task_type == "compare":
                return await self._compare_topics(task_data)
            elif task_type == "related-topics":
                return await self._related_topics(task_data)
            else:
                return await self._general_query(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Real source fetching (Wikipedia public API -- no key required)
    # ------------------------------------------------------------------

    async def _search_titles(self, client, topic: str, limit: int) -> List[str]:
        resp = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": topic, "format": "json", "srlimit": limit},
            headers={"User-Agent": "Nancy-Billion-GeneralResearchAgent/1.0"},
        )
        resp.raise_for_status()
        return [h.get("title", "") for h in resp.json().get("query", {}).get("search", []) if h.get("title")]

    async def _fetch_summary(self, client, title: str) -> Dict[str, Any]:
        resp = await client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}",
            headers={"User-Agent": "Nancy-Billion-GeneralResearchAgent/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "title": data.get("title", title),
            "extract": data.get("extract", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }

    async def _fetch_topic(self, topic: str, limit: int = 3) -> List[Dict[str, Any]]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                titles = await self._search_titles(client, topic, limit)
                results = []
                for title in titles:
                    try:
                        summary = await self._fetch_summary(client, title)
                        if summary["extract"]:
                            results.append(summary)
                    except Exception as e:
                        logger.warning("General research agent: summary fetch failed for '%s': %s", title, e)
                return results
        except Exception as e:
            logger.warning("General research agent: fetch failed for topic '%s': %s", topic, e)
            return []

    async def _related_page_titles(self, topic: str, limit: int = 5) -> List[str]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query", "prop": "links", "titles": topic,
                        "format": "json", "pllimit": limit, "plnamespace": 0,
                    },
                    headers={"User-Agent": "Nancy-Billion-GeneralResearchAgent/1.0"},
                )
                resp.raise_for_status()
                pages = resp.json().get("query", {}).get("pages", {})
                titles: List[str] = []
                for page in pages.values():
                    for link in page.get("links", []):
                        t = link.get("title")
                        if t:
                            titles.append(t)
                return titles[:limit]
        except Exception as e:
            logger.warning("General research agent: related-links fetch failed for '%s': %s", topic, e)
            return []

    # ------------------------------------------------------------------
    # Text utilities
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z]{2,}", text.lower())
        return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    def _keywords(self, text: str, n: int = 8) -> List[str]:
        tokens = self._tokenize(text)
        if not tokens:
            return []
        counts = Counter(tokens)
        return [w for w, _ in counts.most_common(n)]

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _research_brief(self, params: Dict[str, Any]) -> Dict[str, Any]:
        topic = str(params.get("topic", "")).strip()
        if not topic:
            return {"success": False, "task_type": "brief", "error": "'topic' is required"}

        sources = await self._fetch_topic(topic, limit=int(params.get("limit", 3)))
        if not sources:
            return {
                "success": False, "task_type": "brief", "topic": topic,
                "error": "No real sources could be fetched for this topic -- not returning a fabricated brief.",
            }

        combined = " ".join(s["extract"] for s in sources)
        related = await self._related_page_titles(sources[0]["title"], limit=6)

        return {
            "success": True,
            "task_type": "brief",
            "topic": topic,
            "overview": sources[0]["extract"],
            "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
            "key_terms": self._keywords(combined, 10),
            "related_topics": related,
            "open_questions": [
                f"How has understanding of {topic} changed in the most recent sources you can find?",
                f"What do sources disagree on regarding {topic}?",
                f"What's the strongest counter-argument or limitation to what's fetched here about {topic}?",
            ],
        }

    async def _compare_topics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        topic_a = str(params.get("topic_a", "")).strip()
        topic_b = str(params.get("topic_b", "")).strip()
        if not topic_a or not topic_b:
            return {"success": False, "task_type": "compare", "error": "'topic_a' and 'topic_b' are both required"}

        sources_a = await self._fetch_topic(topic_a, limit=1)
        sources_b = await self._fetch_topic(topic_b, limit=1)
        if not sources_a or not sources_b:
            missing = topic_a if not sources_a else topic_b
            return {
                "success": False, "task_type": "compare",
                "error": f"No real source could be fetched for '{missing}' -- not returning a fabricated comparison.",
            }

        text_a, text_b = sources_a[0]["extract"], sources_b[0]["extract"]
        tokens_a, tokens_b = self._tokenize(text_a), self._tokenize(text_b)
        tfidf = tfidf_scores([tokens_a, tokens_b])

        vocab = sorted(set(tokens_a) | set(tokens_b))
        vec_a = [tfidf.get(w, 0.0) if w in tokens_a else 0.0 for w in vocab]
        vec_b = [tfidf.get(w, 0.0) if w in tokens_b else 0.0 for w in vocab]
        similarity = cosine_similarity(vec_a, vec_b) if vocab else 0.0

        shared_terms = sorted(set(self._keywords(text_a, 15)) & set(self._keywords(text_b, 15)))

        return {
            "success": True,
            "task_type": "compare",
            "topic_a": {"name": topic_a, "title": sources_a[0]["title"], "overview": text_a, "url": sources_a[0]["url"]},
            "topic_b": {"name": topic_b, "title": sources_b[0]["title"], "overview": text_b, "url": sources_b[0]["url"]},
            "similarity_score": similarity,
            "shared_key_terms": shared_terms,
            "distinct_terms_a": [w for w in self._keywords(text_a, 10) if w not in shared_terms],
            "distinct_terms_b": [w for w in self._keywords(text_b, 10) if w not in shared_terms],
        }

    async def _related_topics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        topic = str(params.get("topic", "")).strip()
        if not topic:
            return {"success": False, "task_type": "related-topics", "error": "'topic' is required"}

        limit = int(params.get("limit", 10))
        related = await self._related_page_titles(topic, limit=limit)
        if not related:
            return {
                "success": False, "task_type": "related-topics", "topic": topic,
                "error": "No related pages found -- topic may not exist or the fetch failed.",
            }
        return {"success": True, "task_type": "related-topics", "topic": topic, "related_topics": related}

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        if not str(query).strip():
            return {"success": False, "task_type": "query", "error": "'query' is required"}

        sources = await self._fetch_topic(str(query), limit=2)
        answer = await self._llm_answer(str(query))

        result: Dict[str, Any] = {
            "success": True,
            "task_type": "query",
            "query": query,
            "sources": [{"title": s["title"], "url": s["url"], "extract": s["extract"]} for s in sources],
        }
        if answer:
            result["response"] = answer
        elif not sources:
            result["response"] = (
                "No real sources could be fetched and the LLM fallback is unavailable -- "
                "try a more specific topic or use the 'brief' task type."
            )
        return result
