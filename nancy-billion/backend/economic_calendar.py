"""Real live economic-release tracking: NFP, CPI, FOMC.

Data source: FRED (Federal Reserve Bank of St. Louis), api.stlouisfed.org --
free self-serve API key (fred.stlouisfed.org/docs/api/api_key.html), no
paid tier required. Two real FRED capabilities combine to build this:

  1. `fred/release/dates` -- the actual, government-published release
     calendar for a given release_id (50 = Employment Situation/NFP,
     10 = Consumer Price Index/CPI), including future scheduled dates
     when `include_release_dates_with_no_data=true` is passed.
  2. `fred/series/observations` -- the actual historical data for a series
     (PAYEMS = nonfarm payroll level, CPIAUCSL = CPI index, DFEDTARU =
     Fed funds target rate upper bound), used to detect the moment a new
     value posts and to compute the real MoM/YoY change traders quote.

Honesty note: FRED has no consensus/forecast data at all (nothing does,
free -- this project tried Financial Modeling Prep first; its economic-
calendar endpoint turned out to require a paid plan once tested against a
real account, confirmed via direct probe, not assumed). So every event
here has `estimate: None` always -- this reports the real print and the
real previous value, with no invented "vs consensus" framing.

FOMC has no FRED release-calendar equivalent (it isn't data-release shaped
the same way), so its *schedule* is the Fed's own officially published 2026
meeting calendar (federalreserve.gov/monetarypolicy/fomccalendars.htm,
statements released 14:00 ET on the second day of each meeting) -- real
public dates, not fabricated. Its *actual* value is detected by watching
DFEDTARU (Federal Funds Target Range - Upper Limit), a real daily FRED
series that step-changes exactly on a rate-decision day.

Architecture mirrors cron_store.py / webhooks_store.py: this module is a
pure data/polling layer with NO knowledge of Telegram or the WebSocket
manager (both live in main_new.py) -- avoids a circular import, and keeps
the actual notification-firing decision in the same place as every other
proactive push in this backend (_daily_briefing_loop, _cron_execution_loop).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from economic_calendar_store import economic_calendar_store

logger = logging.getLogger(__name__)

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Real, officially-published 2026 FOMC meeting schedule (source:
# federalreserve.gov/monetarypolicy/fomccalendars.htm, verified 2026-07).
# Update this list once the Fed publishes next year's calendar.
FOMC_2026_MEETING_DATES: List[str] = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

TRACKED_RELEASES: Dict[str, Dict[str, Any]] = {
    "nfp":  {"label": "NFP (Nonfarm Payrolls, MoM change)", "release_id": 50, "series_id": "PAYEMS",    "unit": "K", "release_time_et": "08:30:00"},
    "cpi":  {"label": "CPI (Consumer Price Index, YoY)",    "release_id": 10, "series_id": "CPIAUCSL",  "unit": "%", "release_time_et": "08:30:00"},
    "fomc": {"label": "FOMC Rate Decision",                 "release_id": None, "series_id": "DFEDTARU", "unit": "%", "release_time_et": "14:00:00"},
}

POLL_INTERVAL_LOOSE_S = 900   # 15 min, most of the time
POLL_INTERVAL_TIGHT_S = 10    # inside a live release window
TIGHT_WINDOW_BEFORE_MIN = 20  # start tight polling 20 min before a scheduled release
TIGHT_WINDOW_AFTER_MIN = 15   # keep tight polling 15 min after, to catch a delayed print

_cache: List[Dict[str, Any]] = []
_warned_no_key = False


async def _fred_get(path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    import httpx
    query = {**params, "api_key": FRED_API_KEY, "file_type": "json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{FRED_BASE_URL}/{path}", params=query)
            resp.raise_for_status()
            data = resp.json()
            if "error_code" in data:
                logger.warning("economic_calendar: FRED error on %s: %s", path, data.get("error_message"))
                return None
            return data
    except Exception as e:
        logger.warning("economic_calendar: FRED fetch failed (%s): %s", path, e)
        return None


async def _poll_fred_release(canonical_key: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Returns (most_recent_release_event_or_None, next_upcoming_event_or_None)
    for a FRED release-calendar-backed indicator (nfp/cpi)."""
    meta = TRACKED_RELEASES[canonical_key]

    dates_data = await _fred_get("release/dates", {
        "release_id": meta["release_id"],
        "include_release_dates_with_no_data": "true",
        "sort_order": "desc",
        "limit": 20,
    })
    obs_data = await _fred_get("series/observations", {
        "series_id": meta["series_id"],
        "sort_order": "desc",
        "limit": 14,
    })
    if dates_data is None or obs_data is None:
        return None, None

    today_str = datetime.now().strftime("%Y-%m-%d")
    all_dates = sorted((d["date"] for d in dates_data.get("release_dates", [])), reverse=True)
    past_dates = [d for d in all_dates if d <= today_str]
    future_dates = [d for d in all_dates if d > today_str]

    observations = [o for o in obs_data.get("observations", []) if o.get("value") not in (None, ".")]
    observations.sort(key=lambda o: o["date"], reverse=True)

    recent_event: Optional[Dict[str, Any]] = None
    if past_dates and observations:
        latest_val = float(observations[0]["value"])
        previous_val = float(observations[1]["value"]) if len(observations) > 1 else None
        actual: Optional[float]
        previous_display: Optional[float]

        if canonical_key == "cpi" and len(observations) >= 13:
            yoy_base = float(observations[12]["value"])
            actual = round((latest_val / yoy_base - 1.0) * 100.0, 2)
            previous_display = None
            if previous_val is not None and len(observations) >= 14:
                prev_yoy_base = float(observations[13]["value"])
                previous_display = round((previous_val / prev_yoy_base - 1.0) * 100.0, 2)
        elif canonical_key == "nfp" and previous_val is not None:
            actual = round(latest_val - previous_val, 0)
            previous_display = round(previous_val - float(observations[2]["value"]), 0) if len(observations) > 2 else None
        else:
            actual = latest_val
            previous_display = previous_val

        recent_event = {
            "key_prefix": canonical_key, "event_name": meta["label"],
            "date": f"{past_dates[0]} {meta['release_time_et']}",
            "country": "US", "previous": previous_display, "estimate": None, "actual": actual,
            "change": None, "change_percent": None, "unit": meta["unit"], "impact": "High",
        }

    upcoming_event: Optional[Dict[str, Any]] = None
    if future_dates:
        upcoming_event = {
            "key_prefix": canonical_key, "event_name": meta["label"],
            "date": f"{future_dates[-1]} {meta['release_time_et']}",  # nearest future (smallest date, list is descending)
            "country": "US", "previous": None, "estimate": None, "actual": None,
            "change": None, "change_percent": None, "unit": meta["unit"], "impact": "High",
        }

    return recent_event, upcoming_event


