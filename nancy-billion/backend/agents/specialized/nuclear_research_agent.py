"""
Nuclear Research Agent for Nancy/Billion Backend

Scope, deliberately: civilian nuclear science education, radiation safety,
nuclear medicine, reactor physics fundamentals, the nuclear fuel cycle, IAEA
non-proliferation safeguards, and fusion energy research. All numeric
references (isotope half-lives, physical constants, the Lawson criterion)
are real, textbook/public values -- nothing fabricated.

Hard scope limit, enforced in code before any other logic runs (mirrors the
HardRedLineEnforcer pattern in ethical_governance_core.py, specifically its
RL-02 "must not assist in creating weapons of mass destruction" red line):
this agent refuses any request for weapon design, yield/critical-mass
calculations for a device, enrichment-cascade engineering, or other
weaponization detail, regardless of how the request is framed. It exists to
support legitimate education, safety, medicine, and policy research only --
not to substitute for it being blocked at the ethics layer too.
"""
from __future__ import annotations

import math
import re
import logging
from typing import Any, Dict, Optional

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard scope gate -- checked before any task logic executes
# ---------------------------------------------------------------------------
_WEAPON_INTENT_PATTERNS = [
    r"\bweapon(ize|ization|-grade)?\b", r"\bwarhead\b", r"\bbomb\b", r"\bnuke\b",
    r"\bdetonat", r"\bgun[- ]type\s+device\b", r"\bimplosion[- ]type\s+device\b",
    r"\bfission\s+bomb\b", r"\bimprovised\s+nuclear\s+device\b", r"\bdirty\s+bomb\b",
    r"\bpit\s+design\b", r"\btrigger\s+mechanism\b", r"\bexplosive\s+lens\b",
    r"\bhow\s+(to|do\s+i)\s+(build|make|construct)\s+a\s+(nuclear|atomic)\b",
    r"\benrichment\s+cascade\s+design\b", r"\bcritical\s+mass\s+for\s+a\s+device\b",
]
_WEAPON_INTENT_RE = re.compile("|".join(_WEAPON_INTENT_PATTERNS), re.IGNORECASE)

# Real isotope half-lives (public, textbook values -- seconds where useful).
ISOTOPE_HALF_LIVES: Dict[str, Dict[str, Any]] = {
    "tc-99m": {"half_life_s": 6.0058 * 3600, "context": "medical imaging (SPECT tracer)"},
    "i-131":  {"half_life_s": 8.02 * 86400, "context": "thyroid imaging/therapy"},
    "co-60":  {"half_life_s": 5.2711 * 365.25 * 86400, "context": "industrial radiography, teletherapy"},
    "cs-137": {"half_life_s": 30.17 * 365.25 * 86400, "context": "calibration sources, legacy medical therapy"},
    "c-14":   {"half_life_s": 5730 * 365.25 * 86400, "context": "radiocarbon dating"},
    "u-235":  {"half_life_s": 7.04e8 * 365.25 * 86400, "context": "reactor fuel isotope"},
    "u-238":  {"half_life_s": 4.468e9 * 365.25 * 86400, "context": "natural uranium, breeding to Pu-239"},
    "pu-239": {"half_life_s": 24110 * 365.25 * 86400, "context": "reactor fuel (MOX), legacy stockpile material"},
    "k-40":   {"half_life_s": 1.248e9 * 365.25 * 86400, "context": "natural background radiation"},
}

# Point-source gamma dose-rate constants (public health-physics reference
# values, uSv*m^2/(MBq*h)) for common industrial/medical sources.
GAMMA_DOSE_CONSTANTS: Dict[str, float] = {
    "co-60": 0.351, "cs-137": 0.0778, "i-131": 0.0563, "tc-99m": 0.0224,
}


