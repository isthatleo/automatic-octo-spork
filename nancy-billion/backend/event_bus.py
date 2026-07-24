"""Real in-process pub/sub for domain events.

Bridges components that have no business knowing about FastAPI or
WebSockets (AgentService, MissionStore) to main_new.py's WebSocket
ConnectionManager, so a real state change anywhere in the backend can
broadcast to every connected browser tab without those modules importing
anything web-related.

This is intentionally NOT a message broker (no Redis, no persistence, no
cross-process delivery) -- Nancy runs as a single local backend process for
one user (see InstancesPanel's honesty note in the frontend), so an
in-memory asyncio pub/sub is the real architecture here, not a placeholder
for one. If Nancy ever runs as more than one process, this is the seam
where a real broker would replace it.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

Subscriber = Callable[[str, Dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: List[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    async def publish(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Publish a real domain event. Returns the envelope actually sent
        (useful for callers that also want to log/return what was broadcast).
        A subscriber raising must never take down the real state change that
        triggered this -- it's always fire-and-forget from the publisher's
        point of view."""
        envelope: Dict[str, Any] = {"type": event_type, "at": time.time(), **payload}
        for callback in list(self._subscribers):
            try:
                await callback(event_type, envelope)
            except Exception:
                logger.exception("event_bus subscriber failed for %s", event_type)
        return envelope


event_bus = EventBus()
