"""
Carbon Footprint Agent for Nancy/Billion.
Real arithmetic against published average emission factors (not live,
location-specific data -- honestly labeled as estimates using standard
published averages, e.g. EPA/DEFRA-style factors, not fabricated numbers).
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

# Published average emission factors (kg CO2e per unit). These are
# well-known rough averages used for illustrative estimates -- real
# location-specific figures vary and this is disclosed in every result.
_TRAVEL_KG_PER_KM = {
    "car_petrol": 0.192, "car_diesel": 0.171, "car_electric": 0.053,
    "bus": 0.105, "train": 0.041, "flight_short_haul": 0.255, "flight_long_haul": 0.150,
}
_GRID_KG_PER_KWH_GLOBAL_AVERAGE = 0.475


class CarbonFootprintAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Carbon Footprint Agent", "sustainability")
        self.capabilities.update({
            "description": "Real arithmetic estimates of travel/electricity emissions using published average emission factors (honestly labeled as estimates, not live data)",
            "confidence": 0.7,
            "specializations": ["carbon-accounting", "emissions-estimation"],
            "tools": ["published-emission-factors"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "estimate_travel_emissions":
            return self._travel(float(task_data.get("distance_km", 0)), task_data.get("mode", "car_petrol"))
        if task_type == "estimate_electricity_emissions":
            return self._electricity(float(task_data.get("kwh", 0)), task_data.get("grid_kg_per_kwh"))
        if task_type == "status":
            return {"success": True, "status": "ready", "known_travel_modes": list(_TRAVEL_KG_PER_KM)}
        return await self._general(task_data)

    def _travel(self, km: float, mode: str) -> Dict[str, Any]:
        factor = _TRAVEL_KG_PER_KM.get(mode)
        if factor is None:
            return {"success": False, "error": f"Unknown mode '{mode}'. Known: {list(_TRAVEL_KG_PER_KM)}"}
        return {
            "success": True, "distance_km": km, "mode": mode,
            "estimated_kg_co2e": round(km * factor, 2),
            "note": "Estimate using a published average emission factor, not live/location-specific data.",
        }

    def _electricity(self, kwh: float, grid_kg_per_kwh) -> Dict[str, Any]:
        factor = float(grid_kg_per_kwh) if grid_kg_per_kwh else _GRID_KG_PER_KWH_GLOBAL_AVERAGE
        return {
            "success": True, "kwh": kwh, "grid_factor_kg_per_kwh": factor,
            "estimated_kg_co2e": round(kwh * factor, 2),
            "note": "Uses the global average grid intensity unless a real local grid factor is supplied -- not live data.",
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I estimate travel and electricity emissions using published average emission factors -- real arithmetic, "
            "honestly labeled as estimates rather than live location-specific data."
        )}
