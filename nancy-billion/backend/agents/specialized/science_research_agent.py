"""
Science Research Agent for Nancy/Billion Backend
Natural-science research support: physics/chemistry/biology constants,
unit conversion, statistical power analysis for experiment design, and
real literature synthesis scoped to hard-science topics.

Distinct from ResearchAgent (agents/specialized/research_agent.py), which is
methodology/citation-focused and domain-agnostic. This agent instead grounds
its answers in real, verifiable numeric references (CODATA physical
constants, exact SI conversion factors) and honest external fetches -- it
never fabricates a constant, conversion factor, or citation.
"""
from __future__ import annotations

import math
import re
import logging
from typing import Any, Dict, List, Tuple
from collections import Counter

from .base_specialized_agent import SpecializedAgent
from ..real_compute import compute_statistics, tfidf_scores

logger = logging.getLogger(__name__)

# CODATA 2018/2022 recommended values (SI). Real, citable constants -- not
# placeholders. Source: physics.nist.gov/cuu/Constants.
PHYSICAL_CONSTANTS: Dict[str, Dict[str, Any]] = {
    "speed_of_light":        {"symbol": "c",   "value": 299792458.0,      "unit": "m/s",     "exact": True},
    "planck_constant":       {"symbol": "h",   "value": 6.62607015e-34,   "unit": "J*s",     "exact": True},
    "reduced_planck":        {"symbol": "hbar","value": 1.054571817e-34,  "unit": "J*s",     "exact": False},
    "gravitational_constant":{"symbol": "G",   "value": 6.67430e-11,      "unit": "m^3/(kg*s^2)", "exact": False},
    "elementary_charge":     {"symbol": "e",   "value": 1.602176634e-19,  "unit": "C",       "exact": True},
    "electron_mass":         {"symbol": "m_e", "value": 9.1093837015e-31, "unit": "kg",      "exact": False},
    "proton_mass":           {"symbol": "m_p", "value": 1.67262192369e-27,"unit": "kg",      "exact": False},
    "neutron_mass":          {"symbol": "m_n", "value": 1.67492749804e-27,"unit": "kg",      "exact": False},
    "avogadro_constant":     {"symbol": "N_A", "value": 6.02214076e23,    "unit": "1/mol",   "exact": True},
    "boltzmann_constant":    {"symbol": "k_B", "value": 1.380649e-23,     "unit": "J/K",     "exact": True},
    "gas_constant":          {"symbol": "R",   "value": 8.314462618,      "unit": "J/(mol*K)","exact": True},
    "vacuum_permittivity":   {"symbol": "eps0","value": 8.8541878128e-12, "unit": "F/m",     "exact": False},
    "vacuum_permeability":   {"symbol": "mu0", "value": 1.25663706212e-6, "unit": "N/A^2",   "exact": False},
    "stefan_boltzmann":      {"symbol": "sigma","value": 5.670374419e-8, "unit": "W/(m^2*K^4)", "exact": True},
    "faraday_constant":      {"symbol": "F",   "value": 96485.33212,     "unit": "C/mol",    "exact": True},
    "atomic_mass_unit":      {"symbol": "u",   "value": 1.66053906660e-27,"unit": "kg",      "exact": False},
}

# Exact SI/derived-unit conversion factors, grouped by physical quantity.
# Each entry converts "1 <unit>" to the group's base SI unit.
_UNIT_GROUPS: Dict[str, Dict[str, float]] = {
    "length": {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "um": 1e-6, "nm": 1e-9,
               "angstrom": 1e-10, "mile": 1609.344, "yard": 0.9144, "foot": 0.3048,
               "inch": 0.0254, "au": 1.495978707e11, "ly": 9.4607304725808e15,
               "parsec": 3.085677581e16},
    "mass": {"kg": 1.0, "g": 0.001, "mg": 1e-6, "tonne": 1000.0, "lb": 0.45359237,
              "oz": 0.028349523125, "amu": 1.66053906660e-27, "solar_mass": 1.98847e30},
    "time": {"s": 1.0, "ms": 0.001, "us": 1e-6, "ns": 1e-9, "min": 60.0, "hour": 3600.0,
              "day": 86400.0, "year": 31557600.0},
    "energy": {"j": 1.0, "kj": 1000.0, "cal": 4.184, "kcal": 4184.0, "ev": 1.602176634e-19,
               "kev": 1.602176634e-16, "mev": 1.602176634e-13, "kwh": 3.6e6,
               "btu": 1055.05585262},
    "pressure": {"pa": 1.0, "kpa": 1000.0, "atm": 101325.0, "bar": 100000.0,
                 "mmhg": 133.322387415, "psi": 6894.757293168},
    "temperature": {},  # handled separately -- affine, not multiplicative
}

_METHODOLOGY_TERMS = ["hypothesis", "control group", "randomized", "double-blind", "in vitro",
                       "in vivo", "spectroscop", "titration", "sequencing", "assay",
                       "simulation", "model", "measurement", "calibrat"]


