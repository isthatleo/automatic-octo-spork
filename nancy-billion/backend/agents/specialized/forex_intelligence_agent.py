"""
Forex Intelligence Agent for Nancy/Billion.

Real market data ONLY -- reuses trading/forex_engine.py's already-wired,
real, keyless ForexDataAggregator (Frankfurter.app/ECB reference rates for
fiat pairs, Yahoo Finance COMEX futures for XAU/XAG) and
TechnicalAnalysisEngine, the exact same objects that already back
/trading/quotes and /trading/analyze -- this agent just makes that existing,
fully-working data source visible to the specialist-agent fleet (fleet
sweep, dispatcher, capability-index auto-consult), which previously had no
way to reach it at all. No new API key, no new HTTP client: same
zero-integration-cost reasoning as crypto_intelligence_agent.py reusing
trading/crypto_data.py.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

_DEFAULT_WATCHLIST = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "XAU/USD"]


class ForexIntelligenceAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Forex Intelligence Agent", "forex-intelligence")
        self.capabilities.update({
            "description": "Real live forex/metals quotes (Frankfurter/ECB, Yahoo COMEX) and real technical analysis -- never a trade, never fabricated",
            "confidence": 0.8,
            "specializations": ["market-snapshot", "technical-analysis"],
            "tools": ["forex_engine"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "market_snapshot":
            return await self._market_snapshot(task_data.get("pairs") or _DEFAULT_WATCHLIST)
        if task_type == "technical_analysis":
            pair = task_data.get("pair")
            if not pair:
                return {"success": False, "error": "technical_analysis requires a 'pair' (e.g. 'EUR/USD')"}
            return await self._technical_analysis(pair)
        if task_type == "status":
            return {"success": True, "status": "ready", "default_watchlist": _DEFAULT_WATCHLIST}
        return await self._general(task_data)

    async def _market_snapshot(self, pairs: List[str]) -> Dict[str, Any]:
        from main_new import forex_aggregator
        quotes = []
        for pair in pairs:
            snap = await forex_aggregator.get_price(pair)
            if snap is not None:
                quotes.append({
                    "pair": snap.pair, "price": snap.price, "bid": snap.bid, "ask": snap.ask,
                    "change_24h": snap.change_24h, "high_24h": snap.high_24h, "low_24h": snap.low_24h,
                })
        if not quotes:
            return {"success": False, "error": "Could not fetch real quotes for any requested pair"}
        return {"success": True, "quotes": quotes}

    async def _technical_analysis(self, pair: str) -> Dict[str, Any]:
        from main_new import forex_aggregator, analysis_engine
        snapshot = await forex_aggregator.get_price(pair)
        if not snapshot:
            return {"success": False, "error": f"Could not get real market data for {pair}"}
        historical = await forex_aggregator.get_historical(pair)
        analysis = analysis_engine.analyze(pair, snapshot, historical)
        return {"success": True, "pair": pair, "analysis": analysis.to_dict()}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I give you real live forex/metals quotes and real technical analysis -- never a trade, "
            "never a fabricated number."
        )}
