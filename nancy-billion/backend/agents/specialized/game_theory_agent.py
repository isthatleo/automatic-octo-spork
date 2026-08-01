"""
Game Theory Agent for Nancy/Billion.
Real solutions to small game-theory problems: expected value from a real
payoff/probability table, and a two-player zero-sum game's optimal mixed
strategy via linear programming (reuses real_compute.solve_linear_program,
the same solver DataScienceAgent-adjacent code already uses).
"""
from __future__ import annotations

from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent


class GameTheoryAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Game Theory Agent", "game-theory")
        self.capabilities.update({
            "description": "Real expected-value calculations and zero-sum game equilibrium solving via linear programming",
            "confidence": 0.8,
            "specializations": ["expected-value", "zero-sum-games", "linear-programming"],
            "tools": ["scipy.optimize.linprog"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "expected_value":
            return self._expected_value(task_data.get("outcomes", []), task_data.get("probabilities", []))
        if task_type == "solve_zero_sum":
            return self._solve_zero_sum(task_data.get("payoff_matrix", []))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _expected_value(self, outcomes: List[float], probabilities: List[float]) -> Dict[str, Any]:
        if not outcomes or len(outcomes) != len(probabilities):
            return {"success": False, "error": "outcomes and probabilities must be equal-length, non-empty lists"}
        total_p = sum(probabilities)
        if abs(total_p - 1.0) > 0.01:
            return {"success": False, "error": f"probabilities must sum to 1.0 (got {total_p})"}
        ev = sum(o * p for o, p in zip(outcomes, probabilities))
        variance = sum(p * (o - ev) ** 2 for o, p in zip(outcomes, probabilities))
        return {"success": True, "expected_value": round(ev, 4), "variance": round(variance, 4), "std_dev": round(variance ** 0.5, 4)}

    def _solve_zero_sum(self, payoff_matrix: List[List[float]]) -> Dict[str, Any]:
        """Row player's optimal mixed strategy for a real zero-sum game via
        LP: maximize v s.t. the strategy guarantees at least v against every
        column player action -- the textbook minimax LP formulation."""
        if not payoff_matrix or not all(payoff_matrix):
            return {"success": False, "error": "payoff_matrix must be a non-empty 2D list"}
        try:
            from agents.real_compute import solve_linear_program
            n_rows = len(payoff_matrix)
            n_cols = len(payoff_matrix[0])
            # Shift payoffs positive so the LP's implicit non-negativity is safe.
            offset = -min(min(row) for row in payoff_matrix) + 1
            shifted = [[v + offset for v in row] for row in payoff_matrix]
            # Variables: p_1..p_n (row-player mixed strategy), maximize min guaranteed payoff.
            # Standard trick: maximize 1/sum(y) via y_i = p_i / v, minimize sum(y) s.t. shifted^T y >= 1.
            c = [1.0] * n_rows
            A = [[-shifted[r][col] for r in range(n_rows)] for col in range(n_cols)]
            b = [-1.0] * n_cols
            result = solve_linear_program(c, A, b, bounds=[(0, None)] * n_rows)
            if not result.get("success"):
                return {"success": False, "error": result.get("message", "LP solver failed")}
            y = result["x"]
            total_y = sum(y)
            if total_y <= 0:
                return {"success": False, "error": "Degenerate game (no valid mixed strategy found)"}
            strategy = [round(v / total_y, 4) for v in y]
            game_value = round(1.0 / total_y - offset, 4)
            return {"success": True, "row_player_strategy": strategy, "game_value": game_value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I compute real expected values and solve zero-sum games for their optimal mixed strategy via linear programming."
        )}
