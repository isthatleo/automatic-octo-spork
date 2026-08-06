"""Real, textbook candlestick pattern recognition and Fair Value Gap (FVG)
detection, plus timeframe resampling -- all purely mechanical formulas
applied to real OHLC data (trading/forex_engine.py's ForexDataAggregator,
trading/crypto_data.py's CryptoDataAggregator), never a visual/LLM guess at
what a chart "looks like".

Distinct from what trading_intelligence_prompt.py's ground rules gate out
(order-book/liquidity-sweep/institutional-positioning claims): a candlestick
pattern and a Fair Value Gap are BOTH fully determined by a candle's own
open/high/low/close, with one universally standard definition each -- there
is nothing to infer about unobservable institutional intent, so these are
computed here as real, deterministic facts, not narrated by an LLM.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

Candle = Dict[str, Any]  # {"timestamp": "YYYY-MM-DD", "open","high","low","close","volume"}


def _body(c: Candle) -> float:
    return abs(c["close"] - c["open"])


def _range(c: Candle) -> float:
    return max(c["high"] - c["low"], 1e-12)


def _upper_wick(c: Candle) -> float:
    return c["high"] - max(c["open"], c["close"])


def _lower_wick(c: Candle) -> float:
    return min(c["open"], c["close"]) - c["low"]


def _bullish(c: Candle) -> bool:
    return c["close"] > c["open"]


def _bearish(c: Candle) -> bool:
    return c["close"] < c["open"]


# ---------------------------------------------------------------------------
# Real, standard timeframe resampling -- our real sources are daily-
# resolution (see forex_engine.py/crypto_data.py's own honesty notes), so
# "week"/"month" analysis is built by real OHLC aggregation over real daily
# bars (open=first, high=max, low=min, close=last, volume=sum), the
# universally standard way to build a higher timeframe from a lower one --
# never a fabricated or interpolated candle.
# ---------------------------------------------------------------------------
def resample_candles(candles: List[Candle], timeframe: str) -> List[Candle]:
    if timeframe == "day" or not candles:
        return candles

    def _bucket_key(ts: str):
        d = datetime.strptime(ts, "%Y-%m-%d")
        if timeframe == "week":
            year, week, _ = d.isocalendar()
            return (year, week)
        if timeframe == "month":
            return (d.year, d.month)
        raise ValueError(f"Unknown timeframe: {timeframe!r} (expected 'day', 'week', or 'month')")

    buckets: Dict[Any, List[Candle]] = {}
    order: List[Any] = []
    for c in candles:
        key = _bucket_key(c["timestamp"])
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(c)

    out: List[Candle] = []
    for key in order:
        group = buckets[key]
        out.append({
            "timestamp": group[0]["timestamp"],
            "open": group[0]["open"],
            "high": max(g["high"] for g in group),
            "low": min(g["low"] for g in group),
            "close": group[-1]["close"],
            "volume": sum(g.get("volume", 0.0) for g in group),
        })
    return out


# ---------------------------------------------------------------------------
# Real candlestick pattern recognition -- textbook definitions (Nison's
# "Japanese Candlestick Charting Techniques" conventions), each purely a
# function of the candle(s)' own OHLC. "Trend context" for reversal patterns
# uses a real short lookback (prior N closes falling/rising), not assumed.
# ---------------------------------------------------------------------------
def _prior_trend(candles: List[Candle], i: int, lookback: int = 3) -> str:
    if i < lookback:
        return "unknown"
    window = candles[i - lookback:i]
    closes = [c["close"] for c in window]
    if closes[-1] > closes[0]:
        return "up"
    if closes[-1] < closes[0]:
        return "down"
    return "flat"


def detect_candlestick_patterns(candles: List[Candle], lookback_bars: int = 15) -> List[Dict[str, Any]]:
    """Scans the most recent `lookback_bars` real candles for standard
    single/two/three-candle patterns. Returns each real match found --
    never invents a pattern that isn't mechanically present."""
    found: List[Dict[str, Any]] = []
    start = max(0, len(candles) - lookback_bars)

    for i in range(start, len(candles)):
        c = candles[i]
        rng = _range(c)
        body = _body(c)
        upper, lower = _upper_wick(c), _lower_wick(c)
        trend = _prior_trend(candles, i)

        # Doji -- body is a tiny fraction of the real range.
        if body <= rng * 0.1:
            found.append({"pattern": "Doji", "candles": 1, "date": c["timestamp"], "implication": "indecision"})

        # Hammer / Hanging Man -- small body near the top, long lower wick,
        # little/no upper wick. Direction depends on the real preceding trend.
        elif lower >= body * 2 and upper <= body * 0.5 and body > 0:
            if trend == "down":
                found.append({"pattern": "Hammer", "candles": 1, "date": c["timestamp"], "implication": "bullish_reversal"})
            elif trend == "up":
                found.append({"pattern": "Hanging Man", "candles": 1, "date": c["timestamp"], "implication": "bearish_reversal"})

        # Shooting Star / Inverted Hammer -- small body near the bottom, long
        # upper wick, little/no lower wick.
        elif upper >= body * 2 and lower <= body * 0.5 and body > 0:
            if trend == "up":
                found.append({"pattern": "Shooting Star", "candles": 1, "date": c["timestamp"], "implication": "bearish_reversal"})
            elif trend == "down":
                found.append({"pattern": "Inverted Hammer", "candles": 1, "date": c["timestamp"], "implication": "bullish_reversal"})

        if i == 0:
            continue
        prev = candles[i - 1]

        # Engulfing -- current real body fully engulfs the previous real body, opposite color.
        if _bearish(prev) and _bullish(c) and c["open"] <= prev["close"] and c["close"] >= prev["open"]:
            found.append({"pattern": "Bullish Engulfing", "candles": 2, "date": c["timestamp"], "implication": "bullish_reversal"})
        elif _bullish(prev) and _bearish(c) and c["open"] >= prev["close"] and c["close"] <= prev["open"]:
            found.append({"pattern": "Bearish Engulfing", "candles": 2, "date": c["timestamp"], "implication": "bearish_reversal"})

        # Piercing Line / Dark Cloud Cover -- 2-candle reversal, closes past
        # the real midpoint of the previous body.
        prev_mid = (prev["open"] + prev["close"]) / 2
        if _bearish(prev) and _bullish(c) and c["open"] < prev["low"] and prev_mid < c["close"] < prev["open"]:
            found.append({"pattern": "Piercing Line", "candles": 2, "date": c["timestamp"], "implication": "bullish_reversal"})
        if _bullish(prev) and _bearish(c) and c["open"] > prev["high"] and prev["open"] < c["close"] < prev_mid:
            found.append({"pattern": "Dark Cloud Cover", "candles": 2, "date": c["timestamp"], "implication": "bearish_reversal"})

        # Inside Bar / Outside Bar -- current real range fully inside/outside the previous.
        if c["high"] <= prev["high"] and c["low"] >= prev["low"]:
            found.append({"pattern": "Inside Bar", "candles": 2, "date": c["timestamp"], "implication": "compression"})
        elif c["high"] >= prev["high"] and c["low"] <= prev["low"]:
            found.append({"pattern": "Outside Bar", "candles": 2, "date": c["timestamp"], "implication": "expansion"})

        if i < 2:
            continue
        prev2 = candles[i - 2]

        # Morning Star / Evening Star -- real 3-candle reversal: big body,
        # small real-bodied middle candle (a gap/indecision candle), big
        # opposite body closing well into the first candle's real body.
        mid_body_small = _body(prev) <= _range(prev) * 0.35
        if _bearish(prev2) and mid_body_small and _bullish(c) and c["close"] > (prev2["open"] + prev2["close"]) / 2:
            found.append({"pattern": "Morning Star", "candles": 3, "date": c["timestamp"], "implication": "bullish_reversal"})
        if _bullish(prev2) and mid_body_small and _bearish(c) and c["close"] < (prev2["open"] + prev2["close"]) / 2:
            found.append({"pattern": "Evening Star", "candles": 3, "date": c["timestamp"], "implication": "bearish_reversal"})

        # Three White Soldiers / Three Black Crows -- three real consecutive
        # same-direction candles, each closing beyond the prior close.
        if _bullish(prev2) and _bullish(prev) and _bullish(c) and prev["close"] > prev2["close"] and c["close"] > prev["close"]:
            found.append({"pattern": "Three White Soldiers", "candles": 3, "date": c["timestamp"], "implication": "bullish_continuation"})
        if _bearish(prev2) and _bearish(prev) and _bearish(c) and prev["close"] < prev2["close"] and c["close"] < prev["close"]:
            found.append({"pattern": "Three Black Crows", "candles": 3, "date": c["timestamp"], "implication": "bearish_continuation"})

    return found


