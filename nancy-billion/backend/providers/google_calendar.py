"""Real Google Calendar integration -- same OAuth refresh-token idiom as
spotify_tool.py: a one-time manual authorization (documented in
.env.example) produces GOOGLE_CALENDAR_REFRESH_TOKEN, which this module
exchanges for short-lived access tokens automatically on every call (cached
in-process until near expiry). Lets Billion actually see the user's real
schedule, create/delete real events, and flag real conflicts -- not
connected to anything before this.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

_cached_access_token: Optional[str] = None
_cached_expires_at: float = 0.0


def is_configured() -> bool:
    return bool(
        os.getenv("GOOGLE_CALENDAR_CLIENT_ID")
        and os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET")
        and os.getenv("GOOGLE_CALENDAR_REFRESH_TOKEN")
    )


async def _get_access_token() -> Optional[str]:
    global _cached_access_token, _cached_expires_at
    if _cached_access_token and time.time() < _cached_expires_at - 30:
        return _cached_access_token

    client_id = os.getenv("GOOGLE_CALENDAR_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_CALENDAR_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token", "refresh_token": refresh_token,
                    "client_id": client_id, "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            _cached_access_token = data["access_token"]
            _cached_expires_at = time.time() + data.get("expires_in", 3600)
            return _cached_access_token
    except Exception as e:
        logger.warning("google_calendar: token refresh failed: %s", e)
        return None


async def _call(method: str, path: str, **kw: Any) -> Dict[str, Any]:
    token = await _get_access_token()
    if not token:
        return {"success": False, "error": "Google Calendar not configured or token refresh failed"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(
                method, f"{CALENDAR_API_BASE}{path}", headers={"Authorization": f"Bearer {token}"}, **kw
            )
            if resp.status_code == 204:
                return {"success": True}
            resp.raise_for_status()
            return {"success": True, "data": resp.json() if resp.content else None}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"Google Calendar API error {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:
        logger.warning("google_calendar: %s %s failed: %s", method, path, e)
        return {"success": False, "error": str(e)}


def _simplify_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw.get("id"),
        "summary": raw.get("summary"),
        "start": (raw.get("start") or {}).get("dateTime") or (raw.get("start") or {}).get("date"),
        "end": (raw.get("end") or {}).get("dateTime") or (raw.get("end") or {}).get("date"),
        "location": raw.get("location"),
        "description": raw.get("description"),
        "html_link": raw.get("htmlLink"),
    }


async def list_events(
    time_min: Optional[str] = None, time_max: Optional[str] = None,
    max_results: int = 10, calendar_id: str = "primary",
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    params = {
        "timeMin": time_min or now.isoformat(),
        "timeMax": time_max or (now + timedelta(days=7)).isoformat(),
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    result = await _call("GET", f"/calendars/{calendar_id}/events", params=params)
    if not result.get("success"):
        return result
    events = [_simplify_event(e) for e in result["data"].get("items", [])]
    return {"success": True, "events": events}


async def check_conflicts(start: str, end: str, calendar_id: str = "primary") -> Dict[str, Any]:
    result = await list_events(time_min=start, time_max=end, max_results=50, calendar_id=calendar_id)
    if not result.get("success"):
        return result
    return {"success": True, "conflicts": result["events"], "has_conflict": len(result["events"]) > 0}


async def create_event(
    summary: str, start: str, end: str, description: Optional[str] = None,
    location: Optional[str] = None, timezone_name: Optional[str] = None, calendar_id: str = "primary",
) -> Dict[str, Any]:
    start_field: Dict[str, Any] = {"dateTime": start}
    end_field: Dict[str, Any] = {"dateTime": end}
    if timezone_name:
        start_field["timeZone"] = timezone_name
        end_field["timeZone"] = timezone_name
    body = {"summary": summary, "start": start_field, "end": end_field}
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    result = await _call("POST", f"/calendars/{calendar_id}/events", json=body)
    if not result.get("success"):
        return result
    return {"success": True, "event": _simplify_event(result["data"])}


async def delete_event(event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
    return await _call("DELETE", f"/calendars/{calendar_id}/events/{event_id}")


CALENDAR_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "list_calendar_events",
        "description": "List the user's real upcoming Google Calendar events. Defaults to the next 7 days if no range given.",
        "input_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "RFC3339 start of range, e.g. '2025-01-15T00:00:00Z'. Defaults to now."},
                "time_max": {"type": "string", "description": "RFC3339 end of range. Defaults to 7 days from now."},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "check_calendar_conflicts",
        "description": "Check whether a proposed time range overlaps any real existing event -- use before create_calendar_event when a specific slot matters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "RFC3339 datetime."},
                "end": {"type": "string", "description": "RFC3339 datetime."},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Create a real event on the user's Google Calendar. Requires the user's explicit approval "
            "first. Prefer checking check_calendar_conflicts first when the exact time matters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start": {"type": "string", "description": "RFC3339 datetime, e.g. '2025-01-15T14:00:00-05:00'."},
                "end": {"type": "string", "description": "RFC3339 datetime."},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "timezone_name": {"type": "string", "description": "IANA timezone, e.g. 'America/New_York', if start/end lack an explicit offset."},
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete a real event from the user's Google Calendar. Requires the user's explicit approval first.",
        "input_schema": {"type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]},
    },
]
