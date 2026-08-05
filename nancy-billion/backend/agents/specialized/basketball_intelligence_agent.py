"""
Basketball Intelligence Agent for Nancy/Billion.

Real NBA game/team data via balldontlie.io's v1 API -- unlike the other new
agents in this batch, this one is NOT keyless: balldontlie's free tier
(5 req/min) requires registering for your own API key at balldontlie.io,
set as BALLDONTLIE_API_KEY. Uses credential_pool.CredentialPool for the
same real cooldown-on-failure rotation every other keyed integration in
this codebase gets, rather than reading the env var directly. With no key
configured, every real task type reports that honestly rather than
fabricating scores/standings.
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent
from credential_pool import CredentialPool

_BASE = "https://api.balldontlie.io/v1"
_key_pool = CredentialPool("BALLDONTLIE_API_KEY")


class BasketballIntelligenceAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Basketball Intelligence Agent", "basketball-intelligence")
        self.capabilities.update({
            "description": "Real NBA game/team data via balldontlie.io -- requires your own free BALLDONTLIE_API_KEY, never fabricated",
            "confidence": 0.7,
            "specializations": ["today-games", "team-lookup"],
            "tools": ["balldontlie"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "today_games":
            return await self._games(task_data.get("date"))
        if task_type == "team_lookup":
            name = (task_data.get("name") or task_data.get("team") or "").strip()
            if not name:
                return {"success": False, "error": "team_lookup requires a 'name'"}
            return await self._team_lookup(name)
        if task_type == "status":
            return {"success": True, "status": "ready", "api_key_configured": _key_pool.get_key() is not None}
        return await self._general(task_data)

    async def _games(self, date: str | None) -> Dict[str, Any]:
        import datetime
        key = _key_pool.get_key()
        if key is None:
            return {"success": False, "error": "BALLDONTLIE_API_KEY not configured -- register a free key at balldontlie.io"}
        date = date or datetime.date.today().isoformat()
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}/games", params={"dates[]": date}, headers={"Authorization": key})
                if resp.status_code in (401, 429):
                    _key_pool.report_failure(key)
                resp.raise_for_status()
                games = resp.json().get("data") or []
        except Exception as e:
            return {"success": False, "error": f"balldontlie lookup failed: {e}"}
        if not games:
            return {"success": True, "date": date, "games": [], "note": "No real NBA games scheduled for this date"}
        return {"success": True, "date": date, "games": [
            {
                "home": g["home_team"]["full_name"], "away": g["visitor_team"]["full_name"],
                "home_score": g["home_team_score"], "away_score": g["visitor_team_score"],
                "status": g["status"],
            }
            for g in games
        ]}

    async def _team_lookup(self, name: str) -> Dict[str, Any]:
        key = _key_pool.get_key()
        if key is None:
            return {"success": False, "error": "BALLDONTLIE_API_KEY not configured -- register a free key at balldontlie.io"}
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_BASE}/teams", headers={"Authorization": key})
                if resp.status_code in (401, 429):
                    _key_pool.report_failure(key)
                resp.raise_for_status()
                teams = resp.json().get("data") or []
        except Exception as e:
            return {"success": False, "error": f"balldontlie lookup failed: {e}"}
        needle = name.lower()
        match = next((t for t in teams if needle in t["full_name"].lower() or needle in t["name"].lower()), None)
        if not match:
            return {"success": False, "error": f"No real NBA team found matching '{name}'"}
        return {
            "success": True,
            "full_name": match["full_name"],
            "abbreviation": match["abbreviation"],
            "city": match["city"],
            "conference": match["conference"],
            "division": match["division"],
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I give you real NBA game/team data via balldontlie.io -- never a fabricated score."
        )}
