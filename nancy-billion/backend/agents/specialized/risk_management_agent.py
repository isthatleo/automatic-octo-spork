"""
Risk Management Agent for Nancy/Billion.
Real quantitative risk analysis -- reuses real_compute.py's actual Monte
Carlo GBM simulation, historical VaR/CVaR, and portfolio risk metrics
(Sharpe/Sortino/max drawdown), the same functions the trading pipeline
already trusts. No fabricated risk numbers.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent


class RiskManagementAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Risk Management Agent", "risk-management")
        self.capabilities.update({
            "description": "Real Monte Carlo simulation, Value-at-Risk, and portfolio risk metrics (Sharpe/Sortino/drawdown)",
            "confidence": 0.85,
            "specializations": ["monte-carlo", "value-at-risk", "portfolio-risk"],
            "tools": ["real_compute.monte_carlo_simulation", "real_compute.value_at_risk"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        from agents.real_compute import monte_carlo_simulation, value_at_risk, conditional_var, portfolio_metrics

        if task_type == "monte_carlo":
            paths = monte_carlo_simulation(
                float(task_data.get("initial", 100)), float(task_data.get("mu", 0.05)),
                float(task_data.get("sigma", 0.2)), int(task_data.get("steps", 252)),
                int(task_data.get("n_paths", 200)),
            )
            finals = [p[-1] for p in paths]
            return {
                "success": True,
                "n_paths": len(paths),
                "mean_final_value": round(sum(finals) / len(finals), 2),
                "min_final_value": round(min(finals), 2),
                "max_final_value": round(max(finals), 2),
            }
        if task_type == "value_at_risk":
            returns: List[float] = task_data.get("returns", [])
            if not returns:
                return {"success": False, "error": "returns (a list of period returns) is required"}
            confidence = float(task_data.get("confidence", 0.95))
            return {
                "success": True,
                "value_at_risk": round(value_at_risk(returns, confidence), 6),
                "conditional_var": round(conditional_var(returns, confidence), 6),
                "confidence": confidence,
            }
        if task_type == "portfolio_risk":
            returns = task_data.get("returns", [])
            if not returns:
                return {"success": False, "error": "returns (a list of period returns) is required"}
            metrics = portfolio_metrics(returns, float(task_data.get("risk_free_rate", 0.02)))
            return {"success": True, **metrics}
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I run real Monte Carlo simulations, Value-at-Risk, and portfolio risk metrics from real return series."
        )}
