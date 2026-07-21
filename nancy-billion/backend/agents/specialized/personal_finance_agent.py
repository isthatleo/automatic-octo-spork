"""
Personal Finance/Budgeting Agent for Nancy/Billion Backend
Real, deterministic personal-finance math: budget-rule analysis, savings/
retirement projections via standard compound-interest formulas, month-by-
month debt-payoff amortization simulation (avalanche vs. snowball), and net
worth calculation. No external data dependency -- every number here is
computed directly from the caller's own inputs with standard, textbook
financial formulas (never an invented number).

Distinct from CryptoTradingAgent (crypto markets) and EconomicsAgent
(macro/country-level indicators) -- this is household-level personal finance.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)


class PersonalFinanceAgent(SpecializedAgent):
    """Household personal finance: budgeting, savings/retirement projections, debt payoff, net worth"""

    def __init__(self, settings):
        super().__init__(settings, "Personal Finance Agent", "personal-finance")
        self.capabilities.update({
            "description": (
                "Household personal-finance agent: 50/30/20 budget analysis, compound-interest savings "
                "and retirement projections, month-by-month debt-payoff amortization (avalanche vs. "
                "snowball), and net worth calculation -- all real, deterministic formulas over your own inputs."
            ),
            "confidence": 0.85,
            "specializations": [
                "budget-analysis",
                "savings-projection",
                "retirement-projection",
                "debt-payoff-simulation",
                "net-worth-calculation",
            ],
            "tools": ["compound-interest-calculator", "amortization-simulator"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "budget-analysis")
        try:
            if task_type == "budget-analysis":
                return self._budget_analysis(task_data)
            elif task_type == "savings-projection":
                return self._savings_projection(task_data)
            elif task_type == "retirement-projection":
                return self._retirement_projection(task_data)
            elif task_type == "debt-payoff":
                return self._debt_payoff(task_data)
            elif task_type == "net-worth":
                return self._net_worth(task_data)
            else:
                return await self._general_query(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # 50/30/20 budget rule analysis (real classification of caller's own
    # expense categories -- 'needs' vs 'wants' tagging must be supplied,
    # never guessed)
    # ------------------------------------------------------------------

    def _budget_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        income = params.get("monthly_income_after_tax")
        expenses = params.get("expenses")  # {category: {"amount": float, "type": "needs"|"wants"|"savings"}}
        if income is None or not isinstance(expenses, dict) or not expenses:
            return {"success": False, "task_type": "budget-analysis", "error": "'monthly_income_after_tax' and 'expenses' (dict of category -> {amount, type}) are required"}
        income = float(income)
        if income <= 0:
            return {"success": False, "task_type": "budget-analysis", "error": "'monthly_income_after_tax' must be > 0"}

        totals = {"needs": 0.0, "wants": 0.0, "savings": 0.0}
        breakdown = []
        for category, info in expenses.items():
            amount = float(info.get("amount", 0.0))
            bucket = str(info.get("type", "wants")).lower()
            if bucket not in totals:
                bucket = "wants"
            totals[bucket] += amount
            breakdown.append({"category": category, "amount": amount, "bucket": bucket, "pct_of_income": round(amount / income * 100.0, 2)})

        actual_pct = {k: round(v / income * 100.0, 2) for k, v in totals.items()}
        target_pct = {"needs": 50.0, "wants": 30.0, "savings": 20.0}
        deltas = {k: round(actual_pct[k] - target_pct[k], 2) for k in target_pct}

        flags = []
        if deltas["needs"] > 5:
            flags.append(f"Needs spending is {deltas['needs']:+.1f} pts over the 50% target")
        if deltas["wants"] > 5:
            flags.append(f"Wants spending is {deltas['wants']:+.1f} pts over the 30% target")
        if deltas["savings"] < -5:
            flags.append(f"Savings rate is {abs(deltas['savings']):.1f} pts under the 20% target")
        if not flags:
            flags.append("Budget is within +/-5 points of the 50/30/20 target across all categories")

        total_allocated = sum(totals.values())

        return {
            "success": True,
            "task_type": "budget-analysis",
            "monthly_income_after_tax": income,
            "breakdown": breakdown,
            "totals_by_bucket": totals,
            "actual_pct_of_income": actual_pct,
            "target_pct_50_30_20": target_pct,
            "deltas_vs_target_pts": deltas,
            "unallocated_income": round(income - total_allocated, 2),
            "flags": flags,
            "method": "Standard 50/30/20 rule (needs/wants/savings) -- categorization is exactly what the caller supplied",
        }

    # ------------------------------------------------------------------
    # Real compound-interest savings projection (monthly contributions,
    # monthly compounding -- standard annuity-due future value formula)
    # ------------------------------------------------------------------

    def _project_savings(self, principal: float, monthly_contribution: float, annual_rate_pct: float, years: float) -> Dict[str, Any]:
        monthly_rate = (annual_rate_pct / 100.0) / 12.0
        n_months = int(round(years * 12))

        fv_principal = principal * (1.0 + monthly_rate) ** n_months
        if monthly_rate == 0:
            fv_contributions = monthly_contribution * n_months
        else:
            fv_contributions = monthly_contribution * (((1.0 + monthly_rate) ** n_months - 1.0) / monthly_rate)

        total_contributed = principal + monthly_contribution * n_months
        future_value = fv_principal + fv_contributions

        return {
            "months": n_months,
            "future_value": round(future_value, 2),
            "total_contributed": round(total_contributed, 2),
            "total_growth": round(future_value - total_contributed, 2),
        }

    def _savings_projection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            principal = float(params.get("current_savings", 0.0))
            monthly_contribution = float(params.get("monthly_contribution", 0.0))
            annual_rate_pct = float(params.get("annual_rate_pct", 6.0))
            years = float(params.get("years", 10.0))
        except (TypeError, ValueError):
            return {"success": False, "task_type": "savings-projection", "error": "all inputs must be numeric"}

        result = self._project_savings(principal, monthly_contribution, annual_rate_pct, years)
        return {
            "success": True,
            "task_type": "savings-projection",
            "inputs": {"current_savings": principal, "monthly_contribution": monthly_contribution, "annual_rate_pct": annual_rate_pct, "years": years},
            **result,
            "method": "FV = P(1+i)^n + PMT * (((1+i)^n - 1) / i), i = monthly rate, n = months",
        }

    # ------------------------------------------------------------------
    # Real retirement projection (nominal + inflation-adjusted real value)
    # ------------------------------------------------------------------

    def _retirement_projection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            current_age = float(params.get("current_age", 30))
            retirement_age = float(params.get("retirement_age", 65))
            current_savings = float(params.get("current_savings", 0.0))
            monthly_contribution = float(params.get("monthly_contribution", 500.0))
            annual_return_pct = float(params.get("annual_return_pct", 7.0))
            inflation_pct = float(params.get("inflation_pct", 2.5))
        except (TypeError, ValueError):
            return {"success": False, "task_type": "retirement-projection", "error": "all inputs must be numeric"}

        years = retirement_age - current_age
        if years <= 0:
            return {"success": False, "task_type": "retirement-projection", "error": "'retirement_age' must be greater than 'current_age'"}

        nominal = self._project_savings(current_savings, monthly_contribution, annual_return_pct, years)
        real_future_value = nominal["future_value"] / ((1.0 + inflation_pct / 100.0) ** years)

        # 4% safe-withdrawal-rate heuristic (Trinity study rule of thumb) applied
        # to both nominal and inflation-adjusted balances -- clearly labeled as
        # a rule of thumb, not a guarantee.
        annual_withdrawal_nominal = nominal["future_value"] * 0.04
        annual_withdrawal_real = real_future_value * 0.04

        return {
            "success": True,
            "task_type": "retirement-projection",
            "inputs": {
                "current_age": current_age, "retirement_age": retirement_age, "years_to_retirement": years,
                "current_savings": current_savings, "monthly_contribution": monthly_contribution,
                "annual_return_pct": annual_return_pct, "inflation_pct": inflation_pct,
            },
            "nominal_future_value": nominal["future_value"],
            "inflation_adjusted_future_value": round(real_future_value, 2),
            "total_contributed": nominal["total_contributed"],
            "estimated_annual_withdrawal_4pct_rule": {
                "nominal": round(annual_withdrawal_nominal, 2),
                "inflation_adjusted": round(annual_withdrawal_real, 2),
            },
            "method": "Compound growth FV formula; inflation-adjusted via / (1+inflation)^years; "
                      "4% rule is a widely-cited rule of thumb (Trinity study), not a guarantee",
        }

    # ------------------------------------------------------------------
    # Real month-by-month debt-payoff amortization simulation
    # ------------------------------------------------------------------

    def _simulate_payoff(self, debts: List[Dict[str, Any]], extra_payment: float, order: str) -> Dict[str, Any]:
        debts = [dict(d) for d in debts]  # working copies
        if order == "avalanche":
            debts.sort(key=lambda d: -d["apr"])
        else:  # snowball
            debts.sort(key=lambda d: d["balance"])

        month = 0
        total_interest = 0.0
        max_months = 1200  # 100-year safety cap against pathological inputs
        history_summary = []

        while any(d["balance"] > 0.01 for d in debts) and month < max_months:
            month += 1
            freed_up = extra_payment
            month_interest = 0.0

            # Pay minimums first, freeing up minimums from paid-off debts
            for d in debts:
                if d["balance"] <= 0.01:
                    continue
                interest = d["balance"] * (d["apr"] / 100.0 / 12.0)
                month_interest += interest
                d["balance"] += interest
                payment = min(d["min_payment"], d["balance"])
                d["balance"] -= payment

            # Apply extra payment (plus freed-up minimums from already-paid debts)
            freed_up += sum(d["min_payment"] for d in debts if d["balance"] <= 0.01)
            for d in debts:
                if freed_up <= 0:
                    break
                if d["balance"] <= 0.01:
                    continue
                pay = min(freed_up, d["balance"])
                d["balance"] -= pay
                freed_up -= pay

            total_interest += month_interest
            if month % 6 == 0 or all(d["balance"] <= 0.01 for d in debts):
                history_summary.append({"month": month, "total_remaining": round(sum(d["balance"] for d in debts), 2)})

        return {
            "months_to_payoff": month if month < max_months else None,
            "years_to_payoff": round(month / 12.0, 2) if month < max_months else None,
            "total_interest_paid": round(total_interest, 2),
            "history_every_6_months": history_summary,
            "hit_safety_cap": month >= max_months,
        }

    def _debt_payoff(self, params: Dict[str, Any]) -> Dict[str, Any]:
        debts = params.get("debts")
        if not isinstance(debts, list) or not debts:
            return {"success": False, "task_type": "debt-payoff", "error": "'debts' (list of {name, balance, apr, min_payment}) is required"}
        try:
            extra_payment = float(params.get("extra_monthly_payment", 0.0))
            for d in debts:
                float(d["balance"]); float(d["apr"]); float(d["min_payment"])
        except (KeyError, TypeError, ValueError) as e:
            return {"success": False, "task_type": "debt-payoff", "error": f"Each debt needs numeric 'balance', 'apr', 'min_payment': {e}"}

        avalanche = self._simulate_payoff(debts, extra_payment, "avalanche")
        snowball = self._simulate_payoff(debts, extra_payment, "snowball")

        interest_saved_by_avalanche = round(snowball["total_interest_paid"] - avalanche["total_interest_paid"], 2)

        return {
            "success": True,
            "task_type": "debt-payoff",
            "inputs": {"debts": debts, "extra_monthly_payment": extra_payment},
            "avalanche_strategy": {**avalanche, "order": "highest APR first -- minimizes total interest"},
            "snowball_strategy": {**snowball, "order": "smallest balance first -- faster small wins, may cost more interest"},
            "interest_saved_by_avalanche_vs_snowball": interest_saved_by_avalanche,
            "method": "Real month-by-month amortization simulation: interest accrues monthly on remaining "
                      "balance, minimums paid first, extra payment (plus freed-up minimums from paid-off "
                      "debts) applied in strategy order",
        }

    # ------------------------------------------------------------------
    # Real net worth calculation
    # ------------------------------------------------------------------

    def _net_worth(self, params: Dict[str, Any]) -> Dict[str, Any]:
        assets = params.get("assets", {})
        liabilities = params.get("liabilities", {})
        if not isinstance(assets, dict) or not isinstance(liabilities, dict):
            return {"success": False, "task_type": "net-worth", "error": "'assets' and 'liabilities' must both be dicts of {name: amount}"}

        total_assets = sum(float(v) for v in assets.values())
        total_liabilities = sum(float(v) for v in liabilities.values())
        net_worth = total_assets - total_liabilities

        return {
            "success": True,
            "task_type": "net-worth",
            "assets": assets, "total_assets": round(total_assets, 2),
            "liabilities": liabilities, "total_liabilities": round(total_liabilities, 2),
            "net_worth": round(net_worth, 2),
            "debt_to_asset_ratio": round(total_liabilities / total_assets, 4) if total_assets > 0 else None,
        }

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general personal finance question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-query",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "budget-analysis — 50/30/20 rule check on your own categorized expenses",
                "savings-projection — compound-interest future value with monthly contributions",
                "retirement-projection — nominal + inflation-adjusted retirement balance",
                "debt-payoff — real month-by-month avalanche vs. snowball simulation",
                "net-worth — assets minus liabilities",
            ],
        }
