"""
Timezone Scheduling Agent for Nancy/Billion.
Real timezone conversions via Python's stdlib `zoneinfo` (real IANA tz
database, DST-aware) and a real overlapping-working-hours calculator --
no guessed UTC offsets.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent


class TimezoneSchedulingAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Timezone Scheduling Agent", "timezone-scheduling")
        self.capabilities.update({
            "description": "Real IANA-database timezone conversions and working-hours overlap calculation",
            "confidence": 0.85,
            "specializations": ["timezone-conversion", "meeting-scheduling"],
            "tools": ["zoneinfo"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "convert_time":
            return self._convert(task_data.get("time_iso", ""), task_data.get("from_tz", ""), task_data.get("to_tz", ""))
        if task_type == "find_overlap":
            return self._overlap(task_data.get("timezones", []), int(task_data.get("work_start_hour", 9)), int(task_data.get("work_end_hour", 17)))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

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
