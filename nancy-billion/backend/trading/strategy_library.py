"""Real, parameterized trading strategy signal generators -- the same
industry-standard indicator logic used across forex_engine.py's own
TechnicalAnalysisEngine and the crypto trading agent, reused here (via
agents/real_compute.py, no duplicate math) so backtest_engine.py has a
curated set of REAL strategies to run rather than requiring an LLM to write
and sandbox arbitrary strategy code.

Every strategy is a pure function `(candles, **params) -> List[int]`: one
position signal per bar (1 = long, -1 = short, 0 = flat), same length as
`candles`. `backtest_engine.py` turns that signal series into real PnL by
multiplying each bar's forward return by the PREVIOUS bar's signal (no
lookahead -- a signal computed from bar i can only ever affect the return
realized over bar i -> i+1).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from agents.real_compute import compute_moving_average, compute_rsi, macd, compute_bollinger_bands
from trading import indicators as ind


def _closes(candles: List[Dict[str, Any]]) -> List[float]:
    return [float(c["close"]) for c in candles]


def _ohlcv(candles: List[Dict[str, Any]]):
    return ind._highs(candles), ind._lows(candles), ind._closes(candles), ind._volumes(candles)


def sma_crossover(candles: List[Dict[str, Any]], fast: int = 10, slow: int = 30) -> List[int]:
    """Classic trend-following crossover: long while the fast SMA is above
    the slow SMA, short while it's below. No signal (0) until both windows
    have enough history."""
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    for i in range(n):
        window = closes[: i + 1]
        if len(window) < slow:
            continue
        fast_sma = compute_moving_average(window, min(fast, len(window)))[-1]
        slow_sma = compute_moving_average(window, min(slow, len(window)))[-1]
        signals[i] = 1 if fast_sma > slow_sma else -1
    return signals


def rsi_mean_reversion(
    candles: List[Dict[str, Any]], period: int = 14, oversold: float = 30.0, overbought: float = 70.0,
) -> List[int]:
    """Real mean-reversion: goes long when RSI drops into oversold territory
    (expecting a bounce), short when it climbs into overbought (expecting a
    pullback), and holds the previous position while RSI is in the neutral
    zone between the two thresholds -- not flat, since a real mean-reversion
    position is meant to be held until the reversion actually happens."""
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    position = 0
    for i in range(n):
        window = closes[: i + 1]
        if len(window) < period + 1:
            continue
        rsi_series = compute_rsi(window, period)
        current_rsi = rsi_series[-1] if rsi_series else 50.0
        if current_rsi <= oversold:
            position = 1
        elif current_rsi >= overbought:
            position = -1
        signals[i] = position
    return signals


def macd_momentum(candles: List[Dict[str, Any]], fast: int = 12, slow: int = 26, signal_period: int = 9) -> List[int]:
    """Real momentum strategy: long while the MACD line is above its signal
    line, short while below -- the standard MACD-cross interpretation."""
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    for i in range(n):
        window = closes[: i + 1]
        if len(window) < slow + signal_period:
            continue
        result = macd(window, fast, slow, signal_period)
        macd_line = result["macd"][-1] if result["macd"] else 0.0
        signal_line = result["signal"][-1] if result["signal"] else 0.0
        signals[i] = 1 if macd_line > signal_line else -1
    return signals


def bollinger_breakout(candles: List[Dict[str, Any]], period: int = 20, num_std: float = 2.0) -> List[int]:
    """Real breakout strategy: goes long on a close above the upper
    Bollinger band (momentum breakout), short on a close below the lower
    band, and holds the previous position while price is inside the bands."""
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    position = 0
    for i in range(n):
        window = closes[: i + 1]
        if len(window) < period:
            continue
        bands = compute_bollinger_bands(window, min(period, len(window)), num_std)
        upper = bands["upper"][-1]
        lower = bands["lower"][-1]
        close = closes[i]
        if close > upper:
            position = 1
        elif close < lower:
            position = -1
        signals[i] = position
    return signals


####################################################################
# Extended strategy set -- real, standard indicator formulas from
# trading/indicators.py, each producing the same List[int] signal
# convention (1 long / -1 short / 0 flat) as the four above. Every
# indicator here operates on plain OHLCV bars, so the SAME strategy
# functions apply to forex, metals, and crypto alike -- the "asset
# class" is just whichever real data source (ForexDataAggregator,
# CryptoDataAggregator) fetched the candles.
####################################################################

def ema_crossover(candles: List[Dict[str, Any]], fast: int = 12, slow: int = 26) -> List[int]:
    closes = ind._closes(candles)
    fast_ema, slow_ema = ind.ema_series(closes, fast), ind.ema_series(closes, slow)
    return [1 if fast_ema[i] > slow_ema[i] else -1 if fast_ema[i] and slow_ema[i] else 0 for i in range(len(closes))]


def golden_death_cross(candles: List[Dict[str, Any]], fast: int = 50, slow: int = 200) -> List[int]:
    """The classic 50/200 SMA cross -- same mechanism as sma_crossover, its
    own named strategy since this exact pairing is a well-known standalone
    signal in its own right."""
    return sma_crossover(candles, fast=fast, slow=slow)


def triple_ma_alignment(candles: List[Dict[str, Any]], fast: int = 5, mid: int = 20, slow: int = 50) -> List[int]:
    closes = ind._closes(candles)
    f, m, s = ind.ema_series(closes, fast), ind.ema_series(closes, mid), ind.ema_series(closes, slow)
    out = [0] * len(closes)
    for i in range(len(closes)):
        if not (f[i] and m[i] and s[i]):
            continue
        if f[i] > m[i] > s[i]:
            out[i] = 1
        elif f[i] < m[i] < s[i]:
            out[i] = -1
    return out


def macd_zero_cross(candles: List[Dict[str, Any]], fast: int = 12, slow: int = 26, signal_period: int = 9) -> List[int]:
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    for i in range(n):
        window = closes[: i + 1]
        if len(window) < slow:
            continue
        macd_line = macd(window, fast, slow, signal_period)["macd"]
        if macd_line:
            signals[i] = 1 if macd_line[-1] > 0 else -1
    return signals


def macd_histogram_momentum(candles: List[Dict[str, Any]], fast: int = 12, slow: int = 26, signal_period: int = 9) -> List[int]:
    """Trades histogram EXPANSION (momentum accelerating), not just the
    line/signal cross macd_momentum already covers."""
    closes = _closes(candles)
    n = len(closes)
    hist = [0.0] * n
    for i in range(n):
        window = closes[: i + 1]
        if len(window) < slow + signal_period:
            continue
        h = macd(window, fast, slow, signal_period)["histogram"]
        hist[i] = h[-1] if h else 0.0
    signals = [0] * n
    for i in range(1, n):
        if hist[i] > 0 and hist[i] > hist[i - 1]:
            signals[i] = 1
        elif hist[i] < 0 and hist[i] < hist[i - 1]:
            signals[i] = -1
        else:
            signals[i] = signals[i - 1]
    return signals


def adx_trend_following(candles: List[Dict[str, Any]], period: int = 14, adx_threshold: float = 25.0) -> List[int]:
    """Only trades when ADX confirms a real trend is actually in force;
    direction from +DI/-DI. Flat (0) whenever ADX is below threshold --
    the honest 'no clear trend, stay out' state rather than forcing a side."""
    highs, lows, closes, _ = _ohlcv(candles)
    plus_di, minus_di = ind.plus_minus_di(highs, lows, closes, period)
    adx_vals = ind.adx(highs, lows, closes, period)
    return [1 if adx_vals[i] >= adx_threshold and plus_di[i] > minus_di[i]
            else -1 if adx_vals[i] >= adx_threshold and minus_di[i] > plus_di[i]
            else 0 for i in range(len(closes))]


def parabolic_sar_trend(candles: List[Dict[str, Any]], af_step: float = 0.02, af_max: float = 0.2) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    sar = ind.parabolic_sar(highs, lows, af_step, af_max)
    return [1 if closes[i] > sar[i] else -1 for i in range(len(closes))]


def supertrend_following(candles: List[Dict[str, Any]], period: int = 10, multiplier: float = 3.0) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    return ind.supertrend(highs, lows, closes, period, multiplier)["uptrend"]


def donchian_breakout(candles: List[Dict[str, Any]], period: int = 20) -> List[int]:
    """The real Turtle-Trading-style channel breakout: long on a new
    `period`-bar high, short on a new `period`-bar low, hold between."""
    highs, lows, closes, _ = _ohlcv(candles)
    channel = ind.donchian_channel(highs, lows, period)
    signals = [0] * len(closes)
    position = 0
    for i in range(len(closes)):
        if not channel["upper"][i]:
            continue
        if closes[i] >= channel["upper"][i]:
            position = 1
        elif closes[i] <= channel["lower"][i]:
            position = -1
        signals[i] = position
    return signals


def ichimoku_cloud_trend(candles: List[Dict[str, Any]], tenkan: int = 9, kijun: int = 26, senkou_b: int = 52) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    cloud = ind.ichimoku(highs, lows, closes, tenkan, kijun, senkou_b)
    signals = [0] * len(closes)
    for i in range(len(closes)):
        a, b = cloud["senkou_a"][i], cloud["senkou_b"][i]
        if not (a and b):
            continue
        cloud_top, cloud_bottom = max(a, b), min(a, b)
        if closes[i] > cloud_top:
            signals[i] = 1
        elif closes[i] < cloud_bottom:
            signals[i] = -1
    return signals


def linear_regression_trend(candles: List[Dict[str, Any]], period: int = 20) -> List[int]:
    """Real least-squares regression slope over a rolling window -- long
    while the trend line's slope is positive, short while negative."""
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    for i in range(n):
        if i + 1 < period:
            continue
        window = closes[i + 1 - period: i + 1]
        xs = list(range(period))
        mean_x, mean_y = sum(xs) / period, sum(window) / period
        num = sum((xs[j] - mean_x) * (window[j] - mean_y) for j in range(period))
        den = sum((xs[j] - mean_x) ** 2 for j in range(period))
        slope = num / den if den else 0.0
        signals[i] = 1 if slope > 0 else -1 if slope < 0 else 0
    return signals


