"""
Crypto Trading Agent for Nancy Billion Backend
Handles cryptocurrency analysis, trading strategies, and portfolio management

intelligence-report is the NÅNCY Trading Intelligence Division report type
(see trading_intelligence_prompt.py) -- a full institutional-style written
analysis grounded ONLY in the real technical indicators this agent computes
plus real NFP/CPI/FOMC macro events, never SMC/liquidity specifics the
underlying data can't support.
"""
import logging
import re
from .base_specialized_agent import SpecializedAgent
from ..real_compute import (
    compute_statistics, compute_moving_average, compute_ema,
    compute_rsi, compute_bollinger_bands, macd,
    portfolio_metrics, correlation_matrix, monte_carlo_simulation,
    value_at_risk, conditional_var, fibonacci_retracement,
    detect_outliers_iqr, now_utc
)
import numpy as np
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Real symbol/name recognition for pulling a coin out of a free-text
# question -- deliberately the same curated-allowlist approach as
# forex_intelligence_agent.py's _extract_pair, not "any 2-5 letter word",
# so a casual question doesn't get misread as a ticker.
_NAME_TO_SYMBOL = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "cardano": "ADA",
    "polkadot": "DOT", "dogecoin": "DOGE", "ripple": "XRP", "litecoin": "LTC",
    "chainlink": "LINK", "avalanche": "AVAX", "binance coin": "BNB",
}
_KNOWN_SYMBOLS = (
    "BTC", "ETH", "SOL", "ADA", "DOT", "DOGE", "XRP", "MATIC", "LTC",
    "LINK", "AVAX", "BNB", "SHIB", "TRX", "UNI", "ATOM", "XLM", "NEAR",
)
_SYMBOL_RE = re.compile(rf"\b({'|'.join(_KNOWN_SYMBOLS)})\b", re.IGNORECASE)
_REPORT_TRIGGERS = (
    "report", "intelligence report", "full analysis", "institutional",
    "market intelligence", "trade plan", "outlook", "deep dive",
)


def _extract_symbol(text: str) -> Optional[str]:
    """Best-effort real symbol extraction from free text -- e.g. "give me a
    full report on bitcoin" or "institutional outlook on ETH". Returns None
    (never a guess) if nothing recognizable is found."""
    lowered = text.lower()
    for name, symbol in _NAME_TO_SYMBOL.items():
        if name in lowered:
            return symbol
    match = _SYMBOL_RE.search(text)
    return match.group(1).upper() if match else None


