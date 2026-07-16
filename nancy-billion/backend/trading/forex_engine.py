"""
Forex Trading Intelligence Engine for Nancy/Billion

Provides:
- Real-time market data aggregation
- Technical analysis (support/resistance, trends)
- Strategy recommendations
- Risk monitoring and alerts
- Trade history analysis
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Market trend direction"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class RiskLevel(Enum):
    """Risk assessment levels"""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class MarketSnapshot:
    """Current market state for a forex pair"""
    pair: str  # EUR/USD, GBP/USD, etc.
    price: float
    bid: float
    ask: float
    change_24h: float  # Percentage change
    high_24h: float
    low_24h: float
    volume: float
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class TechnicalAnalysis:
    """Technical analysis results"""
    pair: str
    trend: TrendDirection
    support_levels: List[float]
    resistance_levels: List[float]
    pivot_point: float
    momentum: float  # -1.0 to 1.0
    volatility: float  # 0.0 to 1.0
    rsi: float  # Relative Strength Index (0-100)
    macd: float  # Moving Average Convergence Divergence

    def to_dict(self) -> Dict:
        return {
            "pair": self.pair,
            "trend": self.trend.value,
            "support_levels": self.support_levels,
            "resistance_levels": self.resistance_levels,
            "pivot_point": self.pivot_point,
            "momentum": self.momentum,
            "volatility": self.volatility,
            "rsi": self.rsi,
            "macd": self.macd,
        }


class ForexDataAggregator:
    """
    Real forex market data via Frankfurter (frankfurter.app) — free, key-less,
    ECB reference rates, no geographic account restrictions.

    Honesty note: these are **daily-resolution ECB reference rates**, not live
    tick/bid-ask data from a broker or exchange. That's a genuine limitation,
    not a simulation — the numbers returned are real historical/current rates,
    just not sub-second granularity. Bid/ask here is a small synthetic spread
    around the real mid rate (Frankfurter has no bid/ask), clearly derived, not
    fabricated market data. No order execution is wired to this — see
    `TradingManager` for the (currently unconnected) execution path; before any
    real broker/execution integration is added, `volume` should be treated as
    unavailable rather than estimated.
    """

    BASE_URL = "https://api.frankfurter.app"
    _SYNTHETIC_SPREAD_BPS = 1.5  # ~1.5 basis points either side of mid, informational only

    def __init__(self):
        self.cache: Dict[str, MarketSnapshot] = {}
        self.last_update: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def _split_pair(pair: str) -> Tuple[str, str]:
        base, _, quote = pair.upper().partition("/")
        if not base or not quote:
            raise ValueError(f"Invalid pair format: {pair!r}, expected e.g. 'EUR/USD'")
        return base, quote

    async def get_price(self, pair: str) -> Optional[MarketSnapshot]:
        """
        Get current mid-market rate for a forex pair from Frankfurter (real ECB data).

        Args:
            pair: e.g., "EUR/USD", "GBP/JPY"

        Returns:
            MarketSnapshot with real rate data, or None if the pair/network call fails.
        """
        cached = self.cache.get(pair)
        if cached and datetime.now() - self.last_update.get(pair, datetime.min) < self._cache_ttl:
            return cached

        import aiohttp

        base, quote = self._split_pair(pair)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/latest", params={"from": base, "to": quote}, timeout=10
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Frankfurter error for {pair}: HTTP {resp.status}")
                        return None
                    data = await resp.json()

                price = data.get("rates", {}).get(quote)
                if price is None:
                    logger.error(f"Frankfurter response missing rate for {pair}: {data}")
                    return None

                # Real 24h-equivalent change/high/low from the last available prior business day
                yesterday = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
                today = datetime.now().strftime("%Y-%m-%d")
                high_24h = low_24h = price
                change_24h = 0.0
                async with session.get(
                    f"{self.BASE_URL}/{yesterday}..{today}",
                    params={"from": base, "to": quote},
                    timeout=10,
                ) as hist_resp:
                    if hist_resp.status == 200:
                        hist_data = await hist_resp.json()
                        series = hist_data.get("rates", {})
                        values = [v.get(quote) for v in series.values() if quote in v]
                        if values:
                            high_24h = max(values)
                            low_24h = min(values)
                            if len(values) >= 2 and values[0]:
                                change_24h = ((values[-1] - values[0]) / values[0]) * 100

                spread = price * (self._SYNTHETIC_SPREAD_BPS / 10000)
                snapshot = MarketSnapshot(
                    pair=pair,
                    price=price,
                    bid=round(price - spread, 6),
                    ask=round(price + spread, 6),
                    change_24h=round(change_24h, 4),
                    high_24h=high_24h,
                    low_24h=low_24h,
                    volume=0.0,  # unavailable from this free source — not estimated
                )
                self.cache[pair] = snapshot
                self.last_update[pair] = datetime.now()
                return snapshot
        except Exception as e:
            logger.error(f"Failed to fetch real price for {pair}: {e}")
            return None

    async def get_historical(self, pair: str, period: str = "1d", days: int = 30) -> List[Dict]:
        """
        Get real historical daily rates for analysis (Frankfurter has daily
        resolution only — `period` is accepted for interface compatibility but
        finer intraday granularity isn't available from this free source).

        Args:
            pair: Forex pair
            period: kept for interface compatibility; data is always daily
            days: how many calendar days of history to fetch

        Returns:
            List of daily OHLC-shaped dicts built from real close-to-close rates
            (open==prior close, high/low==close since no intraday data exists).
        """
        import aiohttp

        base, quote = self._split_pair(pair)
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/{start}..{end}",
                    params={"from": base, "to": quote},
                    timeout=10,
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Frankfurter historical error for {pair}: HTTP {resp.status}")
                        return []
                    data = await resp.json()

            series = data.get("rates", {})
            dates = sorted(series.keys())
            candles: List[Dict] = []
            prev_close: Optional[float] = None
            for d in dates:
                close = series[d].get(quote)
                if close is None:
                    continue
                open_ = prev_close if prev_close is not None else close
                candles.append({
                    "timestamp": d,
                    "open": open_,
                    "high": max(open_, close),
                    "low": min(open_, close),
                    "close": close,
                    "volume": 0.0,  # unavailable from this free source
                })
                prev_close = close
            return candles
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {pair}: {e}")
            return []


class TechnicalAnalysisEngine:
    """
    Performs technical analysis on forex data.

    Calculates:
    - Support/resistance levels
    - Trend direction
    - Momentum indicators (RSI, MACD)
    - Volatility
    """

    def __init__(self):
        self.analysis_cache = {}

    def analyze(self, pair: str, snapshot: MarketSnapshot, historical: List[Dict]) -> TechnicalAnalysis:
        """
        Perform technical analysis on a forex pair.
        """
        # Calculate trend
        trend = self._detect_trend(snapshot, historical)

        # Find support/resistance
        support, resistance = self._find_levels(snapshot, historical)

        # Calculate indicators
        pivot = self._calculate_pivot(snapshot)
        momentum = self._calculate_momentum(snapshot, historical)
        volatility = self._calculate_volatility(snapshot, historical)
        rsi = self._calculate_rsi(historical)
        macd = self._calculate_macd(historical)

        analysis = TechnicalAnalysis(
            pair=pair,
            trend=trend,
            support_levels=support,
            resistance_levels=resistance,
            pivot_point=pivot,
            momentum=momentum,
            volatility=volatility,
            rsi=rsi,
            macd=macd,
        )

        self.analysis_cache[pair] = analysis
        return analysis

    def _detect_trend(self, snapshot: MarketSnapshot, historical: List[Dict]) -> TrendDirection:
        """Detect bullish/bearish trend"""
        if snapshot.change_24h > 0.5:
            return TrendDirection.BULLISH
        elif snapshot.change_24h < -0.5:
            return TrendDirection.BEARISH
        return TrendDirection.NEUTRAL

    def _find_levels(self, snapshot: MarketSnapshot, historical: List[Dict]) -> Tuple[List[float], List[float]]:
        """Find support and resistance levels"""
        support = [snapshot.low_24h * 0.99, snapshot.low_24h * 0.995]
        resistance = [snapshot.high_24h * 1.005, snapshot.high_24h * 1.01]
        return support, resistance

    def _calculate_pivot(self, snapshot: MarketSnapshot) -> float:
        """Calculate pivot point"""
        return (snapshot.high_24h + snapshot.low_24h + snapshot.price) / 3

    def _calculate_momentum(self, snapshot: MarketSnapshot, historical: List[Dict]) -> float:
        """Calculate momentum (-1.0 to 1.0)"""
        change = snapshot.change_24h
        # Normalize to -1.0 to 1.0 range
        return max(-1.0, min(1.0, change / 2.0))

    def _calculate_volatility(self, snapshot: MarketSnapshot, historical: List[Dict]) -> float:
        """Calculate volatility (0.0 to 1.0)"""
        range_24h = snapshot.high_24h - snapshot.low_24h
        volatility = (range_24h / snapshot.price) * 100
        # Normalize to 0.0 to 1.0
        return min(1.0, volatility / 2.0)

    def _calculate_rsi(self, historical: List[Dict]) -> float:
        """Calculate Relative Strength Index (0-100)"""
        # Simplified RSI calculation
        if not historical or len(historical) < 2:
            return 50.0

        gains = sum(max(0, h.get("close", 0) - historical[i-1].get("close", 0))
                   for i, h in enumerate(historical[1:], 1))
        losses = sum(max(0, historical[i-1].get("close", 0) - h.get("close", 0))
                    for i, h in enumerate(historical[1:], 1))

        if losses == 0:
            return 100.0 if gains > 0 else 50.0

        rs = gains / losses
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_macd(self, historical: List[Dict]) -> float:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        # Simplified MACD calculation
        if not historical:
            return 0.0

        closes = [h.get("close", 0) for h in historical[-26:]]
        if len(closes) < 26:
            return 0.0

        ema12 = sum(closes[-12:]) / 12
        ema26 = sum(closes) / 26
        macd = ema12 - ema26
        return macd


class StrategyAdvisor:
    """
    Provides trading strategy recommendations based on analysis.

    Generates:
    - Entry/exit suggestions
    - Position sizing recommendations
    - Stop-loss and take-profit levels
    - Trade ideas
    """

    def __init__(self):
        self.strategies = {}

    def get_recommendation(self, analysis: TechnicalAnalysis, risk_tolerance: str = "moderate") -> Dict:
        """
        Get trading recommendation based on technical analysis.

        Args:
            analysis: Technical analysis results
            risk_tolerance: "conservative", "moderate", "aggressive"

        Returns:
            Trading recommendation with entry, exit, SL, TP
        """
        trend = analysis.trend
        volatility = analysis.volatility
        rsi = analysis.rsi

        recommendation = {
            "pair": analysis.pair,
            "trend": trend.value,
            "signal": "HOLD"
        }

        # Generate signal based on analysis
        if trend == TrendDirection.BULLISH and rsi < 70:
            recommendation["signal"] = "BUY"
            recommendation["entry"] = analysis.support_levels[0] if analysis.support_levels else None
            recommendation["take_profit"] = analysis.resistance_levels[-1] if analysis.resistance_levels else None
            recommendation["stop_loss"] = analysis.support_levels[-1] if len(analysis.support_levels) > 1 else None
            recommendation["reason"] = "Bullish trend forming, RSI not overbought"

        elif trend == TrendDirection.BEARISH and rsi > 30:
            recommendation["signal"] = "SELL"
            recommendation["entry"] = analysis.resistance_levels[-1] if analysis.resistance_levels else None
            recommendation["take_profit"] = analysis.support_levels[0] if analysis.support_levels else None
            recommendation["stop_loss"] = analysis.resistance_levels[0] if len(analysis.resistance_levels) > 1 else None
            recommendation["reason"] = "Bearish trend forming, RSI not oversold"

        else:
            recommendation["reason"] = "Wait for confirmation"

        # Position sizing based on risk tolerance
        if risk_tolerance == "conservative":
            recommendation["position_size_pct"] = 1.0
        elif risk_tolerance == "aggressive":
            recommendation["position_size_pct"] = 5.0
        else:
            recommendation["position_size_pct"] = 2.0

        return recommendation


class RiskMonitor:
    """
    Monitors trading risks and generates alerts.

    Tracks:
    - Account drawdown
    - Position sizing
    - Correlation between trades
    - Leverage exposure
    """

    def __init__(self, account_balance: float = 100000):
        self.account_balance = account_balance
        self.initial_balance = account_balance
        self.trades = []

    def assess_risk(self, trades: List[Dict]) -> Dict:
        """
        Assess overall trading risk.

        Returns risk level and recommendations.
        """
        total_risk = sum(t.get("risk_amount", 0) for t in trades)
        win_rate = self._calculate_win_rate(trades)
        drawdown = self._calculate_drawdown()

        risk_level = self._determine_risk_level(total_risk, drawdown, win_rate)

        return {
            "risk_level": risk_level.value,
            "total_risk_amount": total_risk,
            "account_risk_pct": (total_risk / self.account_balance) * 100,
            "drawdown_pct": drawdown,
            "win_rate": win_rate,
            "recommendations": self._get_risk_recommendations(risk_level)
        }

    def _calculate_win_rate(self, trades: List[Dict]) -> float:
        """Calculate win rate from trade history"""
        if not trades:
            return 50.0

        wins = sum(1 for t in trades if t.get("result") == "win")
        return (wins / len(trades)) * 100

    def _calculate_drawdown(self) -> float:
        """Calculate account drawdown percentage"""
        if self.account_balance >= self.initial_balance:
            return 0.0

        drawdown = ((self.initial_balance - self.account_balance) / self.initial_balance) * 100
        return drawdown

    def _determine_risk_level(self, total_risk: float, drawdown: float, win_rate: float) -> RiskLevel:
        """Determine overall risk level"""
        if drawdown > 20:
            return RiskLevel.EXTREME
        elif drawdown > 10 or total_risk > self.account_balance * 0.05:
            return RiskLevel.HIGH
        elif drawdown > 5 or total_risk > self.account_balance * 0.02:
            return RiskLevel.MODERATE
        else:
            return RiskLevel.LOW

    def _get_risk_recommendations(self, risk_level: RiskLevel) -> List[str]:
        """Get recommendations based on risk level"""
        recommendations = {
            RiskLevel.LOW: ["Continue current trading strategy"],
            RiskLevel.MODERATE: ["Consider reducing position sizes", "Evaluate win rate"],
            RiskLevel.HIGH: ["Reduce exposure immediately", "Review trading plan"],
            RiskLevel.EXTREME: ["STOP TRADING", "Reduce all positions", "Reassess strategy"],
        }
        return recommendations.get(risk_level, [])


# Example usage
if __name__ == "__main__":
    import asyncio

    async def main():
        # Initialize components
        aggregator = ForexDataAggregator()
        analyzer = TechnicalAnalysisEngine()
        advisor = StrategyAdvisor()
        risk_monitor = RiskMonitor()

        # Get market data
        snapshot = await aggregator.get_price("EUR/USD")
        historical = await aggregator.get_historical("EUR/USD")

        if snapshot:
            print(f"EUR/USD: {snapshot.price}")

            # Analyze
            analysis = analyzer.analyze("EUR/USD", snapshot, historical)
            print(f"Trend: {analysis.trend.value}")
            print(f"Support: {analysis.support_levels}")
            print(f"Resistance: {analysis.resistance_levels}")

            # Get recommendation
            rec = advisor.get_recommendation(analysis)
            print(f"Signal: {rec['signal']}")

            # Assess risk
            risk = risk_monitor.assess_risk([])
            print(f"Risk Level: {risk['risk_level']}")

    asyncio.run(main())

