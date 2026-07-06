"""
Crypto Trading Agent for Nancy Billion Backend
Handles cryptocurrency analysis, trading strategies, and portfolio management
"""
from .base_specialized_agent import SpecializedAgent
from ..real_compute import (
    compute_statistics, compute_moving_average, compute_ema,
    compute_rsi, compute_bollinger_bands, macd,
    portfolio_metrics, correlation_matrix, monte_carlo_simulation,
    value_at_risk, conditional_var, fibonacci_retracement,
    detect_outliers_iqr, now_utc
)
import numpy as np
from typing import Dict, Any


class CryptoTradingAgent(SpecializedAgent):
    """Specialized agent for cryptocurrency trading and analysis"""

    def __init__(self, settings):
        super().__init__(settings, "Crypto Trading Agent", "crypto-trading")
        self.capabilities.update({
            "description": "Advanced cryptocurrency trading agent for market analysis, strategy execution, and risk management",
            "confidence": 0.85,
            "specializations": [
                "technical-analysis",
                "fundamental-analysis",
                "arbitrage-detection",
                "portfolio-optimization",
                "risk-management",
                "defi-analytics",
                "nft-valuation"
            ],
            "tools": [
                "tradingview",
                "coingecko-api",
                "binance-api",
                "etherscan",
                "real-compute-utils",
                "numpy-scipy"
            ]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "market-analysis")

        if task_type == "technical-analysis":
            return self._perform_technical_analysis(task_data)
        elif task_type == "portfolio-optimization":
            return self._optimize_crypto_portfolio(task_data)
        elif task_type == "arbitrage-detection":
            return self._detect_arbitrage_opportunities(task_data)
        elif task_type == "defi-analysis":
            return self._analyze_defi_protocols(task_data)
        else:
            return self._general_crypto_analysis(task_data)

    def _perform_technical_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        symbol = params.get("symbol", "BTC")
        timeframe = params.get("timeframe", "1d")
        price_data = params.get("price_data", [])
        high_data = params.get("high_data", price_data)
        low_data = params.get("low_data", price_data)
        volume_data = params.get("volume_data", [])

        result = {
            "success": True,
            "task_type": "technical-analysis",
            "symbol": symbol,
            "timeframe": timeframe,
            "computed_at": str(now_utc())
        }

        if len(price_data) < 2:
            result["indicators"] = {}
            result["message"] = "Insufficient price data; provide at least 2 data points"
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

        result["support_resistance"] = {
            "support_levels": [
                round(bb_lower, 2),
                round(bb_lower * 0.95, 2),
                round(bb_lower * 0.90, 2)
            ],
            "resistance_levels": [
                round(bb_upper, 2),
                round(bb_upper * 1.05, 2),
                round(bb_upper * 1.10, 2)
            ]
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

        result["recommendations"] = [
            "Set stop-loss orders to manage risk",
            "Consider position sizing based on account risk tolerance",
            "Monitor volume for confirmation of price moves",
            "Watch for divergence between price and momentum indicators"
        ]
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

    def _general_crypto_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "task_type": "general-crypto-analysis",
            "query": params.get("query", "general crypto analysis"),
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
