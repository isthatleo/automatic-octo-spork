"""
Mining Profitability Agent for Nancy/Billion.

An HONEST calculator, not a miner: real Bitcoin network difficulty/hashrate/
block-height (blockchain.info's free, keyless "simple query" API) and a
real current BTC price (trading/crypto_data.py's CoinGecko wrapper) plugged
into the standard mining-profitability formula, against a real electricity
cost the user supplies. This exists specifically because actually mining
Bitcoin on general-purpose CPU/GPU hardware is guaranteed unprofitable
against real ASIC-dominated network hashrate -- rather than pretending
otherwise (or running actual mining software that would just burn
electricity for no return), this tells the user the real, honest number
for whatever hardware they're asking about.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .base_specialized_agent import SpecializedAgent

BLOCKS_PER_DAY = 144.0  # ~10 min/block average, real Bitcoin protocol target
HALVING_INTERVAL_BLOCKS = 210_000
INITIAL_BLOCK_REWARD_BTC = 50.0


class MiningProfitabilityAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Mining Profitability Agent", "mining-profitability")
        self.capabilities.update({
            "description": (
                "Honest Bitcoin mining profitability calculator using real network difficulty/hashrate "
                "and real BTC price -- tells you the truth, including when the answer is 'this loses money'"
            ),
            "confidence": 0.8,
            "specializations": ["mining-economics", "break-even-analysis"],
            "tools": ["blockchain.info", "coingecko"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "calculate":
            return await self._calculate(
                float(task_data.get("hash_rate_th", 0)),
                float(task_data.get("power_watts", 0)),
                float(task_data.get("electricity_cost_per_kwh", 0.12)),
            )
        if task_type == "status":
            return {"success": True, "status": "ready", "coin": "BTC only -- real difficulty/hashrate data source is BTC-specific"}
        return await self._general(task_data)

    async def _fetch_network_stats(self) -> Optional[Dict[str, float]]:
        import asyncio
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                difficulty_resp, hashrate_resp, height_resp = await asyncio.gather(
                    client.get("https://blockchain.info/q/getdifficulty"),
                    client.get("https://blockchain.info/q/hashrate"),
                    client.get("https://blockchain.info/q/getblockcount"),
                )
            return {
                "difficulty": float(difficulty_resp.text),
                "network_hashrate_ghs": float(hashrate_resp.text),
                "block_height": float(height_resp.text),
            }
        except Exception:
            return None

    async def _calculate(self, hash_rate_th: float, power_watts: float, electricity_cost_per_kwh: float) -> Dict[str, Any]:
        if hash_rate_th <= 0 or power_watts <= 0:
            return {"success": False, "error": "hash_rate_th and power_watts must both be positive real numbers for your hardware"}

        stats = await self._fetch_network_stats()
        if stats is None:
            return {"success": False, "error": "Could not reach blockchain.info for real network stats -- try again shortly"}

        from trading.crypto_data import crypto_data
        btc_snapshot = await crypto_data.get_price("BTC")
        if btc_snapshot is None:
            return {"success": False, "error": "Could not fetch a real current BTC price"}

        network_hashrate_hs = stats["network_hashrate_ghs"] * 1e9
        halvings = int(stats["block_height"] // HALVING_INTERVAL_BLOCKS)
        block_reward_btc = INITIAL_BLOCK_REWARD_BTC / (2 ** halvings)

        user_hashrate_hs = hash_rate_th * 1e12
        network_share = user_hashrate_hs / network_hashrate_hs
        expected_btc_per_day = network_share * block_reward_btc * BLOCKS_PER_DAY
        revenue_usd_per_day = expected_btc_per_day * btc_snapshot.price_usd
        cost_usd_per_day = (power_watts / 1000.0) * 24.0 * electricity_cost_per_kwh
        profit_usd_per_day = revenue_usd_per_day - cost_usd_per_day

        return {
            "success": True,
            "inputs": {"hash_rate_th": hash_rate_th, "power_watts": power_watts, "electricity_cost_per_kwh": electricity_cost_per_kwh},
            "real_network_data": {
                "btc_price_usd": btc_snapshot.price_usd,
                "network_hashrate_ths": round(network_hashrate_hs / 1e12, 1),
                "current_block_reward_btc": block_reward_btc,
                "block_height": int(stats["block_height"]),
            },
            "expected_btc_per_day": round(expected_btc_per_day, 8),
            "revenue_usd_per_day": round(revenue_usd_per_day, 2),
            "electricity_cost_usd_per_day": round(cost_usd_per_day, 2),
            "net_profit_usd_per_day": round(profit_usd_per_day, 2),
            "verdict": "PROFITABLE" if profit_usd_per_day > 0 else "LOSES MONEY",
            "note": (
                "Real network difficulty/hashrate and real BTC price -- ignores hardware purchase cost, "
                "pool fees, and cooling, all of which make real-world profit lower than this."
            ),
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "Give me your hardware's hash_rate_th, power_watts, and electricity_cost_per_kwh and I'll "
            "calculate a real, honest daily profit/loss against real current network difficulty and BTC price."
        )}
