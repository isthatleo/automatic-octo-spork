"""Real crypto market data via CoinGecko's free, keyless public API --
same honesty conventions as forex_engine.py's ForexDataAggregator: real
prices, real 24h change/volume/market-cap, cached briefly to stay well
under CoinGecko's free-tier rate limit (10-30 req/min depending on load).

Honesty note: `get_historical`'s /market_chart endpoint returns PRICE
POINTS, not OHLC bars, exactly like Frankfurter's forex data -- open is
synthesized as the prior point's close (open==prior close, high/low==
max/min(open, close)), never fabricated. Real, just not exchange-grade
OHLC. No order execution is wired to this -- data only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# A curated, real mapping for the coins someone's actually likely to ask
# about -- an unmapped symbol fails honestly (get_price returns None)
# rather than guessing at a CoinGecko id that might not exist.
SYMBOL_TO_COINGECKO_ID: Dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "ADA": "cardano",
    "DOT": "polkadot", "DOGE": "dogecoin", "XRP": "ripple", "MATIC": "matic-network",
    "LTC": "litecoin", "LINK": "chainlink", "AVAX": "avalanche-2", "BNB": "binancecoin",
    "USDT": "tether", "USDC": "usd-coin", "SHIB": "shiba-inu", "TRX": "tron",
    "UNI": "uniswap", "ATOM": "cosmos", "XLM": "stellar", "NEAR": "near",
}


@dataclass
class CryptoSnapshot:
    symbol: str
    price_usd: float
    change_24h_pct: float
    volume_24h_usd: float
    market_cap_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class CryptoDataAggregator:
    def __init__(self) -> None:
        self.cache: Dict[str, CryptoSnapshot] = {}
        self.last_update: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=2)

    async def get_price(self, symbol: str) -> Optional[CryptoSnapshot]:
        symbol = symbol.upper()
        cached = self.cache.get(symbol)
        if cached and datetime.now() - self.last_update.get(symbol, datetime.min) < self._cache_ttl:
            return cached

        coin_id = SYMBOL_TO_COINGECKO_ID.get(symbol)
        if coin_id is None:
            logger.error(f"No CoinGecko id mapping for symbol {symbol!r}")
            return None

        import aiohttp
        try:
            # Accept-Encoding: identity -- see forex_engine.py's identical
            # fix; confirmed live this environment can fail to decode a
            # brotli-compressed response from at least two other real APIs.
            async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
                async with session.get(
                    f"{COINGECKO_BASE_URL}/simple/price",
                    params={
                        "ids": coin_id, "vs_currencies": "usd",
                        "include_24hr_change": "true", "include_24hr_vol": "true",
                        "include_market_cap": "true",
                    },
                    timeout=10,
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"CoinGecko price error for {symbol} ({coin_id}): HTTP {resp.status}")
                        return None
                    data = await resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch real crypto price for {symbol}: {e}")
            return None

        entry = data.get(coin_id)
        if not entry or "usd" not in entry:
            logger.error(f"CoinGecko response missing price for {symbol} ({coin_id}): {data}")
            return None

        snapshot = CryptoSnapshot(
            symbol=symbol,
            price_usd=entry["usd"],
            change_24h_pct=round(entry.get("usd_24h_change", 0.0) or 0.0, 4),
            volume_24h_usd=entry.get("usd_24h_vol", 0.0) or 0.0,
            market_cap_usd=entry.get("usd_market_cap", 0.0) or 0.0,
        )
        self.cache[symbol] = snapshot
        self.last_update[symbol] = datetime.now()
        return snapshot

    async def get_historical(self, symbol: str, days: int = 30) -> List[Dict[str, Any]]:
        """Real historical price points from CoinGecko's /market_chart
        endpoint, reshaped into daily OHLC-shaped candles (see module
        docstring for the honest open==prior-close caveat)."""
        symbol = symbol.upper()
        coin_id = SYMBOL_TO_COINGECKO_ID.get(symbol)
        if coin_id is None:
            logger.error(f"No CoinGecko id mapping for symbol {symbol!r}")
            return []

        import aiohttp
        try:
            # Accept-Encoding: identity -- see forex_engine.py's identical
            # fix; confirmed live this environment can fail to decode a
            # brotli-compressed response from at least two other real APIs.
            async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
                async with session.get(
                    f"{COINGECKO_BASE_URL}/coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": str(days), "interval": "daily"},
                    timeout=15,
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"CoinGecko historical error for {symbol} ({coin_id}): HTTP {resp.status}")
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch real historical crypto data for {symbol}: {e}")
            return []

        prices = data.get("prices", [])
        volumes = {int(v[0]): v[1] for v in data.get("total_volumes", [])}
        candles: List[Dict[str, Any]] = []
        prev_close: Optional[float] = None
        for ts_ms, close in prices:
            open_ = prev_close if prev_close is not None else close
            candles.append({
                "timestamp": datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d"),
                "open": open_,
                "high": max(open_, close),
                "low": min(open_, close),
                "close": close,
                "volume": volumes.get(int(ts_ms), 0.0),
            })
            prev_close = close
        return candles


crypto_data = CryptoDataAggregator()
