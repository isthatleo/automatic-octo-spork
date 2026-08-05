"""
Automotive Specs Agent for Nancy/Billion.

Real vehicle specification data ONLY -- the NHTSA vPIC API
(vpic.nhtsa.dot.gov), the official US Department of Transportation vehicle
registry: fully free, no API key, no registration. decode_vin resolves a
real 17-character VIN to year/make/model/trim/engine/transmission/
drivetrain/body style; list_makes enumerates the real current manufacturer
list. Honest scope: vPIC covers vehicles registered for the US market --
it will not have every exotic/non-US-market vehicle, and it carries zero
pricing/market-value data (a real valuation is a separate, generally paid
problem this agent does not attempt to fabricate an answer for).
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

_VPIC_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"


class AutomotiveSpecsAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Automotive Specs Agent", "automotive-specs")
        self.capabilities.update({
            "description": "Real US-market vehicle specs via NHTSA's official vPIC registry (VIN decode, manufacturer list) -- no pricing/valuation data, never fabricated",
            "confidence": 0.75,
            "specializations": ["vin-decode", "vehicle-specs"],
            "tools": ["nhtsa_vpic"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "decode_vin":
            vin = (task_data.get("vin") or "").strip()
            if not vin:
                return {"success": False, "error": "decode_vin requires a 'vin' (17-character vehicle identification number)"}
            return await self._decode_vin(vin)
        if task_type == "list_makes":
            return await self._list_makes()
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    async def _decode_vin(self, vin: str) -> Dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_VPIC_BASE}/decodevinvalues/{vin}", params={"format": "json"})
                resp.raise_for_status()
                results = resp.json().get("Results") or []
        except Exception as e:
            return {"success": False, "error": f"NHTSA vPIC lookup failed: {e}"}
        if not results:
            return {"success": False, "error": f"NHTSA vPIC returned no data for VIN {vin}"}
        row = results[0]
        if not row.get("Make"):
            return {"success": False, "error": f"VIN {vin} did not decode to a real US-market vehicle record"}
        return {
            "success": True,
            "vin": vin,
            "year": row.get("ModelYear"),
            "make": row.get("Make"),
            "model": row.get("Model"),
            "trim": row.get("Trim"),
            "body_class": row.get("BodyClass"),
            "engine": row.get("EngineConfiguration") or row.get("EngineModel"),
            "engine_cylinders": row.get("EngineCylinders"),
            "transmission": row.get("TransmissionStyle"),
            "drive_type": row.get("DriveType"),
            "plant_country": row.get("PlantCountry"),
        }

    async def _list_makes(self) -> Dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_VPIC_BASE}/getallmakes", params={"format": "json"})
                resp.raise_for_status()
                results = resp.json().get("Results") or []
        except Exception as e:
            return {"success": False, "error": f"NHTSA vPIC lookup failed: {e}"}
        if not results:
            return {"success": False, "error": "NHTSA vPIC returned no manufacturer data"}
        makes = sorted({r["Make_Name"] for r in results if r.get("Make_Name")})
        return {"success": True, "count": len(makes), "makes": makes[:200]}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I decode real VINs and look up real US-market vehicle specs via NHTSA's vPIC registry -- "
            "no pricing or valuation data, never a fabricated number."
        )}