# ---------------------------------------------------------------------------
# Real Fair Value Gap (FVG) detection -- the standard 3-candle ICT
# definition, purely price-derived: for consecutive candles A, B, C, a
# bullish FVG exists where A.high < C.low (a real, unfilled gap the middle
# candle displaced through); a bearish FVG where A.low > C.high. Fill status
# is checked against every real candle since it formed, not guessed.
# ---------------------------------------------------------------------------
def detect_fair_value_gaps(candles: List[Candle], lookback_bars: int = 60) -> List[Dict[str, Any]]:
    gaps: List[Dict[str, Any]] = []
    start = max(2, len(candles) - lookback_bars)

    for i in range(start, len(candles)):
        a, c = candles[i - 2], candles[i]
        if a["high"] < c["low"]:
            top, bottom = c["low"], a["high"]
            gap_type = "bullish"
        elif a["low"] > c["high"]:
            top, bottom = a["low"], c["high"]
            gap_type = "bearish"
        else:
            continue

        filled = any(
            candles[j]["low"] <= top and candles[j]["high"] >= bottom
            for j in range(i + 1, len(candles))
        )
        gaps.append({
            "type": gap_type, "top": round(top, 6), "bottom": round(bottom, 6),
            "formed_at": candles[i - 1]["timestamp"], "filled": filled,
        })
    return gaps