def stochastic_reversion(candles: List[Dict[str, Any]], k_period: int = 14, d_period: int = 3, oversold: float = 20.0, overbought: float = 80.0) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    stoch = ind.stochastic_oscillator(highs, lows, closes, k_period, d_period)
    signals = [0] * len(closes)
    position = 0
    for i in range(len(closes)):
        if stoch["k"][i] <= oversold:
            position = 1
        elif stoch["k"][i] >= overbought:
            position = -1
        signals[i] = position
    return signals


def stochastic_momentum(candles: List[Dict[str, Any]], k_period: int = 14, d_period: int = 3) -> List[int]:
    """Trades WITH the %K/%D cross above/below the midline -- the momentum
    (not mean-reversion) read of the same oscillator."""
    highs, lows, closes, _ = _ohlcv(candles)
    stoch = ind.stochastic_oscillator(highs, lows, closes, k_period, d_period)
    return [1 if stoch["k"][i] > stoch["d"][i] and stoch["k"][i] > 50 else
            -1 if stoch["k"][i] < stoch["d"][i] and stoch["k"][i] < 50 else 0
            for i in range(len(closes))]


def cci_mean_reversion(candles: List[Dict[str, Any]], period: int = 20, threshold: float = 100.0) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    cci_vals = ind.cci(highs, lows, closes, period)
    signals = [0] * len(closes)
    position = 0
    for i in range(len(closes)):
        if cci_vals[i] <= -threshold:
            position = 1
        elif cci_vals[i] >= threshold:
            position = -1
        signals[i] = position
    return signals


