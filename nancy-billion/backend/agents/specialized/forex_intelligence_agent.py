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

intelligence_report is the NÅNCY Trading Intelligence Division report type
(see trading_intelligence_prompt.py) -- a full institutional-style written
analysis grounded ONLY in the real quote/technical/macro data this agent
actually fetched, never SMC/liquidity specifics the underlying data source
can't support.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

_DEFAULT_WATCHLIST = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "XAU/USD"]

# Real ISO 4217 currency codes plus the two metals this agent actually
# serves (see forex_engine.py's Yahoo COMEX routing) -- deliberately a
# curated allowlist, not "any two 3-letter words", so a free-text question
# like "can you report on this" doesn't get misread as a pair (e.g. "REP"
# isn't a real code, but a naive 3-letter-token regex would still match it).
_KNOWN_CODES = (
    "USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "CNY", "XAU", "XAG",
    "NOK", "SEK", "MXN", "ZAR", "SGD", "HKD", "TRY", "INR", "BRL", "PLN",
)
_PAIR_RE = re.compile(rf"\b({'|'.join(_KNOWN_CODES)})\s*[/\-]?\s*({'|'.join(_KNOWN_CODES)})\b", re.IGNORECASE)
_METAL_ALIASES = {"gold": "XAU/USD", "silver": "XAG/USD"}
_REPORT_TRIGGERS = (
    "report", "intelligence report", "full analysis", "institutional",
    "market intelligence", "trade plan", "outlook", "deep dive",
)


def _extract_pair(text: str) -> Optional[str]:
    """Best-effort real pair extraction from free text -- e.g. "give me a
    full report on EUR/USD" or "what's your outlook on gold". Returns None
    (never a guess) if nothing recognizable is found."""
    lowered = text.lower()
    for name, pair in _METAL_ALIASES.items():
        if name in lowered:
            return pair
    match = _PAIR_RE.search(text)
    if not match:
        return None
    base, quote = match.group(1).upper(), match.group(2).upper()
    return None if base == quote else f"{base}/{quote}"


def _extract_timeframe(text: str) -> str:
    """"technical analysis on gold for the week" -> 'week'. Defaults to
    'day' (not a guess -- day is this agent's real default resolution)."""
    lowered = text.lower()
    if "month" in lowered:
        return "month"
    if "week" in lowered:
        return "week"
    return "day"


class ForexIntelligenceAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Forex Intelligence Agent", "forex-intelligence")
        self.capabilities.update({
            "description": (
                "Real live forex/metals quotes (Frankfurter/ECB, Yahoo COMEX), real technical analysis "
                "(Wilder RSI/MACD/ATR, real swing support-resistance), and full institutional-style "
                "intelligence reports grounded in that real data plus real NFP/CPI/FOMC macro events -- "
                "never a trade, never fabricated"
            ),
            "confidence": 0.8,
            "specializations": ["market-snapshot", "technical-analysis", "intelligence-report"],
            "tools": ["forex_engine", "economic_calendar"],
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
        if task_type == "intelligence_report":
            pair = task_data.get("pair")
            if not pair:
                return {"success": False, "error": "intelligence_report requires a 'pair' (e.g. 'EUR/USD', 'XAU/USD')"}
            timeframe = task_data.get("timeframe", "day")
            if timeframe not in ("day", "week", "month"):
                return {"success": False, "error": f"timeframe must be 'day', 'week', or 'month' (got {timeframe!r})"}
            return await self._intelligence_report(pair, timeframe)
        if task_type == "status":
            return {"success": True, "status": "ready", "default_watchlist": _DEFAULT_WATCHLIST}
        return await self._general(task_data)

    async def _market_snapshot(self, pairs: List[str]) -> Dict[str, Any]:
        from main_new import forex_aggregator
        from trading.tradingview_symbols import forex_tradingview_symbol
        quotes = []
        for pair in pairs:
            snap = await forex_aggregator.get_price(pair)
            if snap is not None:
                quotes.append({
                    "pair": snap.pair, "price": snap.price, "bid": snap.bid, "ask": snap.ask,
                    "change_24h": snap.change_24h, "high_24h": snap.high_24h, "low_24h": snap.low_24h,
                    "tradingview_symbol": forex_tradingview_symbol(snap.pair),
                })
        if not quotes:
            return {"success": False, "error": "Could not fetch real quotes for any requested pair"}
        return {"success": True, "quotes": quotes}

    async def _technical_analysis(self, pair: str) -> Dict[str, Any]:
        from main_new import forex_aggregator, analysis_engine
        from trading.tradingview_symbols import forex_tradingview_symbol
        snapshot = await forex_aggregator.get_price(pair)
        if not snapshot:
            return {"success": False, "error": f"Could not get real market data for {pair}"}
        # 90 calendar days, not the default 30 -- Frankfurter only returns
        # business days (~21/30 calendar days), and MACD/RSI both need more
        # than that to compute for real rather than falling back to a
        # neutral placeholder (see TechnicalAnalysisEngine's guards).
        historical = await forex_aggregator.get_historical(pair, days=90)
        analysis = analysis_engine.analyze(pair, snapshot, historical)
        return {
            "success": True, "pair": pair, "analysis": analysis.to_dict(),
            "tradingview_symbol": forex_tradingview_symbol(pair),
        }

    async def _real_macro_context(self) -> tuple:
        """Real NFP/CPI/FOMC events (economic_calendar.py, FRED-backed) --
        returns (events_or_None, honest_note_or_None). Never invents a
        consensus/expected figure; FRED has none, and neither does this."""
        try:
            import economic_calendar
        except Exception:
            return None, "Economic calendar module unavailable -- no macro data included in this report."
        if not economic_calendar.FRED_API_KEY:
            return None, "FRED_API_KEY is not configured -- no real economic-calendar data available for this report."
        events = economic_calendar.get_cached_events()
        if not events:
            return None, "Economic calendar is configured but has no cached events yet (still polling)."
        return events, None

    # Real calendar-day fetch window per requested timeframe -- enough real
    # history to build a genuinely useful series of resampled bars (see
    # trading/pattern_detection.py's resample_candles), not just enough for
    # one indicator warm-up. ~2 years for weekly (~104 weekly bars), ~5
    # years for monthly (~60 monthly bars); whatever the real source
    # actually returns short of that is used honestly, never padded.
    _FETCH_DAYS = {"day": 120, "week": 730, "month": 1825}

    async def _intelligence_report(self, pair: str, timeframe: str = "day") -> Dict[str, Any]:
        """The NÅNCY Trading Intelligence Division report -- see
        trading_intelligence_prompt.py for the full honesty contract this
        is built on. Always returns the real underlying data alongside the
        narrative, so every claim in the report is independently checkable
        against the actual numbers that grounded it."""
        from main_new import forex_aggregator, analysis_engine
        from llm import llm_backend
        from trading.tradingview_symbols import forex_tradingview_symbol
        from trading.pattern_detection import resample_candles, detect_candlestick_patterns, detect_fair_value_gaps, key_zones
        from .trading_intelligence_prompt import TRADING_INTELLIGENCE_SYSTEM_PROMPT, build_data_grounding_block
        from trust import annotate_uncertainty, fabrication_reason

        tv_symbol = forex_tradingview_symbol(pair)
        snapshot = await forex_aggregator.get_price(pair)
        if not snapshot:
            return {"success": False, "task_type": "intelligence_report", "error": f"Could not get real market data for {pair}", "tradingview_symbol": tv_symbol}
        historical = await forex_aggregator.get_historical(pair, days=self._FETCH_DAYS[timeframe])
        resampled = resample_candles(historical, timeframe)
        analysis = analysis_engine.analyze(pair, snapshot, resampled)

        closes = [c["close"] for c in resampled]
        highs = [c["high"] for c in resampled]
        lows = [c["low"] for c in resampled]

        real_data = {
            "pair": pair, "timeframe": timeframe,
            "price": snapshot.price, "bid": snapshot.bid, "ask": snapshot.ask,
            "change_24h_pct": snapshot.change_24h, "high_24h": snapshot.high_24h, "low_24h": snapshot.low_24h,
            "historical_bars_available": len(historical), "resampled_bars_available": len(resampled),
            "technical_analysis": analysis.to_dict(),
            "candlestick_patterns": detect_candlestick_patterns(resampled),
            "fair_value_gaps": detect_fair_value_gaps(resampled),
            "key_zones": key_zones(highs, lows, closes) if len(closes) >= 5 else [],
            "note": (
                "Metals (XAU/XAG) are real Yahoo Finance COMEX daily OHLC; fiat pairs are real "
                "Frankfurter/ECB daily reference rates (open synthesized as prior close -- no intraday "
                "data from this free source). Not sub-second broker ticks."
            ),
        }
        macro_events, macro_note = await self._real_macro_context()

        grounding = build_data_grounding_block(pair, "forex/metals", real_data, macro_events, macro_note, timeframe=timeframe)
        prompt = (
            f"{TRADING_INTELLIGENCE_SYSTEM_PROMPT}\n\n{grounding}\n\n"
            f"Write the full institutional intelligence report for {pair} now, on the {timeframe} timeframe."
        )

        try:
            # Bumped from 2400 -- the template grew (candlestick patterns,
            # FVGs, key zones, and now both a long AND a short scenario)
            # and was clipping mid-section at the old ceiling.
            report = await llm_backend.generate(prompt, max_tokens=3400, temperature=0.4)
        except Exception as e:
            logger.warning("ForexIntelligenceAgent: report generation failed for %s: %s", pair, e)
            return {"success": False, "task_type": "intelligence_report", "pair": pair, "error": str(e), "data": real_data, "tradingview_symbol": tv_symbol}
        if not report or not report.strip():
            return {"success": False, "task_type": "intelligence_report", "pair": pair, "error": "LLM produced no report", "data": real_data, "tradingview_symbol": tv_symbol}

        reason = fabrication_reason(report)
        if reason:
            logger.warning("ForexIntelligenceAgent: report for %s flagged (%s) -- qualifying it", pair, reason)
            report = annotate_uncertainty(report)

        return {
            "success": True, "task_type": "intelligence_report", "pair": pair,
            "report": report, "response": report, "data": real_data,
            "tradingview_symbol": tv_symbol,
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        query = task_data.get("query") or task_data.get("text", "")
        # Reachable from a normal chat question, not just a direct /agents/run
        # call -- "give me a full report on EUR/USD" should get the real
        # institutional report, not a generic LLM reply about forex in general.
        if any(t in query.lower() for t in _REPORT_TRIGGERS):
            pair = _extract_pair(query)
            if pair:
                return await self._intelligence_report(pair, _extract_timeframe(query))
        answer = await self._llm_answer(query)
        return {"success": True, "response": answer or (
            "I give you real live forex/metals quotes and real technical analysis -- never a trade, "
            "never a fabricated number."
        )}
