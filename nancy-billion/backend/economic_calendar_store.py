"""Real, persisted "have we already alerted on this release" tracking.

Same JSON-file persistence pattern as webhooks_store.py/cron_store.py. Exists
so a backend restart during a live release window doesn't re-fire the same
Telegram/voice alert twice, and so the frontend's "recent" list survives a
restart instead of going blank until the next fetch cycle.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "economic_calendar.json"


@dataclass
class TrackedEvent:
    # Composite key: f"{event_name}|{date}" -- unique per scheduled release.
    key: str
    event_name: str
    date: str  # ISO-ish "YYYY-MM-DD HH:MM:SS" as returned by the provider
    country: str
    previous: Optional[float] = None
    estimate: Optional[float] = None
    actual: Optional[float] = None
    unit: Optional[str] = None
    impact: Optional[str] = None
    alerted: bool = False
    cached_at: float = field(default_factory=time.time)


class EconomicCalendarStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._events: Dict[str, TrackedEvent] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                ev = TrackedEvent(**item)
                self._events[ev.key] = ev
        except Exception:
            logger.exception("Failed to load economic_calendar.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep only the most recent 500 entries so this file doesn't grow forever.
        entries = sorted(self._events.values(), key=lambda e: e.cached_at, reverse=True)[:500]
        self._events = {e.key: e for e in entries}
        self.path.write_text(json.dumps([asdict(e) for e in entries], indent=2), encoding="utf-8")

    def upsert(self, raw_event: Dict[str, Any]) -> TrackedEvent:
        """Insert/update from a freshly-fetched provider record. Returns the
        stored TrackedEvent (existing 'alerted' flag preserved if already set)."""
        key = f"{raw_event['event_name']}|{raw_event['date']}"
        existing = self._events.get(key)
        ev = TrackedEvent(
            key=key,
            event_name=raw_event["event_name"],
            date=raw_event["date"],
            country=raw_event.get("country", ""),
            previous=raw_event.get("previous"),
            estimate=raw_event.get("estimate"),
            actual=raw_event.get("actual"),
            unit=raw_event.get("unit"),
            impact=raw_event.get("impact"),
            alerted=existing.alerted if existing else False,
        )
        self._events[key] = ev
        return ev

    def mark_alerted(self, key: str) -> None:
        if key in self._events:
            self._events[key].alerted = True
            self._save()

    def list_all(self) -> List[TrackedEvent]:
        return sorted(self._events.values(), key=lambda e: e.date)

    def save(self) -> None:
        self._save()


economic_calendar_store = EconomicCalendarStore()
