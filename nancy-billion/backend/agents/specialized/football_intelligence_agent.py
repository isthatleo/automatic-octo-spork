"""
Football (Soccer) Intelligence Agent for Nancy/Billion.

Real team/standings/fixture data via TheSportsDB's free, no-registration
community test key ("123") -- api.thesportsdb.com's own documentation is
explicit that this shared free key has limited team-search coverage (its
own example notes "Free tier limited to just 'Arsenal'"), so a search that
comes back empty is reported honestly as "not found on the free tier"
rather than silently retried or faked. FOOTBALL_DATA_API_KEY (a real,
separately-registered free key from football-data.org, covering 12 major
competitions with better live score/table coverage) is used automatically
as a second source when configured -- same "optional upgrade path,
zero-cost to leave unset" idiom as providers/registry.py's vendor pattern,
just inline here since this is a single-agent concern rather than a shared
capability category.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

_THESPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/123"
_FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

# TheSportsDB's own documented league id for the English Premier League --
# the one league confirmed against their live docs, used as the default
# when a caller doesn't supply one rather than guessing others.
_DEFAULT_LEAGUE_ID = "4328"


class FootballIntelligenceAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Football Intelligence Agent", "football-intelligence")
        self.capabilities.update({
            "description": "Real team/standings/fixture data via TheSportsDB (free tier, limited search coverage) and optionally football-data.org if FOOTBALL_DATA_API_KEY is set -- never fabricated",
            "confidence": 0.65,
            "specializations": ["standings", "fixtures", "team-lookup"],
            "tools": ["thesportsdb", "football_data_org"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "standings":
            return await self._standings(task_data.get("league_id", _DEFAULT_LEAGUE_ID))
        if task_type == "today_fixtures":
            return await self._today_fixtures(task_data.get("league_id", _DEFAULT_LEAGUE_ID))
        if task_type == "team_lookup":
            name = (task_data.get("name") or task_data.get("team") or "").strip()
            if not name:
                return {"success": False, "error": "team_lookup requires a 'name'"}
            return await self._team_lookup(name)
        if task_type == "status":
            return {"success": True, "status": "ready", "football_data_org_configured": bool(os.getenv("FOOTBALL_DATA_API_KEY"))}
        return await self._general(task_data)

    async def _standings(self, league_id: str) -> Dict[str, Any]:
        api_key = os.getenv("FOOTBALL_DATA_API_KEY")
        if api_key:
            import httpx
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{_FOOTBALL_DATA_BASE}/competitions/{league_id}/standings",
                        headers={"X-Auth-Token": api_key},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                table = (data.get("standings") or [{}])[0].get("table") or []
                if table:
                    return {"success": True, "source": "football-data.org", "table": [
                        {"position": r["position"], "team": r["team"]["name"], "points": r["points"], "played": r["playedGames"]}
                        for r in table
                    ]}
            except Exception:
                pass  # fall through to TheSportsDB below rather than fail outright
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_THESPORTSDB_BASE}/lookuptable.php", params={"l": league_id, "s": "2024-2025"})
                resp.raise_for_status()
                table = resp.json().get("table") or []
        except Exception as e:
            return {"success": False, "error": f"TheSportsDB lookup failed: {e}"}
        if not table:
            return {"success": False, "error": "No real standings data available on the free tier for this league"}
        return {"success": True, "source": "thesportsdb", "table": [
            {"position": r.get("intRank"), "team": r.get("strTeam"), "points": r.get("intPoints"), "played": r.get("intPlayed")}
            for r in table
        ]}

    async def _today_fixtures(self, league_id: str) -> Dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_THESPORTSDB_BASE}/eventsnextleague.php", params={"id": league_id})
                resp.raise_for_status()
                events = resp.json().get("events") or []
        except Exception as e:
            return {"success": False, "error": f"TheSportsDB lookup failed: {e}"}
        if not events:
            return {"success": False, "error": "No real upcoming fixtures available on the free tier for this league"}
        return {"success": True, "fixtures": [
            {"date": e.get("dateEvent"), "time": e.get("strTime"), "home": e.get("strHomeTeam"), "away": e.get("strAwayTeam")}
            for e in events[:15]
        ]}

    async def _team_lookup(self, name: str) -> Dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_THESPORTSDB_BASE}/searchteams.php", params={"t": name})
                resp.raise_for_status()
                teams = resp.json().get("teams") or []
        except Exception as e:
            return {"success": False, "error": f"TheSportsDB lookup failed: {e}"}
        if not teams:
            return {"success": False, "error": f"'{name}' not found -- TheSportsDB's free shared key has limited search coverage"}
        t = teams[0]
        return {
            "success": True,
            "name": t.get("strTeam"),
            "league": t.get("strLeague"),
            "stadium": t.get("strStadium"),
            "founded": t.get("intFormedYear"),
            "country": t.get("strCountry"),
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I give you real standings/fixture/team data via TheSportsDB (and football-data.org if configured) -- "
            "never a fabricated score or table position."
        )}