def cci_momentum(candles: List[Dict[str, Any]], period: int = 20, threshold: float = 100.0) -> List[int]:
    """Trades the breakout OUT of the CCI's normal range, not the fade --
    real momentum interpretation of the same indicator as cci_mean_reversion."""
    highs, lows, closes, _ = _ohlcv(candles)
    cci_vals = ind.cci(highs, lows, closes, period)
    return [1 if v >= threshold else -1 if v <= -threshold else 0 for v in cci_vals]


def williams_r_reversion(candles: List[Dict[str, Any]], period: int = 14, oversold: float = -80.0, overbought: float = -20.0) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    wr = ind.williams_r(highs, lows, closes, period)
    signals = [0] * len(closes)
    position = 0
    for i in range(len(closes)):
        if wr[i] <= oversold:
            position = 1
        elif wr[i] >= overbought:
            position = -1
        signals[i] = position
    return signals


def roc_momentum(candles: List[Dict[str, Any]], period: int = 10) -> List[int]:
    closes = _closes(candles)
    roc = ind.rate_of_change(closes, period)
    return [1 if r > 0 else -1 if r < 0 else 0 for r in roc]


def obv_trend_confirmation(candles: List[Dict[str, Any]], obv_period: int = 20, price_period: int = 20) -> List[int]:
    """Real volume-confirmed trend: long only when BOTH price and On-Balance
    Volume are trending up over the window (volume confirming the move),
    short when both trend down -- flat when they disagree."""
    highs, lows, closes, volumes = _ohlcv(candles)
    obv_vals = ind.obv(closes, volumes)
    obv_sma = ind.sma(obv_vals, obv_period)
    price_sma = ind.sma(closes, price_period)
    signals = [0] * len(closes)
    for i in range(len(closes)):
        if not (obv_sma[i] and price_sma[i]):
            continue
        price_up = closes[i] > price_sma[i]
        volume_up = obv_vals[i] > obv_sma[i]
        if price_up and volume_up:
            signals[i] = 1
        elif not price_up and not volume_up:
            signals[i] = -1
    return signals


