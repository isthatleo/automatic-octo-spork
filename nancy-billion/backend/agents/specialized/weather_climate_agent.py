"""
Weather/Climate Agent for Nancy/Billion Backend
Real current weather, forecasts, and historical climate statistics via the
Open-Meteo public API (open-meteo.com) -- no API key required, no rate-limit
key management, non-commercial use is free. Also computes real derived
meteorological quantities (heat index, wind chill) from standard published
formulas.

Honesty contract, same as ResearchAgent/GeneralResearchAgent: if a real fetch
fails or a location can't be geocoded, this returns success: False with the
underlying reason -- never a fabricated forecast or climate figure.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from .base_specialized_agent import SpecializedAgent
from ..real_compute import compute_statistics, linear_regression

logger = logging.getLogger(__name__)

# Official WMO weather interpretation codes, as published by Open-Meteo's own
# API docs (open-meteo.com/en/docs) -- real, not fabricated.
WMO_WEATHER_CODES: Dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


class WeatherClimateAgent(SpecializedAgent):
    """Real weather forecasts and historical climate statistics via Open-Meteo"""

    def __init__(self, settings):
        super().__init__(settings, "Weather/Climate Agent", "weather-climate")
        self.capabilities.update({
            "description": (
                "Real current weather, multi-day forecasts, and historical climate statistics "
                "(Open-Meteo public API, no key required), plus computed heat index and wind chill."
            ),
            "confidence": 0.85,
            "specializations": [
                "current-weather",
                "weather-forecasting",
                "historical-climate-analysis",
                "heat-index-wind-chill",
            ],
            "tools": ["open-meteo-forecast-api", "open-meteo-geocoding-api", "open-meteo-archive-api"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "current-weather")
        try:
            if task_type == "current-weather":
                return await self._current_weather(task_data)
            elif task_type == "forecast":
                return await self._forecast(task_data)
            elif task_type == "climate-stats":
                return await self._climate_stats(task_data)
            elif task_type == "heat-index":
                return self._heat_index(task_data)
            elif task_type == "wind-chill":
                return self._wind_chill(task_data)
            else:
                return await self._general_query(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Real geocoding + fetch helpers (Open-Meteo public APIs)
    # ------------------------------------------------------------------

    async def _resolve_location(self, params: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
        """Returns (lat, lon, resolved_name, error)."""
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
            logger.warning("WeatherClimateAgent: geocoding failed for '%s': %s", location, e)
            return None, None, None, f"Geocoding request failed: {e}"

    # ------------------------------------------------------------------
    # Current weather
    # ------------------------------------------------------------------

    async def _current_weather(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lat, lon, name, err = await self._resolve_location(params)
        if err:
            return {"success": False, "task_type": "current-weather", "error": err}

        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={"latitude": lat, "longitude": lon, "current_weather": "true", "timezone": "auto"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return {"success": False, "task_type": "current-weather", "error": f"Weather fetch failed: {e}"}

        current = data.get("current_weather")
        if not current:
            return {"success": False, "task_type": "current-weather", "error": "No current_weather in API response"}

        code = int(current.get("weathercode", -1))
        return {
            "success": True,
            "task_type": "current-weather",
            "location": name,
            "coordinates": {"latitude": lat, "longitude": lon},
            "temperature_c": current.get("temperature"),
            "windspeed_kmh": current.get("windspeed"),
            "wind_direction_deg": current.get("winddirection"),
            "weather_code": code,
            "conditions": WMO_WEATHER_CODES.get(code, "Unknown"),
            "observed_at": current.get("time"),
            "source": "Open-Meteo (open-meteo.com)",
        }

    # ------------------------------------------------------------------
    # Multi-day forecast
    # ------------------------------------------------------------------

    async def _forecast(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lat, lon, name, err = await self._resolve_location(params)
        if err:
            return {"success": False, "task_type": "forecast", "error": err}

        days = max(1, min(16, int(params.get("days", 5))))

        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": days,
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                    },
                )
                resp.raise_for_status()
                daily = resp.json().get("daily", {})
        except Exception as e:
            return {"success": False, "task_type": "forecast", "error": f"Forecast fetch failed: {e}"}

        dates = daily.get("time", [])
        if not dates:
            return {"success": False, "task_type": "forecast", "error": "No forecast data returned"}

        days_out = []
        for i, d in enumerate(dates):
            code = int(daily.get("weathercode", [0] * len(dates))[i])
            days_out.append({
                "date": d,
                "high_c": daily.get("temperature_2m_max", [None])[i],
                "low_c": daily.get("temperature_2m_min", [None])[i],
                "precipitation_probability_pct": daily.get("precipitation_probability_max", [None])[i],
                "weather_code": code,
                "conditions": WMO_WEATHER_CODES.get(code, "Unknown"),
            })

        return {
            "success": True,
            "task_type": "forecast",
            "location": name,
            "coordinates": {"latitude": lat, "longitude": lon},
            "forecast_days": len(days_out),
            "daily": days_out,
            "source": "Open-Meteo (open-meteo.com)",
        }

    # ------------------------------------------------------------------
    # Historical climate statistics (real trend analysis, not fabricated
    # "climate normals")
    # ------------------------------------------------------------------

    async def _climate_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lat, lon, name, err = await self._resolve_location(params)
        if err:
            return {"success": False, "task_type": "climate-stats", "error": err}

        start_date = str(params.get("start_date", ""))
        end_date = str(params.get("end_date", ""))
        if not start_date or not end_date:
            return {"success": False, "task_type": "climate-stats", "error": "'start_date' and 'end_date' (YYYY-MM-DD) are required"}

        import httpx
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://archive-api.open-meteo.com/v1/archive",
                    params={
                        "latitude": lat, "longitude": lon, "start_date": start_date, "end_date": end_date,
                        "daily": "temperature_2m_max,temperature_2m_min", "timezone": "auto",
                    },
                )
                resp.raise_for_status()
                daily = resp.json().get("daily", {})
        except Exception as e:
            return {"success": False, "task_type": "climate-stats", "error": f"Historical data fetch failed: {e}"}

        dates = daily.get("time", [])
        highs = [v for v in daily.get("temperature_2m_max", []) if v is not None]
        lows = [v for v in daily.get("temperature_2m_min", []) if v is not None]
        if not dates or not highs:
            return {"success": False, "task_type": "climate-stats", "error": "No historical data returned for this range"}

        high_stats = compute_statistics(highs)
        low_stats = compute_statistics(lows)

        # Real trend: yearly mean high temperature vs. year (linear regression)
        yearly_means: Dict[int, List[float]] = {}
        for d, h in zip(dates, daily.get("temperature_2m_max", [])):
            if h is None:
                continue
            year = int(d[:4])
            yearly_means.setdefault(year, []).append(h)
        years_sorted = sorted(yearly_means.keys())
        trend = None
        if len(years_sorted) >= 3:
            year_avgs = [sum(yearly_means[y]) / len(yearly_means[y]) for y in years_sorted]
            reg = linear_regression([float(y) for y in years_sorted], year_avgs)
            trend = {
                "slope_c_per_year": reg["slope"],
                "r_squared": reg["r_squared"],
                "years_covered": len(years_sorted),
                "interpretation": (
                    f"Average daily high changing by {reg['slope']:+.4f} C/year over {len(years_sorted)} years"
                    if reg["r_squared"] > 0.1 else
                    "No clear linear trend detected in this window (low R^2)"
                ),
            }

        return {
            "success": True,
            "task_type": "climate-stats",
            "location": name,
            "coordinates": {"latitude": lat, "longitude": lon},
            "date_range": {"start": start_date, "end": end_date, "days": len(dates)},
            "daily_high_stats_c": high_stats,
            "daily_low_stats_c": low_stats,
            "yearly_trend": trend,
            "source": "Open-Meteo Historical Weather API (open-meteo.com)",
        }

    # ------------------------------------------------------------------
    # Real derived meteorological formulas
    # ------------------------------------------------------------------

    def _heat_index(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            temp_c = float(params["temperature_c"])
            rh = float(params["relative_humidity_pct"])
        except (KeyError, TypeError, ValueError):
            return {"success": False, "task_type": "heat-index", "error": "'temperature_c' and 'relative_humidity_pct' are required"}

        t_f = temp_c * 9.0 / 5.0 + 32.0
        if t_f < 80.0:
            hi_f = t_f  # NWS formula only applies >= 80F; below that, heat index ~= air temperature
        else:
            # Rothfusz regression (NWS official heat index formula)
            hi_f = (-42.379 + 2.04901523 * t_f + 10.14333127 * rh - 0.22475541 * t_f * rh
                    - 6.83783e-3 * t_f ** 2 - 5.481717e-2 * rh ** 2
                    + 1.22874e-3 * t_f ** 2 * rh + 8.5282e-4 * t_f * rh ** 2
                    - 1.99e-6 * t_f ** 2 * rh ** 2)
        hi_c = (hi_f - 32.0) * 5.0 / 9.0

        return {
            "success": True,
            "task_type": "heat-index",
            "inputs": {"temperature_c": temp_c, "relative_humidity_pct": rh},
            "heat_index_c": round(hi_c, 2),
            "heat_index_f": round(hi_f, 2),
            "method": "NWS Rothfusz regression (official heat index formula, valid >= 80F/27C)",
        }

    def _wind_chill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            temp_c = float(params["temperature_c"])
            wind_kmh = float(params["wind_speed_kmh"])
        except (KeyError, TypeError, ValueError):
            return {"success": False, "task_type": "wind-chill", "error": "'temperature_c' and 'wind_speed_kmh' are required"}

        if temp_c > 10.0 or wind_kmh < 4.8:
            return {
                "success": True, "task_type": "wind-chill",
                "wind_chill_c": round(temp_c, 2),
                "note": "Wind chill formula only applies for temp <= 10C and wind >= 4.8 km/h; returning air temperature",
            }

        v_pow = wind_kmh ** 0.16
        wind_chill_c = 13.12 + 0.6215 * temp_c - 11.37 * v_pow + 0.3965 * temp_c * v_pow

        return {
            "success": True,
            "task_type": "wind-chill",
            "inputs": {"temperature_c": temp_c, "wind_speed_kmh": wind_kmh},
            "wind_chill_c": round(wind_chill_c, 2),
            "method": "Environment Canada / NWS wind chill formula (2001 revision)",
        }

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general weather/climate question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-query",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "current-weather — real conditions for a location",
                "forecast — up to 16-day real forecast",
                "climate-stats — real historical daily-temperature trend analysis",
                "heat-index / wind-chill — NWS-standard derived formulas",
            ],
        }