def _fomc_upcoming_event() -> Optional[Dict[str, Any]]:
    meta = TRACKED_RELEASES["fomc"]
    today_str = datetime.now().strftime("%Y-%m-%d")
    future = sorted(d for d in FOMC_2026_MEETING_DATES if d > today_str)
    if not future:
        return None
    return {
        "key_prefix": "fomc", "event_name": meta["label"],
        "date": f"{future[0]} {meta['release_time_et']}",
        "country": "US", "previous": None, "estimate": None, "actual": None,
        "change": None, "change_percent": None, "unit": meta["unit"], "impact": "High",
    }


async def _fomc_recent_event() -> Optional[Dict[str, Any]]:
    """Watches DFEDTARU (a real daily series) for a step-change -- that IS
    a rate decision, whether or not it fell on a hardcoded meeting date
    (inter-meeting emergency moves are rare but real)."""
    meta = TRACKED_RELEASES["fomc"]
    obs_data = await _fred_get("series/observations", {"series_id": meta["series_id"], "sort_order": "desc", "limit": 5})
    if obs_data is None:
        return None
    observations = [o for o in obs_data.get("observations", []) if o.get("value") not in (None, ".")]
    if len(observations) < 2:
        return None

    latest, previous = observations[0], observations[1]
    latest_val, previous_val = float(latest["value"]), float(previous["value"])
    if latest_val == previous_val:
        return None  # no change -- nothing "just happened"

    return {
        "key_prefix": "fomc", "event_name": meta["label"],
        "date": f"{latest['date']} {meta['release_time_et']}",
        "country": "US", "previous": previous_val, "estimate": None, "actual": latest_val,
        "change": round(latest_val - previous_val, 2), "change_percent": None,
        "unit": meta["unit"], "impact": "High",
    }


async def poll_once() -> List[Dict[str, Any]]:
    """Fetch NFP/CPI/FOMC state, update the cache + persisted store, and
    return just the events that *newly* got an actual value on this call
    (i.e. should be alerted on right now). Never fabricates data -- if a
    fetch fails or no key is configured, affected events are simply
    skipped rather than backfilled with an invented figure."""
    global _warned_no_key, _cache

    if not FRED_API_KEY:
        if not _warned_no_key:
            logger.warning("economic_calendar: FRED_API_KEY not set -- economic calendar tracking is disabled until it is configured in .env")
            _warned_no_key = True
        return []

    normalized: List[Dict[str, Any]] = []
    newly_alerted: List[Dict[str, Any]] = []

    for key in ("nfp", "cpi"):
        recent, upcoming = await _poll_fred_release(key)
        for event in (recent, upcoming):
            if event is None:
                continue
            normalized.append(event)
            tracked = economic_calendar_store.upsert(event)
            if tracked.actual is not None and not tracked.alerted:
                economic_calendar_store.mark_alerted(tracked.key)
                newly_alerted.append(event)

    fomc_upcoming = _fomc_upcoming_event()
    if fomc_upcoming:
        normalized.append(fomc_upcoming)

    fomc_recent = await _fomc_recent_event()
    if fomc_recent:
        normalized.append(fomc_recent)
        tracked = economic_calendar_store.upsert(fomc_recent)
        if tracked.actual is not None and not tracked.alerted:
            economic_calendar_store.mark_alerted(tracked.key)
            newly_alerted.append(fomc_recent)

    economic_calendar_store.save()
    _cache = sorted(normalized, key=lambda e: e["date"])
    return newly_alerted


def get_cached_events() -> List[Dict[str, Any]]:
    return list(_cache)


def compose_alert_text(event: Dict[str, Any]) -> str:
    """No 'vs consensus' framing -- FRED has no forecast data, so this
    reports the real print and the real previous value only."""
    actual, previous = event.get("actual"), event.get("previous")
    unit = event.get("unit") or ""

    parts = [f"{event['event_name']} just released: {actual}{unit}"]
    if previous is not None:
        parts.append(f"previous: {previous}{unit}")
    change = event.get("change")
    if change is not None:
        parts.append(f"{change:+g}{unit} change")
    return ", ".join(parts) + "."


def next_poll_interval_s() -> float:
    """Tight-poll (every 10s) if any cached event is scheduled to release
    within the next TIGHT_WINDOW_BEFORE_MIN minutes, or released within the
    last TIGHT_WINDOW_AFTER_MIN minutes (covers a delayed BLS/Fed print).
    Loose-poll (every 15 min) otherwise. FRED's free tier allows a generous
    ~120 requests/minute, so this cadence is nowhere near any rate limit."""
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
