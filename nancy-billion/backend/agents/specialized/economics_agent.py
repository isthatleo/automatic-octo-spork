"""
Economics/Macro Agent for Nancy/Billion Backend
Real macroeconomic indicator data via the World Bank Open Data API
(api.worldbank.org -- free, no key required, any ISO2/ISO3 country code or
aggregate like "WLD"), plus standard real financial/economic formulas
(compound growth, CAGR, rule-of-70 doubling time, inflation adjustment).

Distinct from CryptoTradingAgent (crypto markets) and MarketResearchAgent
(consumer/competitive research) -- this covers macro/country-level economics.
Same honesty contract as the other research agents: an indicator/country
combination with no real data returns success: False, never an invented figure.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_specialized_agent import SpecializedAgent
from ..real_compute import compute_statistics, linear_regression

logger = logging.getLogger(__name__)

# World Bank indicator codes (real, public -- data.worldbank.org/indicator).
INDICATORS: Dict[str, Dict[str, str]] = {
    "gdp_current_usd":        {"code": "NY.GDP.MKTP.CD",   "label": "GDP (current US$)"},
    "gdp_growth_pct":         {"code": "NY.GDP.MKTP.KD.ZG", "label": "GDP growth (annual %)"},
    "gdp_per_capita_usd":     {"code": "NY.GDP.PCAP.CD",    "label": "GDP per capita (current US$)"},
    "inflation_pct":          {"code": "FP.CPI.TOTL.ZG",    "label": "Inflation, consumer prices (annual %)"},
    "cpi_index":              {"code": "FP.CPI.TOTL",       "label": "Consumer price index (2010=100)"},
    "unemployment_pct":       {"code": "SL.UEM.TOTL.ZS",    "label": "Unemployment (% of total labor force)"},
    "population_total":       {"code": "SP.POP.TOTL",       "label": "Population, total"},
    "exports_pct_gdp":        {"code": "NE.EXP.GNFS.ZS",    "label": "Exports of goods and services (% of GDP)"},
    "imports_pct_gdp":        {"code": "NE.IMP.GNFS.ZS",    "label": "Imports of goods and services (% of GDP)"},
    "real_interest_rate_pct": {"code": "FR.INR.RINR",       "label": "Real interest rate (%)"},
    "gov_debt_pct_gdp":       {"code": "GC.DOD.TOTL.GD.ZS", "label": "Central government debt (% of GDP)"},
}


class EconomicsAgent(SpecializedAgent):
    """Macroeconomic research: real World Bank indicator data + standard economic/financial formulas"""

    def __init__(self, settings):
        super().__init__(settings, "Economics/Macro Agent", "economics-macro")
        self.capabilities.update({
            "description": (
                "Macroeconomic research agent: real country-level indicator time series from the World "
                "Bank Open Data API, plus standard economic formulas (CAGR, rule-of-70 doubling time, "
                "compound growth, CPI-based inflation adjustment)."
            ),
            "confidence": 0.84,
            "specializations": [
                "macroeconomic-indicators",
                "growth-trend-analysis",
                "inflation-adjustment",
                "compound-growth-projection",
            ],
            "tools": ["world-bank-open-data-api"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "indicator-lookup")
        try:
            if task_type == "indicator-lookup":
                return await self._indicator_lookup(task_data)
            elif task_type == "growth-analysis":
                return await self._growth_analysis(task_data)
            elif task_type == "inflation-adjust":
                return await self._inflation_adjust(task_data)
            elif task_type == "compound-growth":
                return self._compound_growth(task_data)
            elif task_type == "list-indicators":
                return {"success": True, "task_type": "list-indicators", "indicators": INDICATORS}
            else:
                return await self._general_query(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Real World Bank data fetch
    # ------------------------------------------------------------------

    async def _fetch_indicator(self, country: str, indicator_code: str, per_page: int = 100) -> Optional[List[Dict[str, Any]]]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator_code}",
                    params={"format": "json", "per_page": per_page},
                )
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
                    return None
                return payload[1]
        except Exception as e:
            logger.warning("EconomicsAgent: fetch failed for %s/%s: %s", country, indicator_code, e)
            return None

    def _resolve_indicator(self, params: Dict[str, Any]) -> Optional[Dict[str, str]]:
        name = str(params.get("indicator", "")).strip().lower()
        if name in INDICATORS:
            return INDICATORS[name]
        for key, entry in INDICATORS.items():
            if entry["code"].lower() == name:
                return entry
        return None

    async def _indicator_lookup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        country = str(params.get("country", "")).strip().upper()
        if not country:
            return {"success": False, "task_type": "indicator-lookup", "error": "'country' (ISO2/ISO3 code, e.g. 'US', 'DEU', or 'WLD' for world) is required"}

        indicator = self._resolve_indicator(params)
        if indicator is None:
            return {
                "success": False, "task_type": "indicator-lookup",
                "error": f"Unknown indicator '{params.get('indicator')}'.",
                "known_indicators": sorted(INDICATORS.keys()),
            }

        raw = await self._fetch_indicator(country, indicator["code"])
        if not raw:
            return {
                "success": False, "task_type": "indicator-lookup", "country": country,
                "error": f"No real data returned for '{indicator['label']}' in '{country}' -- not returning a fabricated figure.",
            }

        series = [(entry["date"], entry["value"]) for entry in raw if entry.get("value") is not None]
        series.sort(key=lambda p: p[0])
        if not series:
            return {"success": False, "task_type": "indicator-lookup", "country": country, "error": "All returned values were null for this range"}

        values = [v for _, v in series]
        stats = compute_statistics(values)
        latest_year, latest_value = series[-1]

        return {
            "success": True,
            "task_type": "indicator-lookup",
            "country": country,
            "indicator": indicator["label"],
            "indicator_code": indicator["code"],
            "latest": {"year": latest_year, "value": latest_value},
            "series": [{"year": y, "value": v} for y, v in series],
            "statistics": stats,
            "source": "World Bank Open Data API (api.worldbank.org)",
        }

    # ------------------------------------------------------------------
    # Real trend analysis (CAGR + linear regression)
    # ------------------------------------------------------------------

    async def _growth_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        country = str(params.get("country", "")).strip().upper()
        indicator = self._resolve_indicator(params) or INDICATORS["gdp_per_capita_usd"]
        if not country:
            return {"success": False, "task_type": "growth-analysis", "error": "'country' is required"}

        raw = await self._fetch_indicator(country, indicator["code"])
        if not raw:
            return {"success": False, "task_type": "growth-analysis", "country": country, "error": "No real data returned -- not fabricating a growth analysis"}

        series = sorted(((entry["date"], entry["value"]) for entry in raw if entry.get("value") is not None), key=lambda p: p[0])
        if len(series) < 2:
            return {"success": False, "task_type": "growth-analysis", "country": country, "error": "Not enough real data points to analyze growth"}

        years = [float(y) for y, _ in series]
        values = [v for _, v in series]
        first_year, first_value = series[0]
        last_year, last_value = series[-1]
        n_years = years[-1] - years[0]

        cagr = None
        doubling_time = None
        if first_value > 0 and n_years > 0:
            cagr = (last_value / first_value) ** (1.0 / n_years) - 1.0
            if cagr > 0:
                doubling_time = 70.0 / (cagr * 100.0)  # Rule of 70

        reg = linear_regression(years, values)

        return {
            "success": True,
            "task_type": "growth-analysis",
            "country": country,
            "indicator": indicator["label"],
            "period": {"from": first_year, "to": last_year, "years": round(n_years, 1)},
            "cagr_pct": round(cagr * 100.0, 4) if cagr is not None else None,
            "rule_of_70_doubling_time_years": round(doubling_time, 2) if doubling_time else None,
            "linear_trend": reg,
            "volatility": compute_statistics(values),
            "method": "CAGR = (end/start)^(1/years) - 1; doubling time = 70 / (CAGR%) (Rule of 70)",
            "source": "World Bank Open Data API (api.worldbank.org)",
        }

    # ------------------------------------------------------------------
    # Real CPI-based inflation adjustment
    # ------------------------------------------------------------------

    async def _inflation_adjust(self, params: Dict[str, Any]) -> Dict[str, Any]:
        country = str(params.get("country", "")).strip().upper()
        amount = params.get("amount")
        from_year = str(params.get("from_year", ""))
        to_year = str(params.get("to_year", ""))
        if not country or amount is None or not from_year or not to_year:
            return {"success": False, "task_type": "inflation-adjust", "error": "'country', 'amount', 'from_year', 'to_year' are all required"}

        raw = await self._fetch_indicator(country, INDICATORS["cpi_index"]["code"])
        if not raw:
            return {"success": False, "task_type": "inflation-adjust", "error": "No real CPI data returned -- not fabricating an adjustment"}

        cpi_by_year = {entry["date"]: entry["value"] for entry in raw if entry.get("value") is not None}
        cpi_from = cpi_by_year.get(from_year)
        cpi_to = cpi_by_year.get(to_year)
        if cpi_from is None or cpi_to is None:
            return {
                "success": False, "task_type": "inflation-adjust",
                "error": f"CPI data unavailable for {'from_year' if cpi_from is None else 'to_year'}",
                "available_years": sorted(cpi_by_year.keys()),
            }

        amount = float(amount)
        adjusted = amount * (cpi_to / cpi_from)

        return {
            "success": True,
            "task_type": "inflation-adjust",
            "country": country,
            "inputs": {"amount": amount, "from_year": from_year, "to_year": to_year},
            "cpi_from": cpi_from, "cpi_to": cpi_to,
            "adjusted_amount": round(adjusted, 2),
            "cumulative_inflation_pct": round((cpi_to / cpi_from - 1.0) * 100.0, 2),
            "method": "adjusted = amount * (CPI_to / CPI_from)",
            "source": "World Bank Open Data API (api.worldbank.org), CPI 2010=100",
        }

    # ------------------------------------------------------------------
    # Standard real compound-growth formula (no external fetch needed)
    # ------------------------------------------------------------------

    def _compound_growth(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            principal = float(params.get("principal", 100.0))
            rate_pct = float(params.get("annual_rate_pct", 3.0))
            years = float(params.get("years", 10.0))
        except (TypeError, ValueError):
            return {"success": False, "task_type": "compound-growth", "error": "'principal', 'annual_rate_pct', 'years' must be numeric"}

        rate = rate_pct / 100.0
        future_value = principal * (1.0 + rate) ** years
        doubling_time = (70.0 / rate_pct) if rate_pct > 0 else None

        return {
            "success": True,
            "task_type": "compound-growth",
            "inputs": {"principal": principal, "annual_rate_pct": rate_pct, "years": years},
            "future_value": round(future_value, 2),
            "total_growth_pct": round((future_value / principal - 1.0) * 100.0, 2),
            "rule_of_70_doubling_time_years": round(doubling_time, 2) if doubling_time else None,
            "method": "FV = P * (1 + r)^t",
        }

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general economics question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-query",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "indicator-lookup — real World Bank macro indicator series for a country",
                "growth-analysis — real CAGR/doubling-time/trend analysis",
                "inflation-adjust — real CPI-based amount adjustment between years",
                "compound-growth — standard compound-interest projection",
                "list-indicators — see all supported indicator names",
            ],
        }
