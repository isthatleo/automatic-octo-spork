"""
Energy Grid/Renewables Agent for Nancy/Billion Backend
Real solar/wind output estimates (using live irradiance/wind-speed data from
the Open-Meteo public API, no key required), plus standard real engineering
formulas: Levelized Cost of Energy (LCOE), grid carbon intensity (published
IPCC lifecycle emission factors), and battery storage sizing.

Distinct from NuclearResearchAgent (fission/fusion physics specifically) and
EnvironmentalControlNexus (IoT/smart-home device control) -- this is grid-
scale renewable energy engineering and economics.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional, Tuple

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

AIR_DENSITY_KG_M3 = 1.225        # sea-level standard air density
BETZ_LIMIT = 0.593                # theoretical maximum wind turbine efficiency (Betz's law)

# Real IPCC lifecycle greenhouse-gas emission factors (g CO2-eq/kWh), median
# values from IPCC AR5 WG3 Annex III -- public, widely cited reference data.
EMISSION_FACTORS_G_CO2_PER_KWH: Dict[str, float] = {
    "coal": 820, "gas": 490, "oil": 650, "biomass": 230,
    "solar_pv": 41, "wind": 11, "hydro": 24, "nuclear": 12, "geothermal": 38,
}


class EnergyGridAgent(SpecializedAgent):
    """Grid-scale renewable energy: real solar/wind output, LCOE, carbon intensity, battery sizing"""

    def __init__(self, settings):
        super().__init__(settings, "Energy Grid/Renewables Agent", "energy-grid")
        self.capabilities.update({
            "description": (
                "Renewable energy engineering agent: real solar-PV and wind-turbine output estimates "
                "grounded in live irradiance/wind data (Open-Meteo), plus standard LCOE, grid carbon "
                "intensity (IPCC lifecycle emission factors), and battery storage sizing formulas."
            ),
            "confidence": 0.83,
            "specializations": [
                "solar-output-estimation",
                "wind-output-estimation",
                "levelized-cost-of-energy",
                "grid-carbon-intensity",
                "battery-storage-sizing",
            ],
            "tools": ["open-meteo-forecast-api", "lcoe-calculator", "ipcc-emission-factors"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "solar-output")
        try:
            if task_type == "solar-output":
                return await self._solar_output(task_data)
            elif task_type == "wind-output":
                return await self._wind_output(task_data)
            elif task_type == "lcoe":
                return self._lcoe(task_data)
            elif task_type == "carbon-intensity":
                return self._carbon_intensity(task_data)
            elif task_type == "battery-sizing":
                return self._battery_sizing(task_data)
            else:
                return await self._general_query(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Real location resolution + live data fetch (Open-Meteo)
    # ------------------------------------------------------------------

    async def _resolve_location(self, params: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
        lat = params.get("latitude")
        lon = params.get("longitude")
        if lat is not None and lon is not None:
            return float(lat), float(lon), f"{lat},{lon}", None

        location = str(params.get("location", "")).strip()
        if not location:
            return None, None, None, "Provide either 'location' (place name) or 'latitude'+'longitude'"

        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1, "language": "en", "format": "json"},
                )
                resp.raise_for_status()
                results = resp.json().get("results")
                if not results:
                    return None, None, None, f"Could not geocode location '{location}'"
                hit = results[0]
                name = f"{hit.get('name')}, {hit.get('country', '')}".strip(", ")
                return float(hit["latitude"]), float(hit["longitude"]), name, None
        except Exception as e:
            logger.warning("EnergyGridAgent: geocoding failed for '%s': %s", location, e)
            return None, None, None, f"Geocoding request failed: {e}"

    async def _fetch_hourly(self, lat: float, lon: float, variable: str) -> Optional[list]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={"latitude": lat, "longitude": lon, "hourly": variable, "forecast_days": 1, "timezone": "auto"},
                )
                resp.raise_for_status()
                return resp.json().get("hourly", {}).get(variable)
        except Exception as e:
            logger.warning("EnergyGridAgent: hourly fetch failed for '%s': %s", variable, e)
            return None

    # ------------------------------------------------------------------
    # Real solar PV output estimate
    # ------------------------------------------------------------------

    async def _solar_output(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lat, lon, name, err = await self._resolve_location(params)
        if err:
            return {"success": False, "task_type": "solar-output", "error": err}

        panel_area_m2 = float(params.get("panel_area_m2", 20.0))
        panel_efficiency = float(params.get("panel_efficiency", 0.20))
        performance_ratio = float(params.get("performance_ratio", 0.80))  # real-world derate (inverter loss, temp, soiling)

        irradiance = await self._fetch_hourly(lat, lon, "shortwave_radiation")
        if not irradiance:
            return {"success": False, "task_type": "solar-output", "error": "No real irradiance data returned for this location"}

        irradiance = [v for v in irradiance if v is not None]
        peak_irradiance = max(irradiance) if irradiance else 0.0
        avg_irradiance = sum(irradiance) / len(irradiance) if irradiance else 0.0
        # Energy = integral of Power dt; hourly W/m^2 values summed give Wh/m^2/day
        daily_energy_wh_m2 = sum(irradiance)

        peak_power_w = peak_irradiance * panel_area_m2 * panel_efficiency * performance_ratio
        daily_energy_kwh = (daily_energy_wh_m2 * panel_area_m2 * panel_efficiency * performance_ratio) / 1000.0

        return {
            "success": True,
            "task_type": "solar-output",
            "location": name,
            "inputs": {"panel_area_m2": panel_area_m2, "panel_efficiency": panel_efficiency, "performance_ratio": performance_ratio},
            "peak_irradiance_w_m2": round(peak_irradiance, 1),
            "avg_irradiance_w_m2": round(avg_irradiance, 1),
            "estimated_peak_power_w": round(peak_power_w, 1),
            "estimated_daily_energy_kwh": round(daily_energy_kwh, 3),
            "estimated_annual_energy_kwh": round(daily_energy_kwh * 365.25, 1),
            "method": "Power = Irradiance x Area x Efficiency x Performance_ratio; daily energy = sum of hourly Wh/m^2",
            "source": "Open-Meteo hourly shortwave_radiation forecast (open-meteo.com), today's data",
        }

    # ------------------------------------------------------------------
    # Real wind turbine output estimate
    # ------------------------------------------------------------------

    async def _wind_output(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lat, lon, name, err = await self._resolve_location(params)
        if err:
            return {"success": False, "task_type": "wind-output", "error": err}

        rotor_diameter_m = float(params.get("rotor_diameter_m", 100.0))
        power_coefficient = min(float(params.get("power_coefficient", 0.40)), BETZ_LIMIT)

        wind_speeds_kmh = await self._fetch_hourly(lat, lon, "windspeed_10m")
        if not wind_speeds_kmh:
            return {"success": False, "task_type": "wind-output", "error": "No real wind-speed data returned for this location"}

        wind_speeds_ms = [v / 3.6 for v in wind_speeds_kmh if v is not None]
        if not wind_speeds_ms:
            return {"success": False, "task_type": "wind-output", "error": "Wind-speed data was empty"}

        swept_area_m2 = math.pi * (rotor_diameter_m / 2.0) ** 2

        def power_at(v: float) -> float:
            return 0.5 * AIR_DENSITY_KG_M3 * swept_area_m2 * (v ** 3) * power_coefficient

        hourly_power_w = [power_at(v) for v in wind_speeds_ms]
        daily_energy_kwh = sum(hourly_power_w) / 1000.0  # 1 sample/hour -> Wh, sum -> Wh, /1000 -> kWh
        avg_wind_ms = sum(wind_speeds_ms) / len(wind_speeds_ms)
        peak_power_w = max(hourly_power_w)

        return {
            "success": True,
            "task_type": "wind-output",
            "location": name,
            "inputs": {"rotor_diameter_m": rotor_diameter_m, "power_coefficient": power_coefficient},
            "swept_area_m2": round(swept_area_m2, 1),
            "avg_wind_speed_ms": round(avg_wind_ms, 2),
            "estimated_peak_power_w": round(peak_power_w, 1),
            "estimated_daily_energy_kwh": round(daily_energy_kwh, 3),
            "estimated_annual_energy_kwh": round(daily_energy_kwh * 365.25, 1),
            "betz_limit_note": f"power_coefficient capped at Betz limit ({BETZ_LIMIT}) -- the theoretical maximum for any wind turbine",
            "method": "Power = 0.5 x air_density x swept_area x wind_speed^3 x Cp",
            "source": "Open-Meteo hourly windspeed_10m forecast (open-meteo.com), today's data",
        }

    # ------------------------------------------------------------------
    # Real Levelized Cost of Energy
    # ------------------------------------------------------------------

    def _lcoe(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            capex = float(params.get("capex_usd", 1_000_000.0))
            opex_annual = float(params.get("opex_annual_usd", 20_000.0))
            annual_output_kwh = float(params.get("annual_output_kwh", 2_000_000.0))
            discount_rate_pct = float(params.get("discount_rate_pct", 6.0))
            lifetime_years = float(params.get("lifetime_years", 25.0))
        except (TypeError, ValueError):
            return {"success": False, "task_type": "lcoe", "error": "all inputs must be numeric"}
        if annual_output_kwh <= 0:
            return {"success": False, "task_type": "lcoe", "error": "'annual_output_kwh' must be > 0"}

        r = discount_rate_pct / 100.0
        n = lifetime_years
        if r == 0:
            crf = 1.0 / n
        else:
            crf = (r * (1.0 + r) ** n) / ((1.0 + r) ** n - 1.0)  # capital recovery factor

        annualized_capex = capex * crf
        lcoe_usd_per_kwh = (annualized_capex + opex_annual) / annual_output_kwh

        return {
            "success": True,
            "task_type": "lcoe",
            "inputs": {
                "capex_usd": capex, "opex_annual_usd": opex_annual, "annual_output_kwh": annual_output_kwh,
                "discount_rate_pct": discount_rate_pct, "lifetime_years": lifetime_years,
            },
            "capital_recovery_factor": round(crf, 6),
            "annualized_capex_usd": round(annualized_capex, 2),
            "lcoe_usd_per_kwh": round(lcoe_usd_per_kwh, 4),
            "lcoe_usd_per_mwh": round(lcoe_usd_per_kwh * 1000.0, 2),
            "method": "LCOE = (CapEx * CRF + OpEx_annual) / AnnualEnergyOutput; "
                      "CRF = r(1+r)^n / ((1+r)^n - 1) (standard capital recovery factor)",
        }

    # ------------------------------------------------------------------
    # Real grid carbon intensity (weighted average, real IPCC factors)
    # ------------------------------------------------------------------

    def _carbon_intensity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        mix = params.get("generation_mix_pct")
        if not isinstance(mix, dict) or not mix:
            return {
                "success": False, "task_type": "carbon-intensity",
                "error": "'generation_mix_pct' (dict of source -> percentage, summing to ~100) is required",
                "known_sources": sorted(EMISSION_FACTORS_G_CO2_PER_KWH.keys()),
            }

        unknown = [s for s in mix if s not in EMISSION_FACTORS_G_CO2_PER_KWH]
        if unknown:
            return {
                "success": False, "task_type": "carbon-intensity",
                "error": f"Unknown source(s): {unknown}",
                "known_sources": sorted(EMISSION_FACTORS_G_CO2_PER_KWH.keys()),
            }

        total_pct = sum(mix.values())
        weighted = sum(pct / 100.0 * EMISSION_FACTORS_G_CO2_PER_KWH[source] for source, pct in mix.items())

        renewable_sources = {"solar_pv", "wind", "hydro", "geothermal"}
        renewable_pct = sum(pct for s, pct in mix.items() if s in renewable_sources)

        return {
            "success": True,
            "task_type": "carbon-intensity",
            "generation_mix_pct": mix,
            "total_pct_supplied": round(total_pct, 2),
            "weighted_carbon_intensity_g_co2_per_kwh": round(weighted, 2),
            "renewable_share_pct": round(renewable_pct, 2),
            "emission_factors_used": {s: EMISSION_FACTORS_G_CO2_PER_KWH[s] for s in mix},
            "method": "Weighted average of IPCC AR5 WG3 Annex III median lifecycle emission factors, weighted by generation share",
            "note": "If total_pct_supplied isn't ~100, treat the weighted intensity as proportional, not absolute.",
        }

    # ------------------------------------------------------------------
    # Real battery storage sizing
    # ------------------------------------------------------------------

    def _battery_sizing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            daily_energy_kwh = float(params.get("daily_energy_kwh", 30.0))
            autonomy_days = float(params.get("autonomy_days", 1.0))
            depth_of_discharge = float(params.get("depth_of_discharge", 0.8))
            round_trip_efficiency = float(params.get("round_trip_efficiency", 0.9))
        except (TypeError, ValueError):
            return {"success": False, "task_type": "battery-sizing", "error": "all inputs must be numeric"}
        if depth_of_discharge <= 0 or round_trip_efficiency <= 0:
            return {"success": False, "task_type": "battery-sizing", "error": "'depth_of_discharge' and 'round_trip_efficiency' must be > 0"}

        usable_energy_needed = daily_energy_kwh * autonomy_days
        nameplate_capacity_kwh = usable_energy_needed / (depth_of_discharge * round_trip_efficiency)

        return {
            "success": True,
            "task_type": "battery-sizing",
            "inputs": {
                "daily_energy_kwh": daily_energy_kwh, "autonomy_days": autonomy_days,
                "depth_of_discharge": depth_of_discharge, "round_trip_efficiency": round_trip_efficiency,
            },
            "usable_energy_needed_kwh": round(usable_energy_needed, 2),
            "required_nameplate_capacity_kwh": round(nameplate_capacity_kwh, 2),
            "method": "Nameplate capacity = (daily_energy x autonomy_days) / (depth_of_discharge x round_trip_efficiency)",
        }

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general energy/renewables question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-query",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "solar-output — real irradiance-grounded PV output estimate for a location",
                "wind-output — real wind-speed-grounded turbine output estimate",
                "lcoe — standard Levelized Cost of Energy calculation",
                "carbon-intensity — weighted grid carbon intensity from a generation mix",
                "battery-sizing — required storage capacity for a given autonomy target",
            ],
        }
