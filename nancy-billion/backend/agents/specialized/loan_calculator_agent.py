"""
Loan Calculator Agent for Nancy/Billion.
Real amortization math (the standard fixed-rate loan payment formula) --
an exact monthly payment and a real month-by-month schedule, not a rounded
guess.
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


class LoanCalculatorAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Loan Calculator Agent", "loan-calculator")
        self.capabilities.update({
            "description": "Real fixed-rate loan/mortgage amortization: exact monthly payment, total interest, and a real payment schedule",
            "confidence": 0.85,
            "specializations": ["amortization", "mortgage-math", "loan-payoff"],
            "tools": ["standard-amortization-formula"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "amortize":
            return self._amortize(
                float(task_data.get("principal", 0)),
                float(task_data.get("annual_rate_pct", 0)),
                int(task_data.get("term_years", 30)),
                bool(task_data.get("include_schedule", False)),
            )
        if task_type == "extra_payment_payoff":
            return self._extra_payment_payoff(
                float(task_data.get("principal", 0)),
                float(task_data.get("annual_rate_pct", 0)),
                int(task_data.get("term_years", 30)),
                float(task_data.get("extra_monthly_payment", 0)),
            )
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    @staticmethod
    def _monthly_payment(principal: float, annual_rate_pct: float, term_years: int) -> float:
        n = term_years * 12
        if annual_rate_pct == 0:
            return principal / n
        r = (annual_rate_pct / 100) / 12
        return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)

    def _amortize(self, principal: float, annual_rate_pct: float, term_years: int, include_schedule: bool) -> Dict[str, Any]:
        if principal <= 0 or term_years <= 0:
            return {"success": False, "error": "principal must be positive and term_years must be a positive integer"}
        payment = self._monthly_payment(principal, annual_rate_pct, term_years)
        n = term_years * 12
        r = (annual_rate_pct / 100) / 12
        balance = principal
        schedule = []
        total_interest = 0.0
        for month in range(1, n + 1):
            interest = balance * r
            principal_paid = payment - interest
            balance = max(0.0, balance - principal_paid)
            total_interest += interest
            if include_schedule:
                schedule.append({"month": month, "payment": round(payment, 2), "principal": round(principal_paid, 2), "interest": round(interest, 2), "balance": round(balance, 2)})

        result = {
            "success": True,
            "principal": principal, "annual_rate_pct": annual_rate_pct, "term_years": term_years,
            "monthly_payment": round(payment, 2),
            "total_paid": round(payment * n, 2),
            "total_interest": round(total_interest, 2),
        }
        if include_schedule:
            result["schedule"] = schedule
        return result

    def _extra_payment_payoff(self, principal: float, annual_rate_pct: float, term_years: int, extra_monthly: float) -> Dict[str, Any]:
        if principal <= 0 or term_years <= 0:
            return {"success": False, "error": "principal must be positive and term_years must be a positive integer"}
        base_payment = self._monthly_payment(principal, annual_rate_pct, term_years)
        payment = base_payment + max(0.0, extra_monthly)
        r = (annual_rate_pct / 100) / 12
        balance = principal
        months = 0
        total_interest = 0.0
        while balance > 0.01 and months < term_years * 12 * 2:  # real safety cap, never an infinite loop
            interest = balance * r
            principal_paid = min(balance, payment - interest)
            balance -= principal_paid
            total_interest += interest
            months += 1

        original = self._amortize(principal, annual_rate_pct, term_years, False)
        return {
            "success": True,
            "base_monthly_payment": round(base_payment, 2),
            "with_extra_monthly_payment": round(payment, 2),
            "months_to_payoff": months,
            "years_to_payoff": round(months / 12, 2),
            "total_interest_paid": round(total_interest, 2),
            "interest_saved_vs_original": round(original["total_interest"] - total_interest, 2),
            "months_saved": term_years * 12 - months,
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I calculate real loan amortization -- give me a principal, rate, and term and I'll give you the "
            "exact monthly payment, total interest, and (if you want) the full real schedule."
        )}
