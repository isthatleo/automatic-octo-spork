"""
Timezone Scheduling Agent for Nancy/Billion.
Real timezone conversions via Python's stdlib `zoneinfo` (real IANA tz
database, DST-aware) and a real overlapping-working-hours calculator --
no guessed UTC offsets.

current_time is the fix for a real, confirmed-live failure: Billion had no
tool anywhere that answered "what time is it" -- the system prompt never
contained a live clock value (see main_new.py's _live_datetime_prompt_block
for the "here" half of that fix) and this agent previously only *converted*
a time the caller already supplied, with no way to look up "now" for an
arbitrary place. Resolves a city/country/zip code to a real IANA timezone
via geocoding (map_snapshot.py's Nominatim wrapper, the same one
geospatial_agent.py uses) + timezonefinder's offline lat/lon->tz lookup
(no API key, no network call for the timezone part itself), then reads the
real current time in that zone -- never an assumed/fabricated UTC offset.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base_specialized_agent import SpecializedAgent

_tz_finder = None


def _get_timezone_finder():
    """Lazy singleton -- TimezoneFinder() loads a real shapefile-derived
    dataset into memory on construction (a genuine, if brief, cost), so
    this is built once per process and reused, not once per request."""
    global _tz_finder
    if _tz_finder is None:
        from timezonefinder import TimezoneFinder
        _tz_finder = TimezoneFinder()
    return _tz_finder


class TimezoneSchedulingAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Timezone Scheduling Agent", "timezone-scheduling")
        self.capabilities.update({
            "description": "Real current time anywhere (city/country/zip -> real IANA timezone), real timezone conversions, and working-hours overlap calculation",
            "confidence": 0.85,
            "specializations": ["current-time", "timezone-conversion", "meeting-scheduling"],
            "tools": ["zoneinfo", "timezonefinder", "nominatim"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "current_time":
            return await self._current_time(task_data.get("place"))
        if task_type == "convert_time":
            return self._convert(task_data.get("time_iso", ""), task_data.get("from_tz", ""), task_data.get("to_tz", ""))
        if task_type == "find_overlap":
            return self._overlap(task_data.get("timezones", []), int(task_data.get("work_start_hour", 9)), int(task_data.get("work_end_hour", 17)))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    async def _current_time(self, place: Optional[str]) -> Dict[str, Any]:
        if not place:
            now_here = datetime.now().astimezone()
            return {
                "success": True,
                "place": "here (user's local time)",
                "iso": now_here.isoformat(),
                "formatted": now_here.strftime("%A, %B %d, %Y, %I:%M %p (%Z)"),
            }
        from map_snapshot import geocode
        result = await geocode(place)
        if result is None:
            return {"success": False, "error": f"Could not geocode '{place}' -- not a real, resolvable place"}
        try:
            tf = _get_timezone_finder()
            tz_name = tf.timezone_at(lat=result.lat, lng=result.lon)
        except Exception as e:
            return {"success": False, "error": f"Timezone lookup failed: {e}"}
        if not tz_name:
            return {"success": False, "error": f"Could not resolve a real timezone for '{place}' (likely open ocean/no landmass match)"}
        from zoneinfo import ZoneInfo
        now_there = datetime.now(ZoneInfo(tz_name))
        return {
            "success": True,
            "place": result.display_name,
            "timezone": tz_name,
            "iso": now_there.isoformat(),
            "formatted": now_there.strftime("%A, %B %d, %Y, %I:%M %p (%Z)"),
        }

    def _convert(self, time_iso: str, from_tz: str, to_tz: str) -> Dict[str, Any]:
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.fromisoformat(time_iso).replace(tzinfo=ZoneInfo(from_tz))
            converted = dt.astimezone(ZoneInfo(to_tz))
            return {"success": True, "original": dt.isoformat(), "converted": converted.isoformat(), "to_tz": to_tz}
        except Exception as e:
            return {"success": False, "error": f"Invalid time/timezone (use IANA names like 'Europe/London'): {e}"}

    def _overlap(self, timezones: List[str], work_start: int, work_end: int) -> Dict[str, Any]:
        """Real overlap: converts each timezone's working-hours window (in
        its own local time, today's date as the reference) into UTC minutes,
        then intersects all windows."""
        if len(timezones) < 2:
            return {"success": False, "error": "Provide at least 2 IANA timezone names"}
        try:
            from zoneinfo import ZoneInfo
            today = datetime.now().date()
            windows_utc = []
            for tz_name in timezones:
                tz = ZoneInfo(tz_name)
                start_local = datetime(today.year, today.month, today.day, work_start, tzinfo=tz)
                end_local = datetime(today.year, today.month, today.day, work_end, tzinfo=tz)
                start_utc = start_local.astimezone(ZoneInfo("UTC"))
                end_utc = end_local.astimezone(ZoneInfo("UTC"))
                windows_utc.append((start_utc, end_utc))

            overlap_start = max(w[0] for w in windows_utc)
            overlap_end = min(w[1] for w in windows_utc)
            if overlap_start >= overlap_end:
                return {"success": True, "has_overlap": False, "timezones": timezones}
            return {
                "success": True, "has_overlap": True, "timezones": timezones,
                "overlap_start_utc": overlap_start.isoformat(), "overlap_end_utc": overlap_end.isoformat(),
                "overlap_duration_hours": round((overlap_end - overlap_start) / timedelta(hours=1), 2),
            }
        except Exception as e:
            return {"success": False, "error": f"Invalid timezone name: {e}"}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I do real IANA timezone conversions and find real working-hours overlap windows across timezones."
        )}
