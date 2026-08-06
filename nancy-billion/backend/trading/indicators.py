"""Real technical indicator formulas -- standard, textbook implementations
(Wilder's ATR/ADX/DI smoothing, classic stochastic/CCI/Williams %R/ROC/OBV/
MFI/TRIX/Vortex/Awesome Oscillator/Parabolic SAR/SuperTrend/Keltner/Ichimoku/
floor pivot points), each a full-series function: takes the whole price
series once, returns a same-length series (warm-up bars before enough
history exists are filled with a neutral placeholder, never fabricated).
Used by strategy_library.py's extended strategy set -- agents/real_compute.py
already covers SMA/EMA/RSI/Bollinger/MACD, so those aren't duplicated here.
"""
from __future__ import annotations

from typing import Dict, List, Tuple


def _closes(candles): return [float(c["close"]) for c in candles]
def _highs(candles): return [float(c.get("high", c["close"])) for c in candles]
def _lows(candles): return [float(c.get("low", c["close"])) for c in candles]
def _volumes(candles): return [float(c.get("volume", 0.0)) for c in candles]


def sma(data: List[float], period: int) -> List[float]:
    out = [0.0] * len(data)
    for i in range(len(data)):
        if i + 1 < period:
            continue
        out[i] = sum(data[i + 1 - period: i + 1]) / period
    return out


def ema_series(data: List[float], period: int) -> List[float]:
    """Full EMA series (agents/real_compute.py's compute_ema only returns
    the tail once fully warmed -- this keeps a value at every index, 0.0
    until the first `period` bars are available, so it lines up 1:1 with
    other full-series indicators here)."""
    out = [0.0] * len(data)
    k = 2.0 / (period + 1)
    ema_val = None
    for i, price in enumerate(data):
        if ema_val is None:
            if i + 1 < period:
                continue
            ema_val = sum(data[: period]) / period
        else:
            ema_val = price * k + ema_val * (1 - k)
        out[i] = ema_val
    return out


