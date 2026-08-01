"""
Statistical Testing Agent for Nancy/Billion.
Real hypothesis testing via scipy.stats -- an actual two-sample t-test,
chi-square test, and a real minimum-sample-size calculation for planning an
A/B test, never a guessed "this looks significant."
"""
from __future__ import annotations

from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent


class StatisticalTestingAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Statistical Testing Agent", "statistical-testing")
        self.capabilities.update({
            "description": "Real hypothesis testing (t-test, chi-square) and A/B test sample-size planning via scipy.stats",
            "confidence": 0.85,
            "specializations": ["hypothesis-testing", "ab-testing", "sample-size-planning"],
            "tools": ["scipy.stats"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "t_test":
            return self._t_test(task_data.get("group_a", []), task_data.get("group_b", []))
        if task_type == "chi_square":
            return self._chi_square(task_data.get("observed", []))
        if task_type == "ab_sample_size":
            return self._ab_sample_size(
                float(task_data.get("baseline_rate", 0.1)),
                float(task_data.get("minimum_detectable_effect", 0.02)),
                float(task_data.get("power", 0.8)),
                float(task_data.get("alpha", 0.05)),
            )
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _t_test(self, group_a: List[float], group_b: List[float]) -> Dict[str, Any]:
        if len(group_a) < 2 or len(group_b) < 2:
            return {"success": False, "error": "group_a and group_b each need at least 2 real values"}
        try:
            from scipy import stats
            import numpy as np
            a, b = np.array(group_a, dtype=np.float64), np.array(group_b, dtype=np.float64)
            t_stat, p_value = stats.ttest_ind(a, b, equal_var=False)  # Welch's t-test, doesn't assume equal variance
            return {
                "success": True,
                "mean_a": round(float(a.mean()), 4), "mean_b": round(float(b.mean()), 4),
                "t_statistic": round(float(t_stat), 4), "p_value": round(float(p_value), 6),
                "significant_at_0.05": bool(p_value < 0.05),
                "method": "Welch's two-sample t-test (unequal variance assumed)",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _chi_square(self, observed: List[List[float]]) -> Dict[str, Any]:
        if not observed or len(observed) < 2:
            return {"success": False, "error": "observed must be a real 2D contingency table (at least 2 rows)"}
        try:
            from scipy import stats
            chi2, p_value, dof, expected = stats.chi2_contingency(observed)
            return {
                "success": True,
                "chi2_statistic": round(float(chi2), 4), "p_value": round(float(p_value), 6),
                "degrees_of_freedom": int(dof), "significant_at_0.05": bool(p_value < 0.05),
                "expected_frequencies": [[round(float(v), 2) for v in row] for row in expected],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _ab_sample_size(self, baseline_rate: float, mde: float, power: float, alpha: float) -> Dict[str, Any]:
        """Real per-variant sample size for a two-proportion test, using the
        standard normal-approximation formula (Cohen's method)."""
        if not (0 < baseline_rate < 1) or mde <= 0:
            return {"success": False, "error": "baseline_rate must be in (0,1) and minimum_detectable_effect must be positive"}
        try:
            from scipy import stats
            p1 = baseline_rate
            p2 = baseline_rate + mde
            p_avg = (p1 + p2) / 2
            z_alpha = stats.norm.ppf(1 - alpha / 2)
            z_beta = stats.norm.ppf(power)
            numerator = (z_alpha * (2 * p_avg * (1 - p_avg)) ** 0.5 + z_beta * (p1 * (1 - p1) + p2 * (1 - p2)) ** 0.5) ** 2
            n = numerator / (mde ** 2)
            return {
                "success": True,
                "baseline_rate": p1, "target_rate": round(p2, 4),
                "required_sample_size_per_variant": int(n) + 1,
                "power": power, "alpha": alpha,
                "method": "two-proportion z-test sample size (normal approximation)",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I run real hypothesis tests (t-test, chi-square) and calculate real A/B test sample sizes -- "
            "give me your real numbers, not a guess."
        )}