class NuclearResearchAgent(SpecializedAgent):
    """Civilian nuclear science research: physics, radiation safety, medicine, fuel cycle, non-proliferation, fusion"""

    def __init__(self, settings):
        super().__init__(settings, "Nuclear Research Agent", "nuclear-research")
        self.capabilities.update({
            "description": (
                "Civilian nuclear science research agent scoped to education, radiation safety, nuclear "
                "medicine, reactor physics fundamentals, the nuclear fuel cycle, IAEA non-proliferation "
                "safeguards, and fusion energy research. Refuses any weapon-design, yield, or "
                "enrichment-cascade engineering request as a hard rule, not a soft preference."
            ),
            "confidence": 0.8,
            "specializations": [
                "radioactive-decay",
                "nuclear-binding-energy",
                "radiation-dosimetry",
                "fuel-cycle-and-safeguards",
                "fusion-energy-research",
            ],
            "tools": ["decay-law-calculator", "semi-empirical-mass-formula", "dose-rate-estimator"],
            "mode": "scope-restricted",
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        # Scan every free-text field for weapon-intent phrasing before doing
        # anything else. This runs regardless of task_type -- there is no
        # code path in this agent that skips it.
        blocked = self._scope_gate(task_data)
        if blocked is not None:
            return blocked

        task_type = task_data.get("type", "general-nuclear-science")
        try:
            if task_type == "decay-calculation":
                return self._decay_calculation(task_data)
            elif task_type == "binding-energy":
                return self._binding_energy(task_data)
            elif task_type == "dose-estimate":
                return self._dose_estimate(task_data)
            elif task_type == "fuel-cycle-overview":
                return self._fuel_cycle_overview(task_data)
            elif task_type == "fusion-overview":
                return self._fusion_overview(task_data)
            else:
                return await self._general_nuclear_science(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Hard scope gate
    # ------------------------------------------------------------------

    def _scope_gate(self, task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        text_fields = []
        for key in ("query", "description", "purpose", "prompt", "task"):
            v = task_data.get(key)
            if isinstance(v, str):
                text_fields.append(v)
        combined = " ".join(text_fields)
        if combined and _WEAPON_INTENT_RE.search(combined):
            logger.warning("NuclearResearchAgent: blocked weapon-intent request: %r", combined[:200])
            return {
                "success": False,
                "task_type": "scope_blocked",
                "verdict": "prohibited",
                "error": (
                    "This request falls outside this agent's scope. The Nuclear Research Agent supports "
                    "civilian nuclear science education, radiation safety, nuclear medicine, reactor "
                    "physics fundamentals, the fuel cycle, non-proliferation policy, and fusion research "
                    "only. It does not and will not provide weapon design, yield, critical-mass-for-a-device, "
                    "or enrichment-cascade engineering assistance, regardless of framing or stated intent."
                ),
                "reference": "See the IAEA (iaea.org) for authoritative non-proliferation and nuclear safety guidance.",
            }
        return None

    # ------------------------------------------------------------------
    # Real physics: radioactive decay law
    # ------------------------------------------------------------------

    def _decay_calculation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        isotope = str(params.get("isotope", "")).strip().lower()
        entry = ISOTOPE_HALF_LIVES.get(isotope)
        if entry is None:
            return {
                "success": False, "task_type": "decay-calculation",
                "error": f"Unknown isotope '{isotope}'.",
                "known_isotopes": sorted(ISOTOPE_HALF_LIVES.keys()),
            }

        half_life_s = entry["half_life_s"]
        lam = math.log(2) / half_life_s
        n0 = float(params.get("initial_quantity", 1.0))
        elapsed_s = float(params.get("elapsed_seconds", half_life_s))

        n_t = n0 * math.exp(-lam * elapsed_s)
        activity_now = lam * n_t
        fraction_remaining = n_t / n0 if n0 else 0.0
        half_lives_elapsed = elapsed_s / half_life_s

        return {
            "success": True,
            "task_type": "decay-calculation",
            "isotope": isotope,
            "context": entry["context"],
            "half_life_s": half_life_s,
            "half_life_human": self._human_duration(half_life_s),
            "decay_constant_per_s": lam,
            "elapsed_seconds": elapsed_s,
            "half_lives_elapsed": round(half_lives_elapsed, 4),
            "initial_quantity": n0,
            "remaining_quantity": n_t,
            "fraction_remaining": round(fraction_remaining, 6),
            "activity_now": activity_now,
            "method": "N(t) = N0 * exp(-lambda*t), lambda = ln(2)/half_life  (standard radioactive decay law)",
        }

    @staticmethod
    def _human_duration(seconds: float) -> str:
        units = [("year", 365.25 * 86400), ("day", 86400.0), ("hour", 3600.0), ("minute", 60.0), ("second", 1.0)]
        for name, size in units:
            if seconds >= size:
                return f"{seconds / size:.3g} {name}s"
        return f"{seconds:.3g} seconds"

    # ------------------------------------------------------------------
    # Real physics: binding energy per nucleon (semi-empirical mass formula)
    # ------------------------------------------------------------------

    def _binding_energy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            a = int(params["mass_number"])
            z = int(params["atomic_number"])
        except (KeyError, TypeError, ValueError):
            return {"success": False, "task_type": "binding-energy", "error": "'mass_number' (A) and 'atomic_number' (Z) are required integers"}
        if a <= 0 or z < 0 or z > a:
            return {"success": False, "task_type": "binding-energy", "error": "require 0 <= Z <= A and A > 0"}

        n = a - z
        a_v, a_s, a_c, a_a = 15.75, 17.8, 0.711, 23.7
        a_p = 11.18

        volume_term = a_v * a
        surface_term = -a_s * a ** (2.0 / 3.0)
        coulomb_term = -a_c * z * (z - 1) / (a ** (1.0 / 3.0))
        asymmetry_term = -a_a * (a - 2 * z) ** 2 / a

        if z % 2 == 0 and n % 2 == 0:
            pairing_term = a_p / math.sqrt(a)
        elif z % 2 == 1 and n % 2 == 1:
            pairing_term = -a_p / math.sqrt(a)
        else:
            pairing_term = 0.0

        binding_energy_mev = volume_term + surface_term + coulomb_term + asymmetry_term + pairing_term
        per_nucleon = binding_energy_mev / a

        return {
            "success": True,
            "task_type": "binding-energy",
            "mass_number_A": a,
            "atomic_number_Z": z,
            "neutron_number_N": n,
            "binding_energy_mev": round(binding_energy_mev, 3),
            "binding_energy_per_nucleon_mev": round(per_nucleon, 4),
            "terms_mev": {
                "volume": round(volume_term, 3), "surface": round(surface_term, 3),
                "coulomb": round(coulomb_term, 3), "asymmetry": round(asymmetry_term, 3),
                "pairing": round(pairing_term, 3),
            },
            "method": "Semi-empirical (Weizsacker) mass formula -- standard nuclear physics, most accurate mid-mass-range",
            "note": "Peaks near A~56 (iron group), which is why fusion releases energy below that mass and "
                    "fission releases energy above it -- the standard textbook explanation for both processes.",
        }

    # ------------------------------------------------------------------
    # Real health-physics: point-source gamma dose-rate estimate
    # ------------------------------------------------------------------

    def _dose_estimate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        isotope = str(params.get("isotope", "")).strip().lower()
        gamma_constant = GAMMA_DOSE_CONSTANTS.get(isotope)
        if gamma_constant is None:
            return {
                "success": False, "task_type": "dose-estimate",
                "error": f"No gamma dose constant on file for '{isotope}'.",
                "known_isotopes": sorted(GAMMA_DOSE_CONSTANTS.keys()),
            }

        activity_mbq = float(params.get("activity_mbq", 100.0))
        distance_m = float(params.get("distance_m", 1.0))
        shielding_halving_layers = float(params.get("shielding_halving_layers", 0.0))

        if distance_m <= 0:
            return {"success": False, "task_type": "dose-estimate", "error": "'distance_m' must be > 0"}

        unshielded_rate = gamma_constant * activity_mbq / (distance_m ** 2)  # uSv/h
        shielded_rate = unshielded_rate / (2 ** shielding_halving_layers)

        return {
            "success": True,
            "task_type": "dose-estimate",
            "isotope": isotope,
            "inputs": {"activity_mbq": activity_mbq, "distance_m": distance_m, "shielding_halving_layers": shielding_halving_layers},
            "gamma_dose_constant_uSv_m2_per_MBq_h": gamma_constant,
            "unshielded_dose_rate_uSv_per_h": round(unshielded_rate, 4),
            "shielded_dose_rate_uSv_per_h": round(shielded_rate, 6),
            "method": "Point-source inverse-square law: dose_rate = Gamma * A / d^2, with each half-value "
                      "layer of shielding halving the rate -- standard health-physics approximation.",
            "reference_context": "For comparison, natural background is roughly 0.1-0.3 uSv/h; occupational "
                                  "limits are set by bodies like the NRC/ICRP, not by this estimate.",
            "safety_note": "This is an educational approximation, not a substitute for a certified health "
                            "physicist's survey for any real source or facility.",
        }

    # ------------------------------------------------------------------
    # Policy / qualitative overviews
    # ------------------------------------------------------------------

    def _fuel_cycle_overview(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "task_type": "fuel-cycle-overview",
            "front_end": [
                "Mining and milling of uranium ore into yellowcake (U3O8)",
                "Conversion to uranium hexafluoride (UF6)",
                "Enrichment to reactor-grade (typically 3-5% U-235) for most power reactors",
                "Fuel fabrication into fuel assemblies",
            ],
            "back_end": [
                "Spent fuel interim storage (wet pools, then dry cask storage)",
                "Reprocessing (where practiced) to recover usable uranium/plutonium",
                "Long-term geological disposal of high-level waste",
            ],
            "non_proliferation_safeguards": [
                "IAEA safeguards under the Nuclear Non-Proliferation Treaty (NPT) verify declared nuclear "
                "material isn't diverted to weapons use",
                "Material accounting, containment/surveillance, and on-site inspections are the core "
                "safeguards mechanisms",
                "Enrichment above reactor-grade and reprocessing are the two fuel-cycle steps that draw the "
                "most proliferation scrutiny, which is exactly why IAEA safeguards focus there",
            ],
            "reference": "IAEA Safeguards Overview: iaea.org/topics/safeguards-and-verification",
        }

    def _fusion_overview(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "task_type": "fusion-overview",
            "lawson_criterion": (
                "Ignition requires the triple product n*T*tau_E (density x temperature x energy confinement "
                "time) to exceed roughly 3e21 keV*s/m^3 for D-T fusion -- the standard benchmark fusion "
                "reactors are measured against."
            ),
            "leading_approaches": [
                {"approach": "magnetic confinement (tokamak)", "flagship_project": "ITER (France)", "status": "under construction, first plasma targeted for the 2030s"},
                {"approach": "magnetic confinement (stellarator)", "flagship_project": "Wendelstein 7-X (Germany)", "status": "operational research device"},
                {"approach": "inertial confinement", "flagship_project": "National Ignition Facility (USA)", "status": "achieved net energy gain from the fuel capsule in 2022"},
            ],
            "why_fusion_is_proliferation_resistant": (
                "D-T fusion doesn't produce or require fissile material, and most fusion concepts (tokamak, "
                "stellarator, laser ICF) have no straightforward weaponization path -- a key reason fusion "
                "energy research doesn't carry the same non-proliferation concerns as fission fuel cycles."
            ),
            "recommendations": [
                "Track ITER's assembly milestones for the current state of magnetic confinement",
                "Follow NIF/LLNL publications for inertial confinement progress",
                "Watch private-sector approaches (e.g. compact high-field tokamaks) for near-term commercialization claims",
            ],
        }

    async def _general_nuclear_science(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general nuclear science question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-nuclear-science",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "decay-calculation — real radioactive decay law for common isotopes",
                "binding-energy — semi-empirical mass formula",
                "dose-estimate — point-source gamma dose-rate approximation",
                "fuel-cycle-overview — civilian fuel cycle + IAEA safeguards",
                "fusion-overview — Lawson criterion and leading fusion approaches",
            ],
            "scope_note": "Civilian science, safety, medicine, and policy only -- see this agent's description for its hard scope limits.",
        }