def true_range(highs: List[float], lows: List[float], closes: List[float]) -> List[float]:
    out = [0.0] * len(closes)
    for i in range(len(closes)):
        if i == 0:
            out[i] = highs[i] - lows[i]
            continue
        out[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    return out


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    tr = true_range(highs, lows, closes)
    out = [0.0] * len(closes)
    val = None
    for i in range(len(closes)):
        if val is None:
            if i + 1 < period:
                continue
            val = sum(tr[: period]) / period
        else:
            val = (val * (period - 1) + tr[i]) / period
        out[i] = val
    return out


def plus_minus_di(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[List[float], List[float]]:
    n = len(closes)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
    tr = true_range(highs, lows, closes)

    def _wilder_smooth(series: List[float]) -> List[float]:
        out = [0.0] * n
        val = None
        for i in range(n):
            if val is None:
                if i + 1 < period:
                    continue
                val = sum(series[1: period + 1]) if period + 1 <= n else sum(series[1:i + 1])
            else:
                val = val - (val / period) + series[i]
            out[i] = val
        return out

    smoothed_tr = _wilder_smooth(tr)
    smoothed_plus = _wilder_smooth(plus_dm)
    smoothed_minus = _wilder_smooth(minus_dm)
    plus_di = [100.0 * smoothed_plus[i] / smoothed_tr[i] if smoothed_tr[i] else 0.0 for i in range(n)]
    minus_di = [100.0 * smoothed_minus[i] / smoothed_tr[i] if smoothed_tr[i] else 0.0 for i in range(n)]
    return plus_di, minus_di


def adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    plus_di, minus_di = plus_minus_di(highs, lows, closes, period)
    n = len(closes)
    dx = [0.0] * n
    for i in range(n):
        total = plus_di[i] + minus_di[i]
        dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / total if total else 0.0
    return sma(dx, period)


def donchian_channel(highs: List[float], lows: List[float], period: int = 20) -> Dict[str, List[float]]:
    n = len(highs)
    upper = [0.0] * n
    lower = [0.0] * n
    for i in range(n):
        if i + 1 < period:
            continue
        upper[i] = max(highs[i + 1 - period: i + 1])
        lower[i] = min(lows[i + 1 - period: i + 1])
    mid = [(u + l) / 2 if u or l else 0.0 for u, l in zip(upper, lower)]
    return {"upper": upper, "lower": lower, "mid": mid}


def stochastic_oscillator(highs: List[float], lows: List[float], closes: List[float], k_period: int = 14, d_period: int = 3) -> Dict[str, List[float]]:
    n = len(closes)
    k = [50.0] * n
    for i in range(n):
        if i + 1 < k_period:
            continue
        hh = max(highs[i + 1 - k_period: i + 1])
        ll = min(lows[i + 1 - k_period: i + 1])
        k[i] = 100.0 * (closes[i] - ll) / (hh - ll) if hh != ll else 50.0
    d = sma(k, d_period)
    return {"k": k, "d": d}


def cci(highs: List[float], lows: List[float], closes: List[float], period: int = 20) -> List[float]:
    n = len(closes)
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    out = [0.0] * n
    for i in range(n):
        if i + 1 < period:
            continue
        window = typical[i + 1 - period: i + 1]
        mean_tp = sum(window) / period
        mean_dev = sum(abs(t - mean_tp) for t in window) / period
        out[i] = (typical[i] - mean_tp) / (0.015 * mean_dev) if mean_dev else 0.0
    return out


def williams_r(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    n = len(closes)
    out = [-50.0] * n
    for i in range(n):
        if i + 1 < period:
            continue
        hh = max(highs[i + 1 - period: i + 1])
        ll = min(lows[i + 1 - period: i + 1])
        out[i] = -100.0 * (hh - closes[i]) / (hh - ll) if hh != ll else -50.0
    return out


def rate_of_change(closes: List[float], period: int = 10) -> List[float]:
    n = len(closes)
    out = [0.0] * n
    for i in range(n):
        if i < period or closes[i - period] == 0:
            continue
        out[i] = 100.0 * (closes[i] - closes[i - period]) / closes[i - period]
    return out


def obv(closes: List[float], volumes: List[float]) -> List[float]:
    n = len(closes)
    out = [0.0] * n
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def money_flow_index(highs: List[float], lows: List[float], closes: List[float], volumes: List[float], period: int = 14) -> List[float]:
    n = len(closes)
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    raw_flow = [typical[i] * volumes[i] for i in range(n)]
    out = [50.0] * n
    for i in range(n):
        if i + 1 < period + 1:
            continue
        pos_flow = sum(raw_flow[j] for j in range(i - period + 1, i + 1) if typical[j] > typical[j - 1])
        neg_flow = sum(raw_flow[j] for j in range(i - period + 1, i + 1) if typical[j] < typical[j - 1])
        if neg_flow == 0:
            out[i] = 100.0 if pos_flow > 0 else 50.0
        else:
            money_ratio = pos_flow / neg_flow
            out[i] = 100.0 - (100.0 / (1.0 + money_ratio))
    return out


def trix(closes: List[float], period: int = 15) -> List[float]:
    e1 = ema_series(closes, period)
    e2 = ema_series([v if v else closes[i] for i, v in enumerate(e1)], period)
    e3 = ema_series([v if v else e2[i] for i, v in enumerate(e2)], period)
    n = len(closes)
    out = [0.0] * n
    for i in range(1, n):
        if e3[i - 1]:
            out[i] = 100.0 * (e3[i] - e3[i - 1]) / e3[i - 1]
    return out


def vortex_indicator(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Dict[str, List[float]]:
    n = len(closes)
    vm_plus = [0.0] * n
    vm_minus = [0.0] * n
    for i in range(1, n):
        vm_plus[i] = abs(highs[i] - lows[i - 1])
        vm_minus[i] = abs(lows[i] - highs[i - 1])
    tr = true_range(highs, lows, closes)
    vi_plus = [0.0] * n
    vi_minus = [0.0] * n
    for i in range(n):
        if i + 1 < period:
            continue
        sum_tr = sum(tr[i + 1 - period: i + 1])
        if sum_tr == 0:
            continue
        vi_plus[i] = sum(vm_plus[i + 1 - period: i + 1]) / sum_tr
        vi_minus[i] = sum(vm_minus[i + 1 - period: i + 1]) / sum_tr
    return {"plus": vi_plus, "minus": vi_minus}


def awesome_oscillator(highs: List[float], lows: List[float]) -> List[float]:
    midpoint = [(highs[i] + lows[i]) / 2.0 for i in range(len(highs))]
    fast = sma(midpoint, 5)
    slow = sma(midpoint, 34)
    return [f - s for f, s in zip(fast, slow)]


def parabolic_sar(highs: List[float], lows: List[float], af_step: float = 0.02, af_max: float = 0.2) -> List[float]:
    n = len(highs)
    if n == 0:
        return []
    sar = [0.0] * n
    uptrend = True
    ep = highs[0]
    af = af_step
    sar[0] = lows[0]
    for i in range(1, n):
        prev_sar = sar[i - 1]
        new_sar = prev_sar + af * (ep - prev_sar)
        if uptrend:
            new_sar = min(new_sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if lows[i] < new_sar:
                uptrend = False
                new_sar = ep
                ep = lows[i]
                af = af_step
            elif highs[i] > ep:
                ep = highs[i]
                af = min(af + af_step, af_max)
        else:
            new_sar = max(new_sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if highs[i] > new_sar:
                uptrend = True
                new_sar = ep
                ep = highs[i]
                af = af_step
            elif lows[i] < ep:
                ep = lows[i]
                af = min(af + af_step, af_max)
        sar[i] = new_sar
    return sar


def supertrend(highs: List[float], lows: List[float], closes: List[float], period: int = 10, multiplier: float = 3.0) -> Dict[str, List[float]]:
    n = len(closes)
    atr_vals = atr(highs, lows, closes, period)
    hl2 = [(highs[i] + lows[i]) / 2.0 for i in range(n)]
    upper_band = [hl2[i] + multiplier * atr_vals[i] for i in range(n)]
    lower_band = [hl2[i] - multiplier * atr_vals[i] for i in range(n)]
    trend_up = [True] * n
    line = [0.0] * n
    for i in range(n):
        if i == 0 or atr_vals[i] == 0:
            line[i] = lower_band[i]
            continue
        if closes[i - 1] <= line[i - 1]:
            final_upper = min(upper_band[i], upper_band[i - 1]) if upper_band[i - 1] else upper_band[i]
        else:
            final_upper = upper_band[i]
        if closes[i - 1] >= line[i - 1]:
            final_lower = max(lower_band[i], lower_band[i - 1]) if lower_band[i - 1] else lower_band[i]
        else:
            final_lower = lower_band[i]

        if trend_up[i - 1] and closes[i] < final_lower:
            trend_up[i] = False
        elif not trend_up[i - 1] and closes[i] > final_upper:
            trend_up[i] = True
        else:
            trend_up[i] = trend_up[i - 1]
        line[i] = final_lower if trend_up[i] else final_upper
        upper_band[i], lower_band[i] = final_upper, final_lower
    return {"line": line, "uptrend": [1 if t else -1 for t in trend_up]}


def keltner_channel(highs: List[float], lows: List[float], closes: List[float], period: int = 20, atr_mult: float = 2.0) -> Dict[str, List[float]]:
    mid = ema_series(closes, period)
    atr_vals = atr(highs, lows, closes, period)
    upper = [mid[i] + atr_mult * atr_vals[i] if mid[i] else 0.0 for i in range(len(closes))]
    lower = [mid[i] - atr_mult * atr_vals[i] if mid[i] else 0.0 for i in range(len(closes))]
    return {"upper": upper, "mid": mid, "lower": lower}


def ichimoku(highs: List[float], lows: List[float], closes: List[float], tenkan: int = 9, kijun: int = 26, senkou_b: int = 52) -> Dict[str, List[float]]:
    n = len(closes)

    def _mid_channel(period: int) -> List[float]:
        out = [0.0] * n
        for i in range(n):
            if i + 1 < period:
                continue
            out[i] = (max(highs[i + 1 - period: i + 1]) + min(lows[i + 1 - period: i + 1])) / 2.0
        return out

    tenkan_sen = _mid_channel(tenkan)
    kijun_sen = _mid_channel(kijun)
    senkou_a = [(tenkan_sen[i] + kijun_sen[i]) / 2.0 if tenkan_sen[i] and kijun_sen[i] else 0.0 for i in range(n)]
    senkou_b_line = _mid_channel(senkou_b)
    return {"tenkan": tenkan_sen, "kijun": kijun_sen, "senkou_a": senkou_a, "senkou_b": senkou_b_line}


def swing_levels(
    highs: List[float], lows: List[float], closes: List[float],
    lookback: int = 2, max_levels: int = 3,
) -> Dict[str, List[float]]:
    """Real support/resistance via swing highs/lows (a bar whose high/low is
    the extreme of its own `lookback`-bar neighborhood on both sides -- the
    standard fractal-pivot definition, not SMC-specific). Replaces the
    previous approach in forex_engine.py/crypto_trading_agent.py, which
    derived "support/resistance" as an arbitrary fixed percentage offset
    from the 24h high/low (e.g. low * 0.99) -- a real number dressed up as a
    technical level with no actual price-structure behind it.

    Returns up to `max_levels` resistance levels above the last close
    (nearest first) and `max_levels` support levels below it (nearest
    first). Empty lists (not a fabricated guess) if there isn't enough
    history to find a real swing point on either side.
    """
    n = len(closes)
    if n < lookback * 2 + 1:
        return {"support": [], "resistance": []}

    last_close = closes[-1]
    swing_highs: List[float] = []
    swing_lows: List[float] = []
    for i in range(lookback, n - lookback):
        window_highs = highs[i - lookback: i + lookback + 1]
        window_lows = lows[i - lookback: i + lookback + 1]
        if highs[i] == max(window_highs) and window_highs.count(highs[i]) == 1:
            swing_highs.append(highs[i])
        if lows[i] == min(window_lows) and window_lows.count(lows[i]) == 1:
            swing_lows.append(lows[i])

    resistance = sorted({round(h, 2) for h in swing_highs if h > last_close})[:max_levels]
    support = sorted({round(l, 2) for l in swing_lows if l < last_close}, reverse=True)[:max_levels]
    return {"support": support, "resistance": resistance}


def pivot_points(prev_high: float, prev_low: float, prev_close: float) -> Dict[str, float]:
    """Classic floor-trader pivot points from the PRIOR bar's H/L/C."""
    pivot = (prev_high + prev_low + prev_close) / 3.0
    return {
        "pivot": pivot,
        "r1": 2 * pivot - prev_low, "s1": 2 * pivot - prev_high,
        "r2": pivot + (prev_high - prev_low), "s2": pivot - (prev_high - prev_low),
    }


def fibonacci_levels(high: float, low: float) -> Dict[str, float]:
    diff = high - low
    return {
        "0.0": high, "0.236": high - 0.236 * diff, "0.382": high - 0.382 * diff,
        "0.5": high - 0.5 * diff, "0.618": high - 0.618 * diff, "1.0": low,
    }
