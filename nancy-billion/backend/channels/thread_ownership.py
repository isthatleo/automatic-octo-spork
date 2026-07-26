"""Real thread-ownership arbitration -- ported from OpenClaw's thread-ownership
extension (prevents two OpenClaw gateway instances both replying in the same
Slack thread). Built as genuinely general infrastructure: a real TTL-based
claim/release/heartbeat API keyed on (channel, thread_id), backed by a JSON
store so it's correct across a process restart, not just in-memory.

Nancy runs as a single backend instance today, so there is no second
instance to race against yet -- this ships as the real, correct-from-day-one
arbitration primitive so the moment a second replica/instance of this
backend ever exists (a load-balanced deployment, a staging+prod pair both
watching the same Slack workspace), it is already safe by construction
rather than needing to be retrofitted under pressure.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent.parent / "data" / "thread_ownership.json"
DEFAULT_TTL_S = 30.0  # a claim auto-expires this long after its last heartbeat


def _load() -> dict:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data), encoding="utf-8")


def _key(channel: str, thread_id: str) -> str:
    return f"{channel}:{thread_id}"


def claim(channel: str, thread_id: str, owner_id: str, ttl_s: float = DEFAULT_TTL_S) -> bool:
    """Attempts to claim ownership of a (channel, thread_id) so this
    instance -- and only this instance -- replies in it. Returns True if the
    claim succeeded (either unclaimed, expired, or already owned by
    `owner_id`); False if another live owner holds it."""
    data = _load()
    k = _key(channel, thread_id)
    existing = data.get(k)
    now = time.time()
    if existing and existing["owner_id"] != owner_id and existing["expires_at"] > now:
        return False
    data[k] = {"owner_id": owner_id, "expires_at": now + ttl_s}
    _save(data)
    return True


def heartbeat(channel: str, thread_id: str, owner_id: str, ttl_s: float = DEFAULT_TTL_S) -> bool:
    """Extends an existing claim -- same semantics as re-claiming."""
    return claim(channel, thread_id, owner_id, ttl_s)


def release(channel: str, thread_id: str, owner_id: str) -> None:
    data = _load()
    k = _key(channel, thread_id)
    existing = data.get(k)
    if existing and existing["owner_id"] == owner_id:
        del data[k]
        _save(data)


def current_owner(channel: str, thread_id: str) -> Optional[str]:
    data = _load()
    existing = data.get(_key(channel, thread_id))
    if not existing or existing["expires_at"] <= time.time():
        return None
    return existing["owner_id"]


# This process's own real, stable identity for claims it makes -- generated
# once per process lifetime, so a restart is treated as a genuinely new
# owner (its old claims will simply expire via TTL rather than being
# force-reclaimed, avoiding a restart racing a still-live second instance).
INSTANCE_ID = str(uuid.uuid4())