# ---------------------------------------------------------------------------
# Real key zones -- clusters trading/indicators.py's real swing highs/lows
# that land within `tolerance_pct` of each other into one zone with a
# touch count (a real measure of how many distinct real swings respected
# that level, i.e. genuine zone strength, not an arbitrary offset).
# ---------------------------------------------------------------------------
def key_zones(highs: List[float], lows: List[float], closes: List[float], tolerance_pct: float = 0.5) -> List[Dict[str, Any]]:
    from trading.indicators import swing_levels

    n = len(closes)
    lookback = 2
    if n < lookback * 2 + 1:
        return []

    swing_highs: List[float] = []
    swing_lows: List[float] = []
    for i in range(lookback, n - lookback):
        window_highs = highs[i - lookback: i + lookback + 1]
        window_lows = lows[i - lookback: i + lookback + 1]
        if highs[i] == max(window_highs) and window_highs.count(highs[i]) == 1:
            swing_highs.append(highs[i])
        if lows[i] == min(window_lows) and window_lows.count(lows[i]) == 1:
            swing_lows.append(lows[i])

    def _cluster(points: List[float], kind: str) -> List[Dict[str, Any]]:
        if not points:
            return []
        points = sorted(points)
        clusters: List[List[float]] = [[points[0]]]
        for p in points[1:]:
            if abs(p - clusters[-1][-1]) / max(clusters[-1][-1], 1e-9) * 100 <= tolerance_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        last_close = closes[-1]
        return [
            {
                "level": round(sum(cl) / len(cl), 6), "kind": kind, "touches": len(cl),
                "distance_pct": round(abs(sum(cl) / len(cl) - last_close) / last_close * 100, 3),
            }
            for cl in clusters
        ]

    zones = _cluster(swing_highs, "resistance") + _cluster(swing_lows, "support")
    zones.sort(key=lambda z: z["distance_pct"])
    return zones