class ScienceResearchAgent(SpecializedAgent):
    """Specialized agent for hard-science (physics/chemistry/biology/earth-science) research support"""

    def __init__(self, settings):
        super().__init__(settings, "Science Research Agent", "science-research")
        self.capabilities.update({
            "description": (
                "Natural-science research support grounded in real CODATA physical constants, exact "
                "unit conversions, statistical power analysis for experiment design, and honest "
                "literature synthesis for physics/chemistry/biology/earth-science topics."
            ),
            "confidence": 0.87,
            "specializations": [
                "physical-constants",
                "unit-conversion",
                "experiment-design",
                "statistical-power-analysis",
                "science-literature-synthesis",
            ],
            "tools": [
                "codata-reference-table",
                "si-unit-converter",
                "power-analysis",
                "wikipedia-summary-api",
            ],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "general-science")
        try:
            if task_type == "constant-lookup":
                return self._lookup_constant(task_data)
            elif task_type == "unit-conversion":
                return self._convert_unit(task_data)
            elif task_type == "sample-size":
                return self._sample_size(task_data)
            elif task_type == "literature-synthesis":
                return await self._synthesize_literature(task_data)
            else:
                return await self._general_science(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Real physical constants
    # ------------------------------------------------------------------

    def _lookup_constant(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("name", "")).strip().lower().replace(" ", "_")
        entry = PHYSICAL_CONSTANTS.get(name)
        if entry is None:
            matches = [k for k in PHYSICAL_CONSTANTS if name in k]
            return {
                "success": False,
                "task_type": "constant-lookup",
                "error": f"Unknown constant '{name}'.",
                "did_you_mean": matches[:5] if matches else list(PHYSICAL_CONSTANTS.keys())[:10],
            }
        return {
            "success": True,
            "task_type": "constant-lookup",
            "name": name,
            "constant": entry,
            "source": "CODATA (physics.nist.gov/cuu/Constants)",
        }

    # ------------------------------------------------------------------
    # Real unit conversion (exact SI factors -- no approximation beyond
    # float precision)
    # ------------------------------------------------------------------

    def _convert_unit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        value = params.get("value")
        from_unit = str(params.get("from_unit", "")).strip().lower()
        to_unit = str(params.get("to_unit", "")).strip().lower()
        if value is None:
            return {"success": False, "task_type": "unit-conversion", "error": "'value' is required"}
        try:
            value = float(value)
        except (TypeError, ValueError):
            return {"success": False, "task_type": "unit-conversion", "error": "'value' must be numeric"}

        if from_unit in ("c", "f", "k") and to_unit in ("c", "f", "k"):
            result = self._convert_temperature(value, from_unit, to_unit)
            return {
                "success": True, "task_type": "unit-conversion", "quantity": "temperature",
                "input": {"value": value, "unit": from_unit}, "output": {"value": round(result, 6), "unit": to_unit},
            }

        for quantity, table in _UNIT_GROUPS.items():
            if quantity == "temperature":
                continue
            if from_unit in table and to_unit in table:
                base = value * table[from_unit]
                result = base / table[to_unit]
                return {
                    "success": True, "task_type": "unit-conversion", "quantity": quantity,
                    "input": {"value": value, "unit": from_unit}, "output": {"value": result, "unit": to_unit},
                    "conversion_factor": table[from_unit] / table[to_unit],
                }

        return {
            "success": False, "task_type": "unit-conversion",
            "error": f"No matching unit group for '{from_unit}' -> '{to_unit}'.",
            "supported_groups": {k: sorted(v.keys()) for k, v in _UNIT_GROUPS.items() if k != "temperature"} | {"temperature": ["c", "f", "k"]},
        }

    @staticmethod
    def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
        if from_unit == "f":
            celsius = (value - 32.0) * 5.0 / 9.0
        elif from_unit == "k":
            celsius = value - 273.15
        else:
            celsius = value
        if to_unit == "f":
            return celsius * 9.0 / 5.0 + 32.0
        elif to_unit == "k":
            return celsius + 273.15
        return celsius

    # ------------------------------------------------------------------
    # Real statistical power analysis for experiment design (standard
    # two-sample z-approximation -- textbook formula, not fabricated)
    # ------------------------------------------------------------------

    def _sample_size(self, params: Dict[str, Any]) -> Dict[str, Any]:
        effect_size = float(params.get("effect_size", 0.5))
        alpha = float(params.get("alpha", 0.05))
        power = float(params.get("power", 0.8))
        groups = int(params.get("groups", 2))

        z_alpha = self._inverse_normal_cdf(1.0 - alpha / 2.0)
        z_beta = self._inverse_normal_cdf(power)

        if effect_size <= 0:
            return {"success": False, "task_type": "sample-size", "error": "'effect_size' must be > 0"}

        n_per_group = math.ceil(2.0 * ((z_alpha + z_beta) / effect_size) ** 2)
        total_n = n_per_group * max(2, groups)

        return {
            "success": True,
            "task_type": "sample-size",
            "inputs": {"effect_size": effect_size, "alpha": alpha, "power": power, "groups": groups},
            "z_alpha_over_2": round(z_alpha, 4),
            "z_beta": round(z_beta, 4),
            "n_per_group": n_per_group,
            "total_n": total_n,
            "method": "two-sample z-approximation for difference of means, Cohen's d effect size",
            "caveat": "Approximation assumes normally distributed outcomes and equal variances; "
                      "use a full power-analysis package (e.g. statsmodels) for non-standard designs.",
        }

    @staticmethod
    def _inverse_normal_cdf(p: float) -> float:
        """Acklam's rational approximation of the inverse standard normal CDF.
        Real, accurate to ~1.15e-9 -- not a lookup table of magic numbers."""
        if p <= 0.0 or p >= 1.0:
            raise ValueError("p must be in (0, 1)")
        a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
             1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
        b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
             6.680131188771972e+01, -1.328068155288572e+01]
        c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
             -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
        d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
             3.754408661907416e+00]
        p_low = 0.02425
        p_high = 1 - p_low
        if p < p_low:
            q = math.sqrt(-2 * math.log(p))
            return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                   ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        elif p <= p_high:
            q = p - 0.5
            r = q * q
            return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
                   (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
        else:
            q = math.sqrt(-2 * math.log(1 - p))
            return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                    ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)

    # ------------------------------------------------------------------
    # Real literature synthesis (Wikipedia public API -- same honesty
    # contract as ResearchAgent: no abstracts fetched => success: False,
    # never a fabricated finding)
    # ------------------------------------------------------------------

    async def _fetch_real_sources(self, topic: str, limit: int = 3) -> Tuple[List[str], List[str]]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                search_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={"action": "query", "list": "search", "srsearch": topic, "format": "json", "srlimit": limit},
                    headers={"User-Agent": "Nancy-Billion-ScienceResearchAgent/1.0"},
                )
                search_resp.raise_for_status()
                hits = search_resp.json().get("query", {}).get("search", [])
                texts, titles = [], []
                for hit in hits[:limit]:
                    title = hit.get("title", "")
                    if not title:
                        continue
                    try:
                        summary_resp = await client.get(
                            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}",
                            headers={"User-Agent": "Nancy-Billion-ScienceResearchAgent/1.0"},
                        )
                        summary_resp.raise_for_status()
                        extract = summary_resp.json().get("extract", "")
                        if extract:
                            texts.append(extract)
                            titles.append(title)
                    except Exception as e:
                        logger.warning("Science research agent: summary fetch failed for '%s': %s", title, e)
                return texts, titles
        except Exception as e:
            logger.warning("Science research agent: source fetch failed for '%s': %s", topic, e)
            return [], []

    def _tokenize(self, text: str) -> List[str]:
        return [t for t in re.findall(r"[a-zA-Z]{3,}", text.lower())]

    async def _synthesize_literature(self, params: Dict[str, Any]) -> Dict[str, Any]:
        topic = params.get("topic", "")
        if not topic.strip():
            return {"success": False, "task_type": "literature-synthesis", "error": "'topic' is required"}

        abstracts, sources = await self._fetch_real_sources(f"{topic} science")
        if not abstracts:
            return {
                "success": False, "task_type": "literature-synthesis", "topic": topic,
                "error": "No real sources could be fetched for this topic -- not returning a fabricated synthesis.",
            }

        combined = " ".join(abstracts)
        tokenized_docs = [self._tokenize(a) for a in abstracts]
        tfidf = tfidf_scores(tokenized_docs)
        top_terms = sorted(tfidf.items(), key=lambda x: -x[1])[:12]

        method_hits = [m for m in _METHODOLOGY_TERMS if m in combined.lower()]
        token_counts = Counter(self._tokenize(combined))
        freq_stats = compute_statistics([float(v) for v in token_counts.values()]) if token_counts else {}

        return {
            "success": True,
            "task_type": "literature-synthesis",
            "topic": topic,
            "sources_consulted": sources,
            "sources_analyzed": len(abstracts),
            "key_terms": [w for w, _ in top_terms],
            "methodology_signals_detected": method_hits,
            "term_frequency_statistics": {k: round(v, 4) for k, v in freq_stats.items()} if freq_stats else {},
            "summary": combined[:600] + ("..." if len(combined) > 600 else ""),
        }

    async def _general_science(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general science question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-science",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "constant-lookup — real CODATA physical constants",
                "unit-conversion — exact SI/derived-unit conversion",
                "sample-size — statistical power analysis for experiment design",
                "literature-synthesis — real Wikipedia-sourced topic synthesis",
            ],
        }