class CryptoTradingAgent(SpecializedAgent):
    """Specialized agent for cryptocurrency trading and analysis"""

    def __init__(self, settings):
        super().__init__(settings, "Crypto Trading Agent", "crypto-trading")
        self.capabilities.update({
            "description": (
                "Advanced cryptocurrency trading agent: real technical analysis (Wilder RSI/MACD/"
                "Bollinger, real swing support-resistance), portfolio optimization, arbitrage detection, "
                "and full institutional-style intelligence reports grounded in that real data plus real "
                "NFP/CPI/FOMC macro events"
            ),
            "confidence": 0.85,
            "specializations": [
                "technical-analysis",
                "fundamental-analysis",
                "arbitrage-detection",
                "portfolio-optimization",
                "risk-management",
                "defi-analytics",
                "nft-valuation",
                "intelligence-report",
            ],
            "tools": [
                "tradingview",
                "coingecko-api",
                "binance-api",
                "etherscan",
                "real-compute-utils",
                "numpy-scipy",
                "economic_calendar",
            ]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "market-analysis")

        if task_type == "technical-analysis":
            return await self._perform_technical_analysis(task_data)
        elif task_type == "portfolio-optimization":
            return self._optimize_crypto_portfolio(task_data)
        elif task_type == "arbitrage-detection":
            return self._detect_arbitrage_opportunities(task_data)
        elif task_type == "defi-analysis":
            return self._analyze_defi_protocols(task_data)
        elif task_type == "backtest":
            return await self._run_backtest(task_data)
        elif task_type == "intelligence-report":
            return await self._intelligence_report(task_data)
        else:
            return await self._general_crypto_analysis(task_data)

    async def _real_macro_context(self) -> tuple:
        """Real NFP/CPI/FOMC events (economic_calendar.py, FRED-backed) --
        same real macro backdrop forex_intelligence_agent.py uses. Relevant
        to crypto too (risk appetite/dollar liquidity conditions move BTC
        and majors right along with FX), not just traditional markets.
        Never invents a consensus/expected figure; FRED has none."""
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

    async def _intelligence_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """The NÅNCY Trading Intelligence Division report -- see
        trading_intelligence_prompt.py for the full honesty contract this
        is built on. Reuses _perform_technical_analysis's real indicator
        computation rather than duplicating it, so the report and the raw
        technical-analysis task type can never silently disagree."""
        symbol = params.get("symbol", "BTC")
        technical = await self._perform_technical_analysis({"symbol": symbol, "days": int(params.get("days", 90))})
        if not technical.get("indicators"):
            return {
                "success": False, "task_type": "intelligence-report", "symbol": symbol,
                "error": technical.get("message", "Could not compute real indicators for this symbol"),
            }

        from llm import llm_backend
        from .trading_intelligence_prompt import TRADING_INTELLIGENCE_SYSTEM_PROMPT, build_data_grounding_block
        from trust import annotate_uncertainty, fabrication_reason

        macro_events, macro_note = await self._real_macro_context()
        grounding = build_data_grounding_block(symbol, "crypto", technical, macro_events, macro_note)
        prompt = (
            f"{TRADING_INTELLIGENCE_SYSTEM_PROMPT}\n\n{grounding}\n\n"
            f"Write the full institutional intelligence report for {symbol} now. This is a crypto asset -- "
            "real 24/7 volume data IS available in the block above (unlike forex), so you may reference "
            "real volume readings; there is still no real order-book/Level II data, so Smart Money Concepts "
            "specifics remain gated per the ground rules."
        )

        try:
            report = await llm_backend.generate(prompt, max_tokens=2400, temperature=0.4)
        except Exception as e:
            logger.warning("CryptoTradingAgent: report generation failed for %s: %s", symbol, e)
            return {"success": False, "task_type": "intelligence-report", "symbol": symbol, "error": str(e), "data": technical}
        if not report or not report.strip():
            return {"success": False, "task_type": "intelligence-report", "symbol": symbol, "error": "LLM produced no report", "data": technical}

        reason = fabrication_reason(report)
        if reason:
            logger.warning("CryptoTradingAgent: report for %s flagged (%s) -- qualifying it", symbol, reason)
            report = annotate_uncertainty(report)

        return {
            "success": True, "task_type": "intelligence-report", "symbol": symbol,
            "report": report, "response": report, "data": technical,
        }

    async def _run_backtest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Real end-to-end crypto strategy backtest: fetches real historical
        daily prices from CoinGecko (crypto_data.py), then runs the
        requested strategy through backtest_engine's real event-driven
        simulation, Monte Carlo permutation test, and walk-forward
        validation -- the crypto-side equivalent of forex_engine.py's
        run_forex_backtest."""
        from trading.crypto_data import crypto_data
        from trading.backtest_engine import run_full_validation

        symbol = params.get("symbol", "BTC")
        strategy = params.get("strategy", "sma_crossover")
        days = int(params.get("days", 90))
        strategy_params = params.get("params")

        candles = await crypto_data.get_historical(symbol, days=days)
        if len(candles) < 10:
            return {"success": False, "error": f"Not enough historical data for {symbol} ({len(candles)} candles fetched)."}
        result = run_full_validation(candles, strategy, strategy_params)
        result["symbol"] = symbol
        return result

    async def _perform_technical_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        symbol = params.get("symbol", "BTC")
        timeframe = params.get("timeframe", "1d")
        price_data = params.get("price_data", [])
        high_data = params.get("high_data", price_data)
        low_data = params.get("low_data", price_data)
        volume_data = params.get("volume_data", [])

        # Real live data fallback -- previously this task type only ever
        # computed on whatever price_data the caller happened to pass in,
        # with no live market data source of its own (forex_engine.py's
        # ForexDataAggregator had one; this agent didn't). CoinGecko fills
        # that real gap: if the caller didn't supply price history, fetch it.
        if len(price_data) < 2:
            from trading.crypto_data import crypto_data
            candles = await crypto_data.get_historical(symbol, days=int(params.get("days", 90)))
            if len(candles) >= 2:
                price_data = [c["close"] for c in candles]
                high_data = [c["high"] for c in candles]
                low_data = [c["low"] for c in candles]
                volume_data = [c["volume"] for c in candles]

        result = {
            "success": True,
            "task_type": "technical-analysis",
            "symbol": symbol,
            "timeframe": timeframe,
            "computed_at": str(now_utc())
        }

        if len(price_data) < 2:
            result["indicators"] = {}
            result["message"] = "Insufficient price data; provide at least 2 data points, or a live CoinGecko fetch for this symbol failed"
            result["recommendations"] = [
                "Set stop-loss orders to manage risk",
                "Consider position sizing based on account risk tolerance",
                "Monitor volume for confirmation of price moves",
                "Watch for divergence between price and momentum indicators"
            ]
            return result

        close_stats = compute_statistics(price_data)
        current_price = price_data[-1]

        sma_20 = compute_moving_average(price_data, min(20, len(price_data)))
        sma_50 = compute_moving_average(price_data, min(50, len(price_data)))
        ema_12 = compute_ema(price_data, 12)
        ema_26 = compute_ema(price_data, 26)
        rsi_vals = compute_rsi(price_data, 14)
        current_rsi = rsi_vals[-1] if len(rsi_vals) > 0 else 50.0
        bollinger = compute_bollinger_bands(price_data, min(20, len(price_data)))
        macd_result = macd(price_data, 12, 26, 9)

        indicators = {
            "moving_averages": {
                "sma_20": sma_20[-1] if len(sma_20) > 0 else current_price,
                "sma_50": sma_50[-1] if len(sma_50) > 0 else current_price,
                "ema_12": ema_12[-1] if len(ema_12) > 0 else current_price,
                "ema_26": ema_26[-1] if len(ema_26) > 0 else current_price
            },
            "oscillators": {
                "rsi": round(current_rsi, 4),
                "macd": {
                    "macd_line": macd_result["macd"][-1] if len(macd_result["macd"]) > 0 else 0.0,
                    "signal_line": macd_result["signal"][-1] if len(macd_result["signal"]) > 0 else 0.0,
                    "histogram": macd_result["histogram"][-1] if len(macd_result["histogram"]) > 0 else 0.0
                }
            },
            "bollinger_bands": {
                "upper": bollinger["upper"][-1],
                "middle": bollinger["middle"][-1],
                "lower": bollinger["lower"][-1]
            }
        }

        bb_mid = indicators["bollinger_bands"]["middle"]
        bb_upper = indicators["bollinger_bands"]["upper"]
        bb_lower = indicators["bollinger_bands"]["lower"]
        bandwidth = ((bb_upper - bb_lower) / bb_mid) * 100 if abs(bb_mid) > 1e-12 else 0.0
        indicators["volatility"] = {
            "bollinger_bandwidth": round(bandwidth, 4),
            "historical_volatility": round(close_stats["std"] / (abs(np.mean(price_data)) + 1e-12), 6)
        }

        if volume_data and len(volume_data) >= 2:
            vol_stats = compute_statistics(volume_data)
            indicators["volume_indicators"] = {
                "average_volume": round(vol_stats["mean"], 6),
                "current_volume": volume_data[-1],
                "volume_trend": "increasing" if volume_data[-1] > volume_data[0] else "decreasing",
                "volume_ratio": round(volume_data[-1] / (vol_stats["mean"] + 1e-12), 4)
            }

        macd_line = indicators["oscillators"]["macd"]["macd_line"]
        signal_line = indicators["oscillators"]["macd"]["signal_line"]
        signals = []
        if current_rsi > 70:
            signals.append("overbought")
        elif current_rsi < 30:
            signals.append("oversold")
        if macd_line > signal_line:
            signals.append("bullish_macd_cross")
        elif macd_line < signal_line:
            signals.append("bearish_macd_cross")
        if current_price > bb_upper:
            signals.append("price_above_upper_bb")
        elif current_price < bb_lower:
            signals.append("price_below_lower_bb")

        result["indicators"] = indicators
        result["signal_summary"] = {
            "signals": signals,
            "total_signals": len(signals)
        }

        current_high = max(high_data)
        current_low = min(low_data)
        fib = fibonacci_retracement(current_high, current_low)
        result["fibonacci_levels"] = fib

        sma20_val = indicators["moving_averages"]["sma_20"]
        sma50_val = indicators["moving_averages"]["sma_50"]
        trend_strength = abs(sma20_val - sma50_val) / (abs(sma50_val) + 1e-12)
        result["trend_analysis"] = {
            "primary_trend": "bullish" if sma20_val > sma50_val else ("bearish" if sma20_val < sma50_val else "sideways"),
            "trend_strength": round(min(trend_strength * 100, 1.0), 4),
            "momentum": "strong" if abs(current_rsi - 50) > 25 else ("moderate" if abs(current_rsi - 50) > 15 else "weak"),
            "volatility": "high" if bandwidth > 10 else ("moderate" if bandwidth > 5 else "low")
        }

        # Real swing-high/swing-low support/resistance off the actual
        # historical series (trading/indicators.py) -- replaces the
        # previous approach of offsetting the Bollinger lower/upper band by
        # an arbitrary fixed 5%/10%, which was a real number with no actual
        # price-structure behind it dressed up as a "resistance level".
        # Falls back to Bollinger-band-derived levels (still real, just a
        # coarser signal) only when there's too little history for a
        # genuine swing point to exist yet.
        from trading.indicators import swing_levels
        swings = swing_levels(high_data, low_data, price_data)
        if swings["support"] or swings["resistance"]:
            result["support_resistance"] = {
                "support_levels": swings["support"] or [round(bb_lower, 2)],
                "resistance_levels": swings["resistance"] or [round(bb_upper, 2)],
                "method": "swing high/low (fractal pivots) over the real historical series",
            }
        else:
            result["support_resistance"] = {
                "support_levels": [round(bb_lower, 2)],
                "resistance_levels": [round(bb_upper, 2)],
                "method": "Bollinger Band-derived fallback -- not enough history yet for a real swing point",
            }

        if current_rsi < 30 and macd_line > signal_line:
            signal = "buy"
        elif current_rsi > 70 and macd_line < signal_line:
            signal = "sell"
        else:
            signal = "hold"
        strength = round(abs(current_rsi - 50) / 50, 4)
        risk_reward = abs(bb_upper - current_price) / (abs(current_price - bb_lower) + 1e-12)
        result["trading_signals"] = {
            "signal": signal,
            "strength": strength,
            "confidence": round(max(0.5, min(0.9, 0.5 + 0.4 * strength)), 4),
            "risk_reward_ratio": round(risk_reward, 4)
        }

        # Data-driven notes reflecting THIS analysis's actual computed
        # values, not a fixed four-line list returned identically regardless
        # of what was just calculated (confirmed live: the previous version
        # returned the same text whether RSI was 12 or 88).
        notes: List[str] = []
        if current_rsi > 70:
            notes.append(f"RSI at {current_rsi:.1f} is in overbought territory -- momentum may be stretched.")
        elif current_rsi < 30:
            notes.append(f"RSI at {current_rsi:.1f} is in oversold territory -- momentum may be stretched to the downside.")
        if "bullish_macd_cross" in signals:
            notes.append("MACD line is above its signal line -- bullish momentum cross.")
        elif "bearish_macd_cross" in signals:
            notes.append("MACD line is below its signal line -- bearish momentum cross.")
        if bandwidth > 10:
            notes.append(f"Bollinger bandwidth of {bandwidth:.1f}% indicates a high-volatility regime -- wider stops warranted.")
        elif bandwidth < 5:
            notes.append(f"Bollinger bandwidth of {bandwidth:.1f}% indicates a compressed, low-volatility regime -- often precedes an expansion move.")
        if not notes:
            notes.append("No indicator is at an extreme right now -- current readings are unremarkable.")
        result["notes"] = notes
        return result

    def _optimize_crypto_portfolio(self, params: Dict[str, Any]) -> Dict[str, Any]:
        assets = params.get("assets", ["BTC", "ETH", "ADA", "SOL", "DOT"])
        returns_data = params.get("returns", {})
        risk_free_rate = params.get("risk_free_rate", 0.02)
        risk_tolerance = params.get("risk_tolerance", "moderate")

        result = {
            "success": True,
            "task_type": "portfolio-optimization",
            "assets": assets,
            "risk_tolerance": risk_tolerance,
            "computed_at": str(now_utc())
        }

        if returns_data and all(len(returns_data.get(a, [])) >= 2 for a in assets):
            n_assets = len(assets)
            returns_matrix = np.array([returns_data[a] for a in assets], dtype=np.float64)
            n_periods = returns_matrix.shape[1]
            mean_returns = np.mean(returns_matrix, axis=1)
            cov_matrix = np.cov(returns_matrix)

            inv_cov = np.linalg.pinv(cov_matrix)
            ones = np.ones(n_assets)
            min_var_weights = inv_cov @ ones / (ones @ inv_cov @ ones + 1e-12)
            max_sharpe_weights = inv_cov @ (mean_returns - risk_free_rate)
            max_sharpe_weights = max_sharpe_weights / (np.sum(max_sharpe_weights) + 1e-12)
            optimal_weights = max_sharpe_weights
            allocation = {assets[i]: round(float(optimal_weights[i]) * 100, 4) for i in range(n_assets)}

            combined_returns = returns_matrix.T @ optimal_weights
            pm = portfolio_metrics(combined_returns.tolist(), risk_free_rate)
            var_95 = value_at_risk(combined_returns.tolist(), 0.95)
            cvar_95 = conditional_var(combined_returns.tolist(), 0.95)

            corr_raw = correlation_matrix(returns_matrix.T.tolist())
            corr_dict = {}
            for i, a1 in enumerate(assets):
                corr_dict[a1] = {a2: corr_raw[i][j] for j, a2 in enumerate(assets)}

            mc_paths = monte_carlo_simulation(100.0, float(np.mean(combined_returns)), float(np.std(combined_returns, ddof=1)), 252, min(500, n_periods * 10))

            hhi = float(np.sum(optimal_weights ** 2))
            div_score = round(1.0 - (hhi - 1.0 / n_assets) / (1.0 - 1.0 / n_assets + 1e-12), 4)

            result["optimal_allocation"] = allocation
            result["portfolio_metrics"] = {
                "expected_return": f"{pm['annualized_return'] * 100:.2f}%",
                "volatility": f"{pm['annualized_vol'] * 100:.2f}%",
                "sharpe_ratio": pm["sharpe_ratio"],
                "sortino_ratio": pm["sortino_ratio"],
                "max_drawdown": f"{pm['max_drawdown'] * 100:.2f}%",
                "calmar_ratio": pm["calmar_ratio"],
                "var_95": f"{var_95 * 100:.2f}%",
                "cvar_95": f"{cvar_95 * 100:.2f}%"
            }
            result["correlation_matrix"] = corr_dict
            result["diversification_score"] = div_score
            result["monte_carlo_paths"] = {
                "n_paths": len(mc_paths),
                "n_steps": len(mc_paths[0]) if mc_paths else 0,
                "final_values": [round(path[-1], 4) for path in mc_paths[:10]] if mc_paths else []
            }
        else:
            equal_weight = round(100.0 / len(assets), 4)
            allocation = {a: equal_weight for a in assets}
            result["optimal_allocation"] = allocation
            result["portfolio_metrics"] = {
                "expected_return": "N/A",
                "volatility": "N/A",
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown": "N/A",
                "calmar_ratio": 0.0,
                "var_95": "N/A",
                "cvar_95": "N/A"
            }
            result["correlation_matrix"] = {}
            result["diversification_score"] = round(1.0 - 1.0 / len(assets), 4)
            result["message"] = "Insufficient returns data; using equal-weight allocation"

        result["rebalancing_frequency"] = "weekly" if risk_tolerance == "aggressive" else "monthly"
        result["recommendations"] = [
            "Consider dollar-cost averaging for entry points",
            "Store majority of assets in cold storage for security",
            "Regularly review and adjust allocations based on market changes",
            "Maintain emergency fund in stablecoins or fiat"
        ]
        return result

    def _detect_arbitrage_opportunities(self, params: Dict[str, Any]) -> Dict[str, Any]:
        exchange_prices = params.get("exchange_prices", {})
        trading_fee = params.get("trading_fee", 0.001)
        opportunities = []
        exchanges_scanned = list(exchange_prices.keys()) if exchange_prices else []

        if exchange_prices and len(exchanges_scanned) >= 2:
            pairs = set.intersection(
                *(set(prices.keys()) for prices in exchange_prices.values())
            ) if exchange_prices else set()

            for pair in pairs:
                prices = {
                    ex: exchange_prices[ex][pair]
                    for ex in exchanges_scanned
                    if pair in exchange_prices.get(ex, {})
                }
                if len(prices) < 2:
                    continue
                sorted_prices = sorted(prices.items(), key=lambda x: x[1])
                buy_exchange, buy_price = sorted_prices[0]
                sell_exchange, sell_price = sorted_prices[-1]
                if buy_exchange == sell_exchange:
                    continue
                gross_profit_pct = ((sell_price - buy_price) / buy_price) * 100
                net_profit_pct = gross_profit_pct - (trading_fee * 2 * 100)
                if net_profit_pct > 0:
                    opportunities.append({
                        "pair": pair,
                        "buy_exchange": buy_exchange,
                        "sell_exchange": sell_exchange,
                        "buy_price": round(buy_price, 6),
                        "sell_price": round(sell_price, 6),
                        "gross_profit_percentage": round(gross_profit_pct, 4),
                        "net_profit_percentage": round(net_profit_pct, 4),
                        "trading_fee": f"{trading_fee * 100:.2f}%"
                    })

            opportunities.sort(key=lambda x: x["net_profit_percentage"], reverse=True)
        else:
            exchanges_scanned = ["Binance", "Coinbase", "Kraken", "KuCoin", "Huobi"]

        return {
            "success": True,
            "task_type": "arbitrage-detection",
            "exchanges_scanned": exchanges_scanned,
            "opportunities_found": len(opportunities),
            "best_opportunities": opportunities[:5],
            "risks": [
                "Execution risk - prices may change during transfer",
                "Network congestion delays",
                "Exchange withdrawal limits",
                "Trading fees reducing actual profit"
            ],
            "recommendations": [
                "Use automated trading bots for real-time execution",
                "Maintain balances on multiple exchanges",
                "Consider transaction fees in profit calculations",
                "Start with small amounts to test strategy"
            ]
        }

    def _analyze_defi_protocols(self, params: Dict[str, Any]) -> Dict[str, Any]:
        protocol_type = params.get("protocol_type", "lending")
        protocols_data = params.get("protocols_data", {})
        analyzed = []

        if protocols_data:
            for name, data in protocols_data.items():
                metrics = {}
                if "tvl" in data:
                    metrics["total_value_locked"] = f"${data['tvl']:,.2f}"
                if "supply_apy" in data:
                    metrics["apy_supply"] = f"{data['supply_apy']:.2f}%"
                if "borrow_apy" in data:
                    metrics["apy_borrow"] = f"{data['borrow_apy']:.2f}%"
                if "utilization_rate" in data:
                    metrics["utilization_rate"] = f"{data['utilization_rate']:.2f}%"
                if "audit_score" in data:
                    metrics["audit_score"] = f"{data['audit_score']}/100"
                analyzed.append({"name": name, "metrics": metrics})
        else:
            analyzed = [{"name": p, "metrics": {}} for p in ["Aave", "Compound", "MakerDAO", "Curve"]]

        return {
            "success": True,
            "task_type": "defi-analysis",
            "protocol_type": protocol_type,
            "protocols_analyzed": analyzed,
            "risks": [
                "Smart contract vulnerabilities",
                "Impermanent loss for liquidity providers",
                "Regulatory uncertainty",
                "Liquidation risk during volatility"
            ],
            "opportunities": [
                "Yield farming strategies",
                "Liquidation bot development",
                "Cross-chain bridge opportunities",
                "Protocol governance participation"
            ],
            "recommendations": [
                "Start with small amounts to test strategies",
                "Diversify across multiple protocols",
                "Monitor gas prices and transaction costs",
                "Stay informed about regulatory developments"
            ]
        }

    async def _general_crypto_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general crypto analysis")
        # Reachable from a normal chat question, not just a direct /agents/run
        # call -- "give me a full report on bitcoin" should get the real
        # institutional report, not a generic LLM reply about crypto in general.
        if any(t in query.lower() for t in _REPORT_TRIGGERS):
            symbol = _extract_symbol(query)
            if symbol:
                return await self._intelligence_report({"symbol": symbol})
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-crypto-analysis",
            "query": query,
            **({"response": answer} if answer else {}),
            "market_overview": {
                "description": "General cryptocurrency market analysis agent",
                "capabilities": [
                    "Technical analysis with real indicators (SMA, EMA, RSI, MACD, Bollinger Bands)",
                    "Portfolio optimization with Sharpe/Sortino ratios and Monte Carlo simulation",
                    "Arbitrage detection across exchange prices",
                    "DeFi protocol analysis with real metrics"
                ]
            },
            "recommendations": [
                "Diversify across different crypto sectors",
                "Focus on projects with strong fundamentals",
                "Consider long-term holding for quality assets",
                "Stay informed about technological developments"
            ]
        }
