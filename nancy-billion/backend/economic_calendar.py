"""Real live economic-release tracking: NFP, CPI, FOMC.

Data source: Financial Modeling Prep's economic-calendar API (real, live-
verified endpoint -- see the v3 URL below; both `financialmodelingprep.com/
api/v3/economic_calendar` and its newer `/stable/economic-calendar` sibling
returned a genuine "Invalid API KEY" JSON error on a direct probe, confirming
the endpoint is live -- but that probe could not see an *authenticated*
response, so the field names below (event/date/country/previous/estimate/
actual/change/changePercentage/impact) reflect FMP's long-documented v3
shape from public sources, not a verified live payload. Every field access
below uses .get() with a safe default specifically so a real but slightly
different shape degrades gracefully instead of crashing -- check this
module's logger output against your own first real fetch to confirm.

Architecture mirrors cron_store.py / webhooks_store.py: this module is a
pure data/polling layer with NO knowledge of Telegram or the WebSocket
manager (both live in main_new.py) -- avoids a circular import, and keeps
the actual notification-firing decision in the same place as every other
proactive push in this backend (_daily_briefing_loop, _cron_execution_loop).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from economic_calendar_store import economic_calendar_store

logger = logging.getLogger(__name__)

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"

# US-only; canonical key -> (display label, regex matched against the
# provider's raw event name, case-insensitive).
TRACKED_RELEASES: Dict[str, Dict[str, Any]] = {
    "nfp":  {"label": "NFP (Nonfarm Payrolls)", "pattern": re.compile(r"\bnon[\s-]?farm\b|\bnfp\b|\bemployment situation\b", re.I)},
    "cpi":  {"label": "CPI (Consumer Price Index)", "pattern": re.compile(r"\bcpi\b|\bconsumer price index\b", re.I)},
    "fomc": {"label": "FOMC Rate Decision", "pattern": re.compile(r"\bfomc\b|\bfederal funds rate\b|\binterest rate decision\b|\bfed interest rate\b", re.I)},
}

DAYS_BACK = 5     # keep a short trailing window so just-released prints stay in "recent"
DAYS_FORWARD = 45  # comfortably covers both monthly (NFP/CPI) and ~6-7-week (FOMC) cycles

POLL_INTERVAL_LOOSE_S = 900   # 15 min, most of the time
POLL_INTERVAL_TIGHT_S = 10    # inside a live release window
TIGHT_WINDOW_BEFORE_MIN = 20  # start tight polling 20 min before a scheduled release
TIGHT_WINDOW_AFTER_MIN = 15   # keep tight polling 15 min after, to catch a delayed print

_cache: List[Dict[str, Any]] = []
_warned_no_key = False


def classify(raw_event_name: str) -> Optional[str]:
    for key, meta in TRACKED_RELEASES.items():
        if meta["pattern"].search(raw_event_name or ""):
            return key
    return None


async def _fetch_raw(from_date: str, to_date: str) -> Optional[List[Dict[str, Any]]]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FMP_BASE_URL, params={"from": from_date, "to": to_date, "apikey": FMP_API_KEY})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "Error Message" in data:
                logger.warning("economic_calendar: FMP returned an error: %s", data["Error Message"])
                return None
            if not isinstance(data, list):
                logger.warning("economic_calendar: unexpected FMP response shape: %r", type(data))
                return None
            return data
    except Exception as e:
        logger.warning("economic_calendar: FMP fetch failed: %s", e)
        return None


def _normalize(raw: Dict[str, Any], canonical_key: str) -> Dict[str, Any]:
    return {
        "key_prefix": canonical_key,
        "event_name": TRACKED_RELEASES[canonical_key]["label"],
        "raw_event_name": raw.get("event", ""),
        "date": raw.get("date", ""),
        "country": raw.get("country", ""),
        "previous": raw.get("previous"),
        "estimate": raw.get("estimate"),
        "actual": raw.get("actual"),
        "change": raw.get("change"),
        "change_percent": raw.get("changePercentage"),
        "unit": raw.get("unit", ""),
        "impact": raw.get("impact", ""),
    }


async def poll_once() -> List[Dict[str, Any]]:
    """Fetch the calendar, update the cache + persisted store, and return
    just the events that *newly* got an actual value on this call (i.e.
    should be alerted on right now). Never fabricates data -- if the fetch
    fails or no key is configured, returns [] and leaves the existing cache
    untouched rather than clearing it."""
    global _warned_no_key

    if not FMP_API_KEY:
        if not _warned_no_key:
            logger.warning("economic_calendar: FMP_API_KEY not set -- economic calendar tracking is disabled until it is configured in .env")
            _warned_no_key = True
        return []

    now = datetime.now()
    from_date = (now - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")
    to_date = (now + timedelta(days=DAYS_FORWARD)).strftime("%Y-%m-%d")

    raw_events = await _fetch_raw(from_date, to_date)
    if raw_events is None:
        return []  # honest no-op on failure -- keep serving the last good cache

    newly_alerted: List[Dict[str, Any]] = []
    normalized: List[Dict[str, Any]] = []

    for raw in raw_events:
        country = str(raw.get("country", "")).upper()
        if country not in ("US", "USD", ""):
            continue
        canonical_key = classify(str(raw.get("event", "")))
        if canonical_key is None:
            continue

        event = _normalize(raw, canonical_key)
        normalized.append(event)

        tracked = economic_calendar_store.upsert(event)
        if tracked.actual is not None and not tracked.alerted:
            economic_calendar_store.mark_alerted(tracked.key)
            newly_alerted.append(event)

    economic_calendar_store.save()

    global _cache
    _cache = sorted(normalized, key=lambda e: e["date"])

    return newly_alerted


def get_cached_events() -> List[Dict[str, Any]]:
    return list(_cache)


def compose_alert_text(event: Dict[str, Any]) -> str:
    actual, estimate, previous = event.get("actual"), event.get("estimate"), event.get("previous")
    unit = event.get("unit") or ""

    direction = "in line with"
    if actual is not None and estimate is not None:
        if actual > estimate:
            direction = "above"
        elif actual < estimate:
            direction = "below"

    parts = [f"{event['event_name']} just released: {actual}{unit}"]
    if estimate is not None:
        parts.append(f"vs {estimate}{unit} expected ({direction} consensus)")
    if previous is not None:
        parts.append(f"previous: {previous}{unit}")
    return ", ".join(parts) + "."


def next_poll_interval_s() -> float:
    """Tight-poll (every 10s) if any cached event is scheduled to release
    within the next TIGHT_WINDOW_BEFORE_MIN minutes, or released within the
    last TIGHT_WINDOW_AFTER_MIN minutes (covers a delayed BLS/Fed print).
    Loose-poll (every 15 min) otherwise -- keeps well inside FMP's free-tier
    250 req/day limit (worst case: a handful of tight-window days per month,
    plus ~96/day loose polls the rest of the time)."""
    now = datetime.now()
    for event in _cache:
        try:
            event_dt = datetime.strptime(event["date"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, KeyError):
            continue
        delta_min = (event_dt - now).total_seconds() / 60.0
        if -TIGHT_WINDOW_AFTER_MIN <= delta_min <= TIGHT_WINDOW_BEFORE_MIN:
            return POLL_INTERVAL_TIGHT_S
    return POLL_INTERVAL_LOOSE_S
