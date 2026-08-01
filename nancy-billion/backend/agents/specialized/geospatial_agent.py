"""
Geospatial Agent for Nancy/Billion.
Real geocoding (reuses map_snapshot.py's Nominatim lookup, the same one the
location-snapshot feature uses) plus a real haversine great-circle distance
calculation -- no fabricated coordinates or distances.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

EARTH_RADIUS_KM = 6371.0088


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class GeospatialAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Geospatial Agent", "geospatial")
        self.capabilities.update({
            "description": "Real geocoding and great-circle distance calculations between real places",
            "confidence": 0.85,
            "specializations": ["geocoding", "distance-calculation"],
            "tools": ["nominatim", "haversine"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "geocode":
            return await self._geocode(task_data.get("place", ""))
        if task_type == "distance":
            return await self._distance(task_data.get("place_a", ""), task_data.get("place_b", ""))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    async def _geocode(self, place: str) -> Dict[str, Any]:
        from map_snapshot import geocode
        result = await geocode(place)
        if result is None:
            return {"success": False, "error": f"Could not geocode '{place}'"}
        return {"success": True, "display_name": result.display_name, "lat": result.lat, "lon": result.lon}

    async def _distance(self, place_a: str, place_b: str) -> Dict[str, Any]:
        from map_snapshot import geocode
        a, b = await geocode(place_a), await geocode(place_b)
        if a is None or b is None:
            missing = place_a if a is None else place_b
            return {"success": False, "error": f"Could not geocode '{missing}'"}
        km = _haversine_km(a.lat, a.lon, b.lat, b.lon)
        return {
            "success": True,
            "from": a.display_name, "to": b.display_name,
            "distance_km": round(km, 1), "distance_miles": round(km * 0.621371, 1),
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I do real geocoding and great-circle distance calculations between two real places."
        )}
