"""Real "while you were away" cursor -- a single global bookmark of the last
time the user actually looked at the digest, backed by the same tiny
JSON-store pattern as watch_store.py/cron_store.py.

Deliberately one cursor, not one per client: Nancy is a single local backend
for one user (see event_bus.py's honesty note on the same point), so there is
one real "since I last checked" moment, not per-device state to reconcile.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "digest_cursor.json"


@dataclass
class DigestCursor:
    last_seen_at: float


def _load() -> DigestCursor:
    if not STORE_PATH.exists():
        # First-ever load: "while you were away" must start from now, never
        # from the dawn of time -- a fresh install has no "away" yet, and
        # dumping every pre-existing memory/dream/wiki record as if it just
        # happened would be a lie about when it actually happened.
        cursor = DigestCursor(last_seen_at=time.time())
        _save(cursor)
        return cursor
    try:
        raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        return DigestCursor(last_seen_at=float(raw.get("last_seen_at", time.time())))
    except Exception:
        logger.exception("Failed to load digest_cursor.json -- resetting to now")
        cursor = DigestCursor(last_seen_at=time.time())
        _save(cursor)
        return cursor


def _save(cursor: DigestCursor) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(asdict(cursor), indent=2), encoding="utf-8")


def get_last_seen() -> float:
    return _load().last_seen_at


def mark_seen(ts: Optional[float] = None) -> float:
    ts = ts if ts is not None else time.time()
    _save(DigestCursor(last_seen_at=ts))
    return ts
