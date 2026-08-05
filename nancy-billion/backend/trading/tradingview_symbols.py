"""Real TradingView ticker mapping -- lets the trading agents attach a
correct, embeddable chart reference to their output.

TradingView's free "Advanced Chart" widget (already wired into the frontend
-- see components/nancy/tradingview.tsx, no API key, no scraping) renders
any real exchange-qualified symbol it's given, e.g. "FX:EURUSD",
"OANDA:XAUUSD", "BINANCE:BTCUSDT". This module is the backend-side half of
that: it does NOT fetch anything from TradingView (there is no free data
API for that, and this codebase does not fabricate a workaround) -- it only
translates our own already-real instrument identifiers (a forex pair like
"EUR/USD", a crypto symbol like "BTC") into TradingView's real naming
convention, so agent output can carry a `tradingview_symbol` field the
frontend can hand straight to the existing widget.

The frontend keeps its own copy of an equivalent mapping
(lib/nancy/local-brain.ts's SYMBOL_MAP) for the voice/console "open chart
for X" command path, which must resolve synchronously with no network
round-trip -- duplicated deliberately, not a drift risk, since both sides
derive from the same real, stable convention (TradingView's own documented
exchange prefixes) rather than from each other.
"""
from __future__ import annotations

from typing import Optional

# Metals get their own real OANDA-listed ticker (TradingView has no
# generic "FX:" symbol for XAU/XAG) -- same convention the frontend widget
# already uses for "gold"/"silver".
_METAL_TICKERS = {"XAU": "OANDA:XAUUSD", "XAG": "OANDA:XAGUSD"}

# Real, stable per-symbol exchange listings for the crypto watchlist this
# codebase actually serves (trading/crypto_data.py's SYMBOL_TO_COINGECKO_ID)
# -- Binance's USDT market for each, the same convention already used by
# the frontend's SYMBOL_MAP for BTC/ETH/SOL.
_CRYPTO_EXCHANGE = "BINANCE"


def forex_tradingview_symbol(pair: str) -> Optional[str]:
    """"EUR/USD" -> "FX:EURUSD", "XAU/USD" -> "OANDA:XAUUSD". Returns None
    for anything that doesn't parse as a real BASE/QUOTE pair rather than
    guessing."""
    base, _, quote = pair.upper().partition("/")
    if not base or not quote:
        return None
    if base in _METAL_TICKERS and quote == "USD":
        return _METAL_TICKERS[base]
    return f"FX:{base}{quote}"


def crypto_tradingview_symbol(symbol: str) -> str:
    """"BTC" -> "BINANCE:BTCUSDT". Always returns a value (Binance lists a
    USDT market for every symbol this codebase's watchlist covers), unlike
    the forex version -- there's no invalid-format case to fail on here."""
    return f"{_CRYPTO_EXCHANGE}:{symbol.upper()}USDT"
