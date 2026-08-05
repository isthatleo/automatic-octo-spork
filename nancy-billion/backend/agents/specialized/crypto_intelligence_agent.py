"""
Crypto Intelligence Agent for Nancy/Billion.

Real market data ONLY -- reuses trading/crypto_data.py's real, keyless
CoinGecko wrapper (the same one CryptoTradingAgent's technical-analysis
path uses). Distinct from CryptoTradingAgent (which does on-demand
technical analysis/backtesting): this agent is oriented around proactive
opportunity-scanning -- a real multi-coin snapshot ranked by real 24h
momentum, and a real web-search-backed narrative scan -- so the proactive
task orchestrator has something genuinely useful to run periodically.

Explicitly does NOT do anything mining-related (see mining_profitability_agent.py
for the honest reason why) and never executes a real trade -- this is
market intelligence, not an autonomous trading bot.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

_DEFAULT_WATCHLIST = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA"]


class CryptoIntelligenceAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Crypto Intelligence Agent", "crypto-intelligence")
        self.capabilities.update({
            "description": "Real multi-coin market snapshots ranked by real 24h momentum, plus real web-search narrative scanning -- never a trade, never fabricated",
            "confidence": 0.8,
            "specializations": ["market-snapshot", "momentum-ranking", "narrative-scan"],
            "tools": ["coingecko", "web_search"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "market_snapshot":
            return await self._market_snapshot(task_data.get("symbols") or _DEFAULT_WATCHLIST)
        if task_type == "top_movers":
            return await self._top_movers(task_data.get("symbols") or _DEFAULT_WATCHLIST)
        if task_type == "narrative_scan":
            return await self._narrative_scan(task_data.get("query", "crypto market news today"))
        if task_type == "status":
            return {"success": True, "status": "ready", "default_watchlist": _DEFAULT_WATCHLIST}
        return await self._general(task_data)

    async def _snapshots(self, symbols: List[str]) -> List[Dict[str, Any]]:
        from trading.crypto_data import crypto_data
        from trading.tradingview_symbols import crypto_tradingview_symbol
        out = []
        for sym in symbols:
            snap = await crypto_data.get_price(sym)
            if snap is not None:
                out.append({
                    "symbol": snap.symbol, "price_usd": snap.price_usd,
                    "change_24h_pct": snap.change_24h_pct, "volume_24h_usd": snap.volume_24h_usd,
                    "market_cap_usd": snap.market_cap_usd,
                    "tradingview_symbol": crypto_tradingview_symbol(snap.symbol),
                })
        return out

    async def _market_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        snaps = await self._snapshots(symbols)
        if not snaps:
            return {"success": False, "error": "Could not fetch real prices for any requested symbol"}
        return {"success": True, "snapshots": snaps}

    async def _top_movers(self, symbols: List[str]) -> Dict[str, Any]:
        snaps = await self._snapshots(symbols)
        if not snaps:
            return {"success": False, "error": "Could not fetch real prices for any requested symbol"}
        ranked = sorted(snaps, key=lambda s: s["change_24h_pct"], reverse=True)
        return {
            "success": True,
            "biggest_gainer": ranked[0],
            "biggest_loser": ranked[-1],
            "all_ranked": ranked,
        }

    async def _narrative_scan(self, query: str) -> Dict[str, Any]:
        from providers.registry import get_ordered_providers
        providers = get_ordered_providers("web_search")
        if not providers:
            return {"success": False, "error": "No web search provider is configured (e.g. BRAVE_API_KEY)."}
        try:
            results = await providers[0].search(query, max_results=6)
        except Exception as e:
            return {"success": False, "error": f"Web search failed: {e}"}
        return {"success": True, "query": query, "results": results}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I give you real crypto market snapshots ranked by real momentum, and real web-search news "
            "scans -- never a trade, never a fabricated number."
        )}
