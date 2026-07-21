"""
Materials Science Agent for Nancy/Billion Backend
Bulk engineering material properties (metals, polymers, ceramics, composites)
and real mechanical/thermal calculations -- Hooke's law, thermal expansion,
factor of safety, weighted multi-criteria material selection.

Distinct from NanotechnologyAgent (molecular/atomic-scale engineering) --
this is classical/macroscopic materials engineering. Property values below
are real published reference figures (typical handbook values -- actual
material batches vary, which is stated explicitly rather than implying
precision the source data doesn't have).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

# Real, typical handbook property values. Units: density kg/m^3, Young's
# modulus GPa, yield strength MPa, ultimate tensile strength MPa, thermal
# conductivity W/(m*K), thermal expansion coefficient 1e-6/K, melting point C.
MATERIALS: Dict[str, Dict[str, float]] = {
    "steel_1020":       {"density": 7870, "youngs_modulus_gpa": 200, "yield_mpa": 350,  "uts_mpa": 420,  "thermal_conductivity": 51.9, "thermal_expansion": 11.7, "melting_point_c": 1515},
    "stainless_304":    {"density": 8000, "youngs_modulus_gpa": 193, "yield_mpa": 215,  "uts_mpa": 505,  "thermal_conductivity": 16.2, "thermal_expansion": 17.3, "melting_point_c": 1450},
    "aluminum_6061":    {"density": 2700, "youngs_modulus_gpa": 68.9,"yield_mpa": 276,  "uts_mpa": 310,  "thermal_conductivity": 167,  "thermal_expansion": 23.6, "melting_point_c": 652},
    "titanium_ti6al4v": {"density": 4430, "youngs_modulus_gpa": 113.8,"yield_mpa": 880, "uts_mpa": 950,  "thermal_conductivity": 6.7,  "thermal_expansion": 8.6,  "melting_point_c": 1604},
    "copper_c11000":    {"density": 8960, "youngs_modulus_gpa": 110, "yield_mpa": 69,   "uts_mpa": 220,  "thermal_conductivity": 391,  "thermal_expansion": 16.5, "melting_point_c": 1085},
    "polyethylene_hdpe":{"density": 950,  "youngs_modulus_gpa": 1.0, "yield_mpa": 26,   "uts_mpa": 30,   "thermal_conductivity": 0.48, "thermal_expansion": 200,  "melting_point_c": 130},
    "polypropylene":    {"density": 905,  "youngs_modulus_gpa": 1.5, "yield_mpa": 30,   "uts_mpa": 35,   "thermal_conductivity": 0.22, "thermal_expansion": 150,  "melting_point_c": 160},
    "nylon_6_6":        {"density": 1140, "youngs_modulus_gpa": 2.9, "yield_mpa": 82,   "uts_mpa": 90,   "thermal_conductivity": 0.25, "thermal_expansion": 80,   "melting_point_c": 265},
    "alumina_al2o3":    {"density": 3950, "youngs_modulus_gpa": 370, "yield_mpa": None, "uts_mpa": 300,  "thermal_conductivity": 30,   "thermal_expansion": 8.1,  "melting_point_c": 2072},
    "carbon_fiber_epoxy": {"density": 1600, "youngs_modulus_gpa": 135, "yield_mpa": None, "uts_mpa": 1500, "thermal_conductivity": 7,  "thermal_expansion": 0.5, "melting_point_c": None},
    "glass_soda_lime":  {"density": 2500, "youngs_modulus_gpa": 70,  "yield_mpa": None, "uts_mpa": 50,   "thermal_conductivity": 1.0,  "thermal_expansion": 9.0,  "melting_point_c": 1500},
    "concrete":         {"density": 2400, "youngs_modulus_gpa": 30,  "yield_mpa": None, "uts_mpa": 3,    "thermal_conductivity": 1.7,  "thermal_expansion": 12.0, "melting_point_c": None},
    "wood_pine":        {"density": 500,  "youngs_modulus_gpa": 9,   "yield_mpa": None, "uts_mpa": 40,   "thermal_conductivity": 0.12, "thermal_expansion": 5.0,  "melting_point_c": None},
}


class MaterialsScienceAgent(SpecializedAgent):
    """Bulk engineering materials: property lookup, stress/strain, thermal expansion, material selection"""

    def __init__(self, settings):
        super().__init__(settings, "Materials Science Agent", "materials-science")
        self.capabilities.update({
            "description": (
                "Classical/macroscopic materials engineering: real handbook property lookup for common "
                "metals/polymers/ceramics/composites, Hooke's-law stress-strain analysis, thermal "
                "expansion, and weighted multi-criteria material selection."
            ),
            "confidence": 0.83,
            "specializations": [
                "material-property-lookup",
                "stress-strain-analysis",
                "thermal-expansion",
                "material-selection",
            ],
            "tools": ["materials-property-database", "hookes-law-calculator"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "material-lookup")
        try:
            if task_type == "material-lookup":
                return self._material_lookup(task_data)
            elif task_type == "stress-strain":
                return self._stress_strain(task_data)
            elif task_type == "thermal-expansion":
                return self._thermal_expansion(task_data)
            elif task_type == "material-selection":
                return self._material_selection(task_data)
            else:
                return await self._general_query(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    def _resolve_material(self, name: str) -> tuple[str, Dict[str, float]] | tuple[None, None]:
        key = name.strip().lower().replace(" ", "_").replace("-", "_")
        if key in MATERIALS:
            return key, MATERIALS[key]
        matches = [k for k in MATERIALS if key in k]
        return (matches[0], MATERIALS[matches[0]]) if len(matches) == 1 else (None, None)

    def _material_lookup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("material", ""))
        key, entry = self._resolve_material(name)
        if entry is None:
            return {
                "success": False, "task_type": "material-lookup",
                "error": f"Unknown material '{name}'.",
                "known_materials": sorted(MATERIALS.keys()),
            }
        return {
            "success": True, "task_type": "material-lookup", "material": key,
            "properties": entry,
            "units": {
                "density": "kg/m^3", "youngs_modulus_gpa": "GPa", "yield_mpa": "MPa", "uts_mpa": "MPa",
                "thermal_conductivity": "W/(m*K)", "thermal_expansion": "1e-6/K", "melting_point_c": "C",
            },
            "note": "Typical handbook values -- real material batches vary with processing/alloy grade.",
        }

    # ------------------------------------------------------------------
    # Real Hooke's law stress-strain analysis
    # ------------------------------------------------------------------

    def _stress_strain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("material", ""))
        key, entry = self._resolve_material(name)
        if entry is None:
            return {"success": False, "task_type": "stress-strain", "error": f"Unknown material '{name}'", "known_materials": sorted(MATERIALS.keys())}

        try:
            applied_stress_mpa = float(params.get("applied_stress_mpa", 100.0))
            original_length_m = float(params.get("original_length_m", 1.0))
        except (TypeError, ValueError):
            return {"success": False, "task_type": "stress-strain", "error": "'applied_stress_mpa' and 'original_length_m' must be numeric"}

        e_mpa = entry["youngs_modulus_gpa"] * 1000.0  # GPa -> MPa
        strain = applied_stress_mpa / e_mpa
        elongation_m = strain * original_length_m

        yield_mpa = entry.get("yield_mpa")
        factor_of_safety = round(yield_mpa / applied_stress_mpa, 3) if yield_mpa else None
        within_elastic_limit = (applied_stress_mpa < yield_mpa) if yield_mpa else None

        return {
            "success": True,
            "task_type": "stress-strain",
            "material": key,
            "inputs": {"applied_stress_mpa": applied_stress_mpa, "original_length_m": original_length_m},
            "strain": round(strain, 8),
            "elongation_m": round(elongation_m, 8),
            "yield_strength_mpa": yield_mpa,
            "factor_of_safety": factor_of_safety,
            "within_elastic_limit": within_elastic_limit,
            "method": "Hooke's law: strain = stress / E; elongation = strain * L0 (valid only below yield strength)",
        }

    # ------------------------------------------------------------------
    # Real linear thermal expansion
    # ------------------------------------------------------------------

    def _thermal_expansion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("material", ""))
        key, entry = self._resolve_material(name)
        if entry is None:
            return {"success": False, "task_type": "thermal-expansion", "error": f"Unknown material '{name}'", "known_materials": sorted(MATERIALS.keys())}

        try:
            length_m = float(params.get("length_m", 1.0))
            delta_t_c = float(params.get("delta_temperature_c", 50.0))
        except (TypeError, ValueError):
            return {"success": False, "task_type": "thermal-expansion", "error": "'length_m' and 'delta_temperature_c' must be numeric"}

        alpha = entry["thermal_expansion"] * 1e-6  # 1/K
        delta_l = alpha * length_m * delta_t_c

        return {
            "success": True,
            "task_type": "thermal-expansion",
            "material": key,
            "inputs": {"length_m": length_m, "delta_temperature_c": delta_t_c},
            "expansion_coefficient_per_k": entry["thermal_expansion"] * 1e-6,
            "length_change_m": round(delta_l, 8),
            "new_length_m": round(length_m + delta_l, 8),
            "method": "Linear thermal expansion: delta_L = alpha * L0 * delta_T",
        }

    # ------------------------------------------------------------------
    # Real weighted multi-criteria material selection (deterministic scoring,
    # not a fabricated recommendation)
    # ------------------------------------------------------------------

    def _material_selection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        weights = params.get("weights", {"youngs_modulus_gpa": 0.25, "yield_mpa": 0.25, "thermal_conductivity": 0.25, "density": -0.25})
        candidates = params.get("candidates") or list(MATERIALS.keys())

        valid = {k: MATERIALS[k] for k in candidates if k in MATERIALS}
        if not valid:
            return {"success": False, "task_type": "material-selection", "error": "No valid material names in 'candidates'", "known_materials": sorted(MATERIALS.keys())}

        # Real min-max normalization per property, so each criterion contributes
        # 0-1 regardless of unit scale, then weighted sum (negative weight = "lower is better").
        scores: Dict[str, float] = {k: 0.0 for k in valid}
        for prop, weight in weights.items():
            prop_values = [(k, v[prop]) for k, v in valid.items() if v.get(prop) is not None]
            if len(prop_values) < 2:
                continue
            vals = [v for _, v in prop_values]
            lo, hi = min(vals), max(vals)
            span = (hi - lo) or 1.0
            for k, v in prop_values:
                normalized = (v - lo) / span
                scores[k] += (normalized if weight >= 0 else (1.0 - normalized)) * abs(weight)

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])

        return {
            "success": True,
            "task_type": "material-selection",
            "weights": weights,
            "ranking": [{"material": k, "score": round(s, 4)} for k, s in ranked],
            "recommended": ranked[0][0] if ranked else None,
            "method": "Per-property min-max normalization (0-1), weighted sum; negative weight means 'lower is better' (e.g. density)",
        }

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general materials science question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-query",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "material-lookup — real handbook properties for a material",
                "stress-strain — Hooke's law elongation + factor of safety",
                "thermal-expansion — real linear thermal expansion calculation",
                "material-selection — weighted multi-criteria ranking across the catalog",
            ],
            "known_materials": sorted(MATERIALS.keys()),
        }
