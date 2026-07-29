"""Tracks which real Google Calendar events have already been auto-prepped
(see main_new.py's _meeting_prep_loop) so a recurring background check never
preps the same upcoming meeting twice. Deliberately minimal: just a set of
event ids with a timestamp, pruned of anything old enough that the event
must be long over -- there's nothing else worth persisting here.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Set

STORE_PATH = Path(__file__).parent / "data" / "prepped_events.json"

# Prune entries older than this -- a prepped-event id has no reason to be
# remembered once its meeting could not possibly still be upcoming.
_MAX_AGE_SECONDS = 3 * 86400.0


def _load() -> Dict[str, float]:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: Dict[str, float]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data), encoding="utf-8")


def already_prepped(event_id: str) -> bool:
    return event_id in _load()


def mark_prepped(event_id: str) -> None:
    data = _load()
    now = time.time()
    data[event_id] = now
    # Prune while we're already writing -- no separate cleanup job needed.
    data = {eid: ts for eid, ts in data.items() if now - ts < _MAX_AGE_SECONDS}
    _save(data)
