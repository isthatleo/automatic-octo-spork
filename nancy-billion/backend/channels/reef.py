"""Real Reef encrypted agent-to-agent messaging channel -- ported from
OpenClaw's Reef extension ("guarded end-to-end encrypted claw-to-claw
messaging"). A real client against Reef's message-relay API: this backend
encrypts with its configured key before POSTing, so the relay only ever
sees ciphertext. Currently has no caller within Nancy (there is no second
Nancy/Reef-speaking agent to talk to yet) -- it's real, working
infrastructure for the day Nancy needs to talk to another agent instance,
not a placeholder.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)


class ReefChannel(Channel):
    name = "reef"

    def __init__(self) -> None:
        self.api_key = os.getenv("REEF_API_KEY")
        self.endpoint = os.getenv("REEF_ENDPOINT", "").rstrip("/")
        self.peer_id = os.getenv("REEF_PEER_ID")
        # Real symmetric encryption of the message body before it ever
        # leaves this process -- REEF_ENCRYPTION_KEY is a Fernet key
        # (generate with `Fernet.generate_key()`); without one, Reef sends
        # are refused rather than silently going out in plaintext.
        enc_key = os.getenv("REEF_ENCRYPTION_KEY")
        self._fernet = Fernet(enc_key.encode()) if enc_key else None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.endpoint and self.peer_id and self._fernet)

    async def send(self, message: str, **kw: Any) -> bool:
        if not self.is_configured():
            return False
        peer_id = kw.get("peer_id") or self.peer_id
        try:
            ciphertext = self._fernet.encrypt(message.encode("utf-8")).decode("ascii")
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.endpoint}/v1/messages",
                    json={"to": peer_id, "ciphertext": ciphertext},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("ReefChannel: send failed: %s", e)
            return False

    def decrypt(self, ciphertext: str) -> str:
        """For a future inbound path: decrypts a real received ciphertext.
        Raises InvalidToken (from cryptography) on tamper/wrong key rather
        than silently returning garbage."""
        if not self._fernet:
            raise RuntimeError("REEF_ENCRYPTION_KEY not configured")
        return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")


register_channel_if_configured("reef", ReefChannel)
