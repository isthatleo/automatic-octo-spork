"""Real outbound/inbound notification-channel ABC. `telegram_bot.py`'s
`TelegramNotifier` is the reference shape every new channel matches (it is
NOT rewritten to inherit this ABC -- it predates it and is deeply load-bearing
via the approval-gating flow; new channels are simply built to the same
interface shape so they're interchangeable with it wherever a channel is
just "somewhere to send a message").
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class Channel(ABC):
    name: str = "base"

    @abstractmethod
    async def send(self, message: str, **kw: Any) -> bool:
        """Sends `message` out this channel. Returns True on confirmed
        delivery, False on any failure -- never raises (matches
        telegram_bot.py's send() contract: a channel failure degrades to
        "the message didn't go out," not a crash)."""

    async def receive(self) -> Optional[Dict[str, Any]]:
        """Optional: channels capable of two-way communication (e.g. a
        webhook-backed channel) override this. One-way channels (ntfy,
        ClickClack) leave the default None."""
        return None

    def is_configured(self) -> bool:
        """Whether this channel has what it needs (API key, endpoint, etc.)
        to actually function -- checked before it's offered as a send target,
        same idea as telegram_bot.py's `_load_error` flag."""
        return True
