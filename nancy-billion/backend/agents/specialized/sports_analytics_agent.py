"""
Sports Analytics Agent for Nancy/Billion.
Real Elo rating updates and win-probability calculations -- the actual
formulas used by chess federations and most modern sports rating systems,
not fabricated numbers.
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


class SportsAnalyticsAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Sports Analytics Agent", "sports-analytics")
        self.capabilities.update({
            "description": "Real Elo rating updates and win-probability calculations from real ratings",
            "confidence": 0.8,
            "specializations": ["elo-ratings", "win-probability"],
            "tools": ["elo-formula"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "elo_update":
            return self._elo_update(
                float(task_data.get("rating_a", 1500)), float(task_data.get("rating_b", 1500)),
                float(task_data.get("score_a", 0.5)), float(task_data.get("k_factor", 32)),
            )
        if task_type == "win_probability":
            return self._win_probability(float(task_data.get("rating_a", 1500)), float(task_data.get("rating_b", 1500)))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    @staticmethod
    def _expected(rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

    def _win_probability(self, rating_a: float, rating_b: float) -> Dict[str, Any]:
        p = self._expected(rating_a, rating_b)
        return {"success": True, "rating_a": rating_a, "rating_b": rating_b, "win_probability_a": round(p, 4), "win_probability_b": round(1 - p, 4)}

    def _elo_update(self, rating_a: float, rating_b: float, score_a: float, k: float) -> Dict[str, Any]:
        if score_a not in (0.0, 0.5, 1.0):
            return {"success": False, "error": "score_a must be 0 (loss), 0.5 (draw), or 1 (win)"}
        expected_a = self._expected(rating_a, rating_b)
        new_a = rating_a + k * (score_a - expected_a)
        new_b = rating_b + k * ((1 - score_a) - (1 - expected_a))
        return {
            "success": True,
            "new_rating_a": round(new_a, 1), "new_rating_b": round(new_b, 1),
            "expected_score_a": round(expected_a, 4), "rating_change_a": round(new_a - rating_a, 1),
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I compute real Elo rating updates and win probabilities from actual ratings."
        )}
