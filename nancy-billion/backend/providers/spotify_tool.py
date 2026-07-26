"""Real Spotify Web API playback control -- ported from Hermes' Spotify
plugin. Uses the standard OAuth refresh-token flow: a one-time manual
authorization (documented in .env.example) produces SPOTIFY_REFRESH_TOKEN,
which this module exchanges for short-lived access tokens automatically on
every call (cached in-process until near expiry) -- no re-auth needed after
the initial setup.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

_cached_access_token: Optional[str] = None
_cached_expires_at: float = 0.0


def is_configured() -> bool:
    return bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET") and os.getenv("SPOTIFY_REFRESH_TOKEN"))


async def _get_access_token() -> Optional[str]:
    global _cached_access_token, _cached_expires_at
    if _cached_access_token and time.time() < _cached_expires_at - 30:
        return _cached_access_token

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                SPOTIFY_TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                auth=(client_id, client_secret),
            )
            resp.raise_for_status()
            data = resp.json()
            _cached_access_token = data["access_token"]
            _cached_expires_at = time.time() + data.get("expires_in", 3600)
            return _cached_access_token
    except Exception as e:
        logger.warning("spotify_tool: token refresh failed: %s", e)
        return None


async def _call(method: str, path: str, **kw: Any) -> Dict[str, Any]:
    token = await _get_access_token()
    if not token:
        return {"success": False, "error": "Spotify not configured or token refresh failed"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(method, f"{SPOTIFY_API_BASE}{path}", headers={"Authorization": f"Bearer {token}"}, **kw)
            if resp.status_code == 204:
                return {"success": True}
            resp.raise_for_status()
            return {"success": True, "data": resp.json() if resp.content else None}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"Spotify API error {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        logger.warning("spotify_tool: %s %s failed: %s", method, path, e)
        return {"success": False, "error": str(e)}


async def play(track_uri: Optional[str] = None) -> Dict[str, Any]:
    body = {"uris": [track_uri]} if track_uri else None
    return await _call("PUT", "/me/player/play", json=body)


async def pause() -> Dict[str, Any]:
    return await _call("PUT", "/me/player/pause")


async def next_track() -> Dict[str, Any]:
    return await _call("POST", "/me/player/next")


async def previous_track() -> Dict[str, Any]:
    return await _call("POST", "/me/player/previous")


async def search(query: str, type_: str = "track", limit: int = 5) -> Dict[str, Any]:
    return await _call("GET", "/search", params={"q": query, "type": type_, "limit": limit})


SPOTIFY_TOOLS = [
    {
        "name": "spotify_control",
        "description": "Control Spotify playback: play (optionally a specific track_uri), pause, next, previous, or search for a track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["play", "pause", "next", "previous", "search"]},
                "track_uri": {"type": "string", "description": "For action=play, a specific spotify:track:... URI (optional)."},
                "query": {"type": "string", "description": "For action=search."},
            },
            "required": ["action"],
        },
    },
]


async def handle_spotify_tool(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    action = tool_input.get("action")
    if action == "play":
        return await play(tool_input.get("track_uri"))
    if action == "pause":
        return await pause()
    if action == "next":
        return await next_track()
    if action == "previous":
        return await previous_track()
    if action == "search":
        return await search(tool_input.get("query", ""))
    return {"success": False, "error": f"Unknown action: {action}"}
