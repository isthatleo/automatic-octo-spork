"""
Music Knowledge Agent for Nancy/Billion.

Real artist/discography metadata ONLY -- the MusicBrainz API
(musicbrainz.org/ws/2), fully free and keyless: no API key, no
registration, just a required descriptive User-Agent header (MusicBrainz's
own usage policy) and a real 1 req/sec rate limit this agent respects.
Distinct from audio_analysis_agent.py, which is signal processing (analyzing
actual audio), not music knowledge -- this agent never touches audio, only
structured artist/release/recording facts.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

_MB_BASE = "https://musicbrainz.org/ws/2"
_USER_AGENT = "Nancy-Billion-MusicKnowledgeAgent/1.0 (https://github.com/isthatleo/automatic-octo-spork)"
_last_request_at = 0.0


async def _rate_limited_get(client: Any, url: str, params: Dict[str, Any]) -> Any:
    """MusicBrainz's real usage policy caps unauthenticated clients at
    1 req/sec -- a burst above that gets you temporarily blocked, not just
    slowed down, so this is a real constraint to respect, not a courtesy."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < 1.0:
        await asyncio.sleep(1.0 - elapsed)
    resp = await client.get(url, params=params, headers={"User-Agent": _USER_AGENT})
    _last_request_at = time.monotonic()
    return resp


class MusicKnowledgeAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Music Knowledge Agent", "music-knowledge")
        self.capabilities.update({
            "description": "Real artist/discography metadata via MusicBrainz -- credits, releases, recordings, never fabricated",
            "confidence": 0.75,
            "specializations": ["artist-lookup", "discography"],
            "tools": ["musicbrainz"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "artist_lookup":
            name = (task_data.get("name") or task_data.get("artist") or "").strip()
            if not name:
                return {"success": False, "error": "artist_lookup requires a 'name'"}
            return await self._artist_lookup(name)
        if task_type == "discography":
            name = (task_data.get("name") or task_data.get("artist") or "").strip()
            if not name:
                return {"success": False, "error": "discography requires a 'name'"}
            return await self._discography(name)
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    async def _find_artist_mbid(self, client: Any, name: str) -> Dict[str, Any]:
        resp = await _rate_limited_get(client, f"{_MB_BASE}/artist/", {"query": name, "fmt": "json", "limit": 1})
        resp.raise_for_status()
        artists = resp.json().get("artists") or []
        if not artists:
            return {}
        return artists[0]

    async def _artist_lookup(self, name: str) -> Dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                artist = await self._find_artist_mbid(client, name)
                if not artist:
                    return {"success": False, "error": f"No real MusicBrainz record found for '{name}'"}
                return {
                    "success": True,
                    "name": artist.get("name"),
                    "type": artist.get("type"),
                    "country": artist.get("country"),
                    "disambiguation": artist.get("disambiguation"),
                    "life_span": artist.get("life-span"),
                    "tags": [t.get("name") for t in (artist.get("tags") or [])],
                }
        except Exception as e:
            return {"success": False, "error": f"MusicBrainz lookup failed: {e}"}

    async def _discography(self, name: str) -> Dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                artist = await self._find_artist_mbid(client, name)
                if not artist:
                    return {"success": False, "error": f"No real MusicBrainz record found for '{name}'"}
                mbid = artist["id"]
                resp = await _rate_limited_get(
                    client, f"{_MB_BASE}/release-group/",
                    {"artist": mbid, "fmt": "json", "limit": 50},
                )
                resp.raise_for_status()
                groups = resp.json().get("release-groups") or []
        except Exception as e:
            return {"success": False, "error": f"MusicBrainz lookup failed: {e}"}
        if not groups:
            return {"success": False, "error": f"MusicBrainz has no real release data for '{name}'"}
        releases = sorted(
            (
                {"title": g.get("title"), "type": g.get("primary-type"), "first_release_date": g.get("first-release-date")}
                for g in groups
            ),
            key=lambda r: r["first_release_date"] or "",
        )
        return {"success": True, "artist": artist.get("name"), "release_count": len(releases), "releases": releases}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I give you real artist and discography data via MusicBrainz -- never a fabricated credit or release date."
        )}
