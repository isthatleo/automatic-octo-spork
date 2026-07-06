"""
Strategic Planning Agent for Nancy Billion
Long-term planning, resource allocation, and strategic decision support.
"""
from typing import Dict, Any, Optional, List
import logging
import time
import math

logger = logging.getLogger(__name__)


class StrategicPlanningAgent:
    """Strategic Planning Agent - develops and evaluates strategic plans"""

    def __init__(self, settings):
        self.settings = settings
        self.name = "Strategic Planning Agent"
        self.domain = "strategic-planning"
        self._initialized = False
        self._plans: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        logger.info("Initializing Strategic Planning Agent")
        self._initialized = True

    async def create_plan(self, goal: str, constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()
        c = constraints or {}
        horizon_days = c.get("horizon_days", 90)
        budget = c.get("budget", 100000)
        phases = []
        n_phases = max(2, min(6, horizon_days // 15))
        phase_duration = horizon_days / n_phases
        for i in range(n_phases):
            progress = (i + 1) / n_phases
            phases.append({
                "phase": i + 1,
                "name": f"Phase {i + 1}: {self._phase_name(progress)}",
                "duration_days": round(phase_duration, 1),
                "budget_allocation": round(budget * self._budget_share(i, n_phases), 2),
                "milestones": [f"Milestone {j + 1} for phase {i + 1}" for j in range(max(1, n_phases // 2))]
            })
        plan_id = f"plan_{int(time.time())}_{abs(hash(goal)) % 10000:04d}"
        plan = {
            "id": plan_id,
            "goal": goal,
            "horizon_days": horizon_days,
            "total_budget": budget,
            "phases": phases,
            "estimated_effort_person_days": round(horizon_days * max(1, n_phases // 2) * 0.7, 1),
            "risk_factors": ["Market volatility", "Resource constraints", "Technical debt", "Dependency delays"][:max(1, n_phases // 2)],
            "success_criteria": [f"Criterion {i + 1}" for i in range(3)],
            "timestamp": time.time()
        }
        self._plans[plan_id] = plan
        return plan

    async def evaluate_plan(self, plan_id: str) -> Dict[str, Any]:
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan {plan_id} not found", "success": False}
        n_phases = len(plan.get("phases", []))
        feasibility = min(1.0, max(0.2, 1.0 - (0.1 * n_phases) + 0.3))
        risk_score = min(1.0, max(0.1, 0.3 + 0.1 * len(plan.get("risk_factors", []))))
        resource_efficiency = min(1.0, max(0.3, 0.7 - 0.05 * (len(plan.get("phases", [])) - 2)))
        return {
            "plan_id": plan_id,
            "feasibility_score": round(feasibility, 4),
            "risk_score": round(risk_score, 4),
            "resource_efficiency": round(resource_efficiency, 4),
            "overall_score": round((feasibility + (1 - risk_score) + resource_efficiency) / 3, 4),
            "recommendations": [
                "Reduce phase count to improve focus" if n_phases > 4 else "Phase structure is appropriate",
                "Allocate additional resources to critical path items",
                "Establish clear KPIs for each phase"
            ],
            "timestamp": time.time()
        }

    async def optimize_allocation(self, budget: float, priorities: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_weight = sum(p.get("priority", 1) for p in priorities) + 1e-12
        allocations = []
        for p in priorities:
            weight = p.get("priority", 1) / total_weight
            allocations.append({
                "area": p.get("area", "general"),
                "allocated": round(budget * weight, 2),
                "percentage": round(weight * 100, 2),
                "expected_roi": round(weight * (1 + p.get("expected_return", 0.1)), 4)
            })
        return {
            "total_budget": budget,
            "allocations": allocations,
            "timestamp": time.time()
        }

    def _phase_name(self, progress: float) -> str:
        if progress < 0.2:
            return "Discovery & Research"
        elif progress < 0.4:
            return "Planning & Design"
        elif progress < 0.6:
            return "Development & Implementation"
        elif progress < 0.8:
            return "Testing & Validation"
        return "Deployment & Monitoring"

    def _budget_share(self, phase_idx: int, total_phases: int) -> float:
        weights = [0.15, 0.25, 0.30, 0.20, 0.07, 0.03]
        if phase_idx < len(weights):
            return weights[phase_idx] / sum(weights[:total_phases])
        return 0.05

    async def shutdown(self):
        logger.info("Shutting down Strategic Planning Agent")
        self._initialized = False