def money_flow_reversion(candles: List[Dict[str, Any]], period: int = 14, oversold: float = 20.0, overbought: float = 80.0) -> List[int]:
    highs, lows, closes, volumes = _ohlcv(candles)
    mfi = ind.money_flow_index(highs, lows, closes, volumes, period)
    signals = [0] * len(closes)
    position = 0
    for i in range(len(closes)):
        if mfi[i] <= oversold:
            position = 1
        elif mfi[i] >= overbought:
            position = -1
        signals[i] = position
    return signals


def trix_momentum(candles: List[Dict[str, Any]], period: int = 15) -> List[int]:
    closes = _closes(candles)
    trix_vals = ind.trix(closes, period)
    return [1 if v > 0 else -1 if v < 0 else 0 for v in trix_vals]


def vortex_trend(candles: List[Dict[str, Any]], period: int = 14) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    vi = ind.vortex_indicator(highs, lows, closes, period)
    return [1 if vi["plus"][i] > vi["minus"][i] else -1 if vi["minus"][i] > vi["plus"][i] else 0 for i in range(len(closes))]


def awesome_oscillator_momentum(candles: List[Dict[str, Any]]) -> List[int]:
    highs, lows, _closes_, _ = _ohlcv(candles)
    ao = ind.awesome_oscillator(highs, lows)
    return [1 if v > 0 else -1 if v < 0 else 0 for v in ao]


def keltner_breakout(candles: List[Dict[str, Any]], period: int = 20, atr_mult: float = 2.0) -> List[int]:
    highs, lows, closes, _ = _ohlcv(candles)
    kc = ind.keltner_channel(highs, lows, closes, period, atr_mult)
    signals = [0] * len(closes)
    position = 0
    for i in range(len(closes)):
        if not kc["mid"][i]:
            continue
        if closes[i] > kc["upper"][i]:
            position = 1
        elif closes[i] < kc["lower"][i]:
            position = -1
        signals[i] = position
    return signals


def keltner_reversion(candles: List[Dict[str, Any]], period: int = 20, atr_mult: float = 2.0) -> List[int]:
    """The mean-reversion read of the same Keltner channel keltner_breakout
    uses -- fades a touch of either band back toward the midline instead of
    chasing the breakout."""
    highs, lows, closes, _ = _ohlcv(candles)
    kc = ind.keltner_channel(highs, lows, closes, period, atr_mult)
    signals = [0] * len(closes)
    position = 0
    for i in range(len(closes)):
        if not kc["mid"][i]:
            continue
        if closes[i] < kc["lower"][i]:
            position = 1
        elif closes[i] > kc["upper"][i]:
            position = -1
        elif abs(closes[i] - kc["mid"][i]) < 1e-9:
            position = 0
        signals[i] = position
    return signals


