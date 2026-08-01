"""
E-commerce Research Agent for Nancy/Billion.

Real trending-product research (via the actual configured web-search
provider -- Brave/Tavily/SearXNG, whichever is set up) and real LLM-drafted
product listings/ad copy, saved as pending drafts (product_drafts_store.py)
and to memory for later recall.

Deliberately does NOT publish anything anywhere: there is no Shopify/Etsy/
WooCommerce API integration in this codebase, and even if there were, going
live with a real product or spending real ad money is exactly the kind of
action this system gates behind a human's Telegram approval tap (see
main_new.py's _request_approval) rather than letting an agent do
autonomously -- the same principle every write/delete tool already follows.
request_publish_approval sends a real approval prompt and marks the draft's
outcome; it does not call any external publishing API, because none is
configured.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_specialized_agent import SpecializedAgent


class EcommerceResearchAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "E-commerce Research Agent", "ecommerce-research")
        self.capabilities.update({
            "description": (
                "Real trending-product research via web search, and LLM-drafted product listings/ad "
                "copy saved as pending drafts -- never auto-published, always a human approval away"
            ),
            "confidence": 0.75,
            "specializations": ["market-research", "product-listing-drafts", "ad-copy-drafts"],
            "tools": ["web_search", "product_drafts_store"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "trending_products":
            return await self._trending_products(task_data.get("category", ""))
        if task_type == "draft_listing":
            return await self._draft_listing(task_data.get("product_idea", ""), task_data.get("research", ""))
        if task_type == "draft_ad_copy":
            return await self._draft_ad_copy(task_data.get("draft_id", ""))
        if task_type == "list_drafts":
            return self._list_drafts(task_data.get("status"))
        if task_type == "request_publish_approval":
            return await self._request_publish_approval(task_data.get("draft_id", ""))
        if task_type == "status":
            return self._list_drafts(None)
        return await self._general(task_data)

    async def _trending_products(self, category: str) -> Dict[str, Any]:
        from providers.registry import get_ordered_providers
        providers = get_ordered_providers("web_search")
        if not providers:
            return {"success": False, "error": "No web search provider is configured (e.g. BRAVE_API_KEY)."}
        query = f"trending products to sell online 2026 {category}".strip()
        try:
            results = await providers[0].search(query, max_results=8)
        except Exception as e:
            return {"success": False, "error": f"Web search failed: {e}"}
        return {"success": True, "query": query, "results": results}

    async def _draft_listing(self, product_idea: str, research: str) -> Dict[str, Any]:
        if not product_idea.strip():
            return {"success": False, "error": "product_idea is required"}
        prompt = (
            f"Draft a real, sellable e-commerce product listing for: {product_idea}\n\n"
            + (f"Relevant research/context:\n{research}\n\n" if research else "")
            + "Respond with ONLY a JSON object (no prose, no markdown fences) in this exact shape:\n"
            '{"title": "...", "description": "2-3 sentence real product description", '
            '"suggested_price_usd": 0.0, "tags": ["...", "..."]}'
        )
        answer = await self._llm_answer(prompt, max_tokens=400)
        if not answer:
            return {"success": False, "error": "LLM unavailable for drafting"}
        import json, re
        match = re.search(r"\{.*\}", answer, re.DOTALL)
        if not match:
            return {"success": False, "error": f"Could not parse a listing draft from the model: {answer[:200]}"}
        try:
            spec = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError) as e:
            return {"success": False, "error": f"Invalid JSON draft: {e}"}

        from product_drafts_store import product_drafts_store
        draft = product_drafts_store.create(
            title=str(spec.get("title", product_idea))[:120],
            description=str(spec.get("description", ""))[:1000],
            suggested_price_usd=spec.get("suggested_price_usd"),
            tags=[str(t) for t in (spec.get("tags") or [])][:10],
            source_research=research[:500],
        )
        self._remember_draft(draft)
        return {"success": True, "draft": draft.to_public_dict()}

    async def _draft_ad_copy(self, draft_id: str) -> Dict[str, Any]:
        from product_drafts_store import product_drafts_store
        draft = product_drafts_store.get(draft_id)
        if draft is None:
            return {"success": False, "error": f"No draft with id '{draft_id}'"}
        prompt = (
            f"Write 3 short, real ad headline+body variants for this product:\n"
            f"Title: {draft.title}\nDescription: {draft.description}\n\n"
            'Respond with ONLY a JSON array of strings, no prose: ["variant 1", "variant 2", "variant 3"]'
        )
        answer = await self._llm_answer(prompt, max_tokens=300)
        if not answer:
            return {"success": False, "error": "LLM unavailable for ad copy drafting"}
        import json, re
        match = re.search(r"\[.*\]", answer, re.DOTALL)
        if not match:
            return {"success": False, "error": f"Could not parse ad copy from the model: {answer[:200]}"}
        try:
            variants = [str(v) for v in json.loads(match.group(0))]
        except (json.JSONDecodeError, ValueError) as e:
            return {"success": False, "error": f"Invalid JSON: {e}"}
        draft.ad_copy = variants
        product_drafts_store._save()
        return {"success": True, "draft_id": draft_id, "ad_copy": variants}

    def _list_drafts(self, status: Optional[str]) -> Dict[str, Any]:
        from product_drafts_store import product_drafts_store
        drafts = product_drafts_store.list(status)
        return {"success": True, "count": len(drafts), "drafts": [d.to_public_dict() for d in drafts[:20]]}

    async def _request_publish_approval(self, draft_id: str) -> Dict[str, Any]:
        """Sends a REAL Telegram approval prompt -- does not call any
        publishing API (none is configured/wired). Marking a draft
        "approved" here means the human has signed off on the CONTENT;
        actually listing it on a real store still needs that store's real
        API credentials wired up as a separate, later step."""
        from product_drafts_store import product_drafts_store
        draft = product_drafts_store.get(draft_id)
        if draft is None:
            return {"success": False, "error": f"No draft with id '{draft_id}'"}

        from main_new import _request_approval
        description = (
            f"📦 Publish approval requested for a drafted product:\n\n"
            f"Title: {draft.title}\nPrice: ${draft.suggested_price_usd}\n"
            f"Description: {draft.description}\n\n"
            f"Note: no real store (Shopify/Etsy/etc.) is connected yet -- approving this signs off on the "
            f"content, it does not publish it anywhere by itself."
        )
        approved = await _request_approval(description, timeout=600.0)
        product_drafts_store.set_status(draft_id, "approved" if approved else "rejected")
        return {"success": True, "draft_id": draft_id, "approved": approved}

    def _remember_draft(self, draft) -> None:
        try:
            from memory import MemoryType
            from main_new import memory_manager
            memory_manager.graph.add_or_merge_memory(
                f"Drafted product listing: {draft.title} -- {draft.description[:150]}",
                MemoryType.FACT,
                {"source": "ecommerce_research", "draft_id": draft.id},
                importance=0.5,
            )
        except Exception:
            pass  # memory write is a bonus, never worth failing the draft over

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I research real trending products via web search and draft product listings/ad copy for your "
            "approval -- I never publish or spend anything on my own."
        )}