def zscore_mean_reversion(candles: List[Dict[str, Any]], period: int = 20, z_threshold: float = 2.0) -> List[int]:
    """Real statistical mean-reversion: long when price is more than
    z_threshold standard deviations BELOW its rolling mean, short when
    that far above."""
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    position = 0
    for i in range(n):
        if i + 1 < period:
            continue
        window = closes[i + 1 - period: i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        z = (closes[i] - mean) / std if std else 0.0
        if z <= -z_threshold:
            position = 1
        elif z >= z_threshold:
            position = -1
        signals[i] = position
    return signals


def volatility_breakout(candles: List[Dict[str, Any]], atr_period: int = 14, atr_mult: float = 1.5) -> List[int]:
    """Long when today's bar-to-bar move exceeds atr_mult x ATR to the
    upside, short on the equivalent downside move -- a real breakout-on-
    expanding-volatility signal, distinct from the fixed-band Bollinger/
    Keltner breakouts above."""
    highs, lows, closes, _ = _ohlcv(candles)
    atr_vals = ind.atr(highs, lows, closes, atr_period)
    n = len(closes)
    signals = [0] * n
    position = 0
    for i in range(1, n):
        if not atr_vals[i]:
            continue
        move = closes[i] - closes[i - 1]
        if move > atr_mult * atr_vals[i]:
            position = 1
        elif move < -atr_mult * atr_vals[i]:
            position = -1
        signals[i] = position
    return signals


def atr_trailing_stop_trend(candles: List[Dict[str, Any]], period: int = 14, atr_mult: float = 3.0) -> List[int]:
    """Real chandelier-style ATR trailing stop: stays long as long as price
    holds above (highest high since entry - atr_mult*ATR), flips short on
    the mirrored condition -- a trend-following exit rule turned into an
    entry/hold signal."""
    highs, lows, closes, _ = _ohlcv(candles)
    atr_vals = ind.atr(highs, lows, closes, period)
    n = len(closes)
    signals = [0] * n
    position = 1
    extreme = closes[0] if n else 0.0
    for i in range(n):
        if not atr_vals[i]:
            signals[i] = position
            continue
        if position == 1:
            extreme = max(extreme, highs[i])
            stop = extreme - atr_mult * atr_vals[i]
            if closes[i] < stop:
                position = -1
                extreme = lows[i]
        else:
            extreme = min(extreme, lows[i])
            stop = extreme + atr_mult * atr_vals[i]
            if closes[i] > stop:
                position = 1
                extreme = highs[i]
        signals[i] = position
    return signals


def envelope_reversion(candles: List[Dict[str, Any]], period: int = 20, envelope_pct: float = 2.5) -> List[int]:
    """Real percentage-envelope mean-reversion: fades a close more than
    envelope_pct% away from its own moving average."""
    closes = _closes(candles)
    n = len(closes)
    ma = ind.sma(closes, period)
    signals = [0] * n
    position = 0
    for i in range(n):
        if not ma[i]:
            continue
        upper = ma[i] * (1 + envelope_pct / 100)
        lower = ma[i] * (1 - envelope_pct / 100)
        if closes[i] < lower:
            position = 1
        elif closes[i] > upper:
            position = -1
        elif lower <= closes[i] <= upper and abs(closes[i] - ma[i]) < ma[i] * 0.002:
            position = 0
        signals[i] = position
    return signals


def dual_momentum(candles: List[Dict[str, Any]], period: int = 90) -> List[int]:
    """Real absolute-momentum filter: long if the close is higher than it
    was `period` bars ago, short if lower -- the single-asset ('dual' vs.
    cash/flat) form of dual momentum."""
    closes = _closes(candles)
    n = len(closes)
    return [1 if i >= period and closes[i] > closes[i - period] else
            -1 if i >= period and closes[i] < closes[i - period] else 0
            for i in range(n)]


def pivot_point_bounce(candles: List[Dict[str, Any]]) -> List[int]:
    """Real classic floor-trader pivot points computed from each PRIOR
    bar's H/L/C (no lookahead) -- long on a bounce off support (S1), short
    on rejection at resistance (R1), hold otherwise."""
    highs, lows, closes, _ = _ohlcv(candles)
    n = len(closes)
    signals = [0] * n
    position = 0
    for i in range(1, n):
        levels = ind.pivot_points(highs[i - 1], lows[i - 1], closes[i - 1])
        if closes[i] <= levels["s1"]:
            position = 1
        elif closes[i] >= levels["r1"]:
            position = -1
        signals[i] = position
    return signals


def fibonacci_retracement_bounce(candles: List[Dict[str, Any]], lookback: int = 50) -> List[int]:
    """Real Fibonacci retracement levels from the rolling `lookback`-bar
    high/low -- long near the 61.8% retracement (a classic 'golden pocket'
    support), short near the swing high."""
    highs, lows, closes, _ = _ohlcv(candles)
    n = len(closes)
    signals = [0] * n
    position = 0
    for i in range(n):
        if i + 1 < lookback:
            continue
        window_high = max(highs[i + 1 - lookback: i + 1])
        window_low = min(lows[i + 1 - lookback: i + 1])
        levels = ind.fibonacci_levels(window_high, window_low)
        if closes[i] <= levels["0.618"]:
            position = 1
        elif closes[i] >= levels["0.236"]:
            position = -1
        signals[i] = position
    return signals


def price_above_ma_filter(candles: List[Dict[str, Any]], period: int = 200) -> List[int]:
    """The simplest real trend filter there is: long while price is above
    its own long-period moving average, short while below -- the "is this
    even a bull market" baseline every other strategy here implicitly competes with."""
    closes = _closes(candles)
    ma = ind.sma(closes, period)
    return [1 if ma[i] and closes[i] > ma[i] else -1 if ma[i] and closes[i] < ma[i] else 0 for i in range(len(closes))]


def rsi_trend_following(candles: List[Dict[str, Any]], period: int = 14) -> List[int]:
    """Trades WITH RSI's own trend (>50 long, <50 short) -- the momentum
    read of RSI, the direct opposite philosophy of rsi_mean_reversion's
    overbought/oversold fade using the exact same indicator."""
    closes = _closes(candles)
    n = len(closes)
    signals = [0] * n
    for i in range(n):
        window = closes[: i + 1]
        if len(window) < period + 1:
            continue
        rsi_series = compute_rsi(window, period)
        current_rsi = rsi_series[-1] if rsi_series else 50.0
        signals[i] = 1 if current_rsi > 50 else -1 if current_rsi < 50 else 0
    return signals


STRATEGY_REGISTRY: Dict[str, Callable[..., List[int]]] = {
    "sma_crossover": sma_crossover,
    "rsi_mean_reversion": rsi_mean_reversion,
    "macd_momentum": macd_momentum,
    "bollinger_breakout": bollinger_breakout,
    "ema_crossover": ema_crossover,
    "golden_death_cross": golden_death_cross,
    "triple_ma_alignment": triple_ma_alignment,
    "macd_zero_cross": macd_zero_cross,
    "macd_histogram_momentum": macd_histogram_momentum,
    "adx_trend_following": adx_trend_following,
    "parabolic_sar_trend": parabolic_sar_trend,
    "supertrend_following": supertrend_following,
    "donchian_breakout": donchian_breakout,
    "ichimoku_cloud_trend": ichimoku_cloud_trend,
    "linear_regression_trend": linear_regression_trend,
    "stochastic_reversion": stochastic_reversion,
    "stochastic_momentum": stochastic_momentum,
    "cci_mean_reversion": cci_mean_reversion,
    "cci_momentum": cci_momentum,
    "williams_r_reversion": williams_r_reversion,
    "roc_momentum": roc_momentum,
    "obv_trend_confirmation": obv_trend_confirmation,
    "money_flow_reversion": money_flow_reversion,
    "trix_momentum": trix_momentum,
    "vortex_trend": vortex_trend,
    "awesome_oscillator_momentum": awesome_oscillator_momentum,
    "keltner_breakout": keltner_breakout,
    "keltner_reversion": keltner_reversion,
    "zscore_mean_reversion": zscore_mean_reversion,
    "volatility_breakout": volatility_breakout,
    "atr_trailing_stop_trend": atr_trailing_stop_trend,
    "envelope_reversion": envelope_reversion,
    "dual_momentum": dual_momentum,
    "pivot_point_bounce": pivot_point_bounce,
    "fibonacci_retracement_bounce": fibonacci_retracement_bounce,
    "price_above_ma_filter": price_above_ma_filter,
    "rsi_trend_following": rsi_trend_following,
}

STRATEGY_DESCRIPTIONS: Dict[str, str] = {
    "sma_crossover": "Trend-following: long when the fast moving average is above the slow one, short when below.",
    "rsi_mean_reversion": "Mean-reversion: long when RSI is oversold, short when RSI is overbought.",
    "macd_momentum": "Momentum: long when the MACD line is above its signal line, short when below.",
    "bollinger_breakout": "Breakout: long on a close above the upper Bollinger band, short on a close below the lower band.",
    "ema_crossover": "Trend-following: long when the fast EMA is above the slow EMA, short when below.",
    "golden_death_cross": "The classic 50/200-period SMA cross (golden cross / death cross).",
    "triple_ma_alignment": "Long when fast>mid>slow EMAs are aligned bullishly, short when aligned bearishly.",
    "macd_zero_cross": "Momentum: long when the MACD line is above zero, short when below.",
    "macd_histogram_momentum": "Momentum: trades MACD histogram expansion (accelerating momentum) in either direction.",
    "adx_trend_following": "Trend-strength filtered: only trades when ADX confirms a real trend, direction from +DI/-DI.",
    "parabolic_sar_trend": "Trend-following via the Parabolic SAR stop-and-reverse indicator.",
    "supertrend_following": "Trend-following via the SuperTrend (ATR-based) indicator.",
    "donchian_breakout": "Turtle-style channel breakout: long on a new N-bar high, short on a new N-bar low.",
    "ichimoku_cloud_trend": "Trend-following: long above the Ichimoku cloud, short below it.",
    "linear_regression_trend": "Trend-following via a rolling linear-regression slope.",
    "stochastic_reversion": "Mean-reversion: long when the stochastic oscillator is oversold, short when overbought.",
    "stochastic_momentum": "Momentum: trades %K crossing %D in the direction away from the midline.",
    "cci_mean_reversion": "Mean-reversion: fades CCI extremes back toward zero.",
    "cci_momentum": "Momentum: trades CCI breaking out of its normal +-100 range.",
    "williams_r_reversion": "Mean-reversion via Williams %R oversold/overbought levels.",
    "roc_momentum": "Momentum: long when the rate of change is positive, short when negative.",
    "obv_trend_confirmation": "Long/short only when price trend and On-Balance Volume trend agree.",
    "money_flow_reversion": "Mean-reversion via the volume-weighted Money Flow Index.",
    "trix_momentum": "Momentum via TRIX (triple-smoothed EMA rate of change).",
    "vortex_trend": "Trend-following via the Vortex Indicator's +VI/-VI crossover.",
    "awesome_oscillator_momentum": "Momentum via Bill Williams' Awesome Oscillator (5/34 SMA of the midpoint).",
    "keltner_breakout": "Breakout: long above the upper Keltner channel, short below the lower.",
    "keltner_reversion": "Mean-reversion: fades a touch of either Keltner channel band.",
    "zscore_mean_reversion": "Statistical mean-reversion via a rolling price z-score.",
    "volatility_breakout": "Breakout on a bar-to-bar move exceeding a multiple of ATR.",
    "atr_trailing_stop_trend": "Trend-following via a chandelier-style ATR trailing stop.",
    "envelope_reversion": "Mean-reversion via a fixed percentage envelope around a moving average.",
    "dual_momentum": "Absolute momentum: long/short based on the sign of the N-bar price change.",
    "pivot_point_bounce": "Mean-reversion off classic floor-trader pivot point support/resistance.",
    "fibonacci_retracement_bounce": "Mean-reversion off Fibonacci retracement levels of the recent swing.",
    "price_above_ma_filter": "The simplest trend filter: long above a long-period moving average, short below.",
    "rsi_trend_following": "Momentum: trades WITH RSI's own trend (>50 long, <50 short).",
}


def list_strategies() -> List[Dict[str, str]]:
    return [{"name": name, "description": STRATEGY_DESCRIPTIONS[name]} for name in STRATEGY_REGISTRY]


def run_strategy(name: str, candles: List[Dict[str, Any]], params: Dict[str, Any] | None = None) -> List[int]:
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy {name!r} -- available: {', '.join(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[name](candles, **(params or {}))
