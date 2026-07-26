"""Real Photon/iMessage sidecar channel -- ported from Hermes' Photon
platform integration. The Photon sidecar process itself is macOS-only
(it drives iMessage via a local "Photon Spectrum" helper) and this backend
runs on Windows, so the sidecar has to run on a separate Mac -- Nancy's side
of the integration is nonetheless a fully real, complete implementation of
Photon's actual protocol: outbound sends POST to the sidecar's real HTTP API,
and inbound iMessage replies arrive via Nancy's existing HMAC-verified
inbound-webhook system (inbound_webhooks_store.py) rather than a
Photon-specific listener, so no new inbound surface has to be trusted.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)


class PhotonChannel(Channel):
    """Outbound: POSTs {"to", "message"} to the sidecar's /send endpoint,
    authenticated via a shared secret header -- the sidecar itself validates
    this same secret before actually sending through iMessage. Inbound: the
    sidecar is configured (on its own Mac) to forward incoming iMessages to
    this backend's real /webhooks/inbound/{hook_id} endpoint as a normal,
    HMAC-signed inbound webhook -- see inbound_webhooks_store.py -- so
    receiving a Photon message reuses infrastructure already hardened
    against unauthenticated inbound calls, instead of a second bespoke
    listener with its own auth logic."""

    name = "photon"

    def __init__(self) -> None:
        self.sidecar_url = os.getenv("PHOTON_SIDECAR_URL", "").rstrip("/")
        self.shared_secret = os.getenv("PHOTON_SHARED_SECRET")
        self.default_recipient = os.getenv("PHOTON_DEFAULT_RECIPIENT")

    def is_configured(self) -> bool:
        return bool(self.sidecar_url and self.shared_secret)

    async def send(self, message: str, **kw: Any) -> bool:
        to = kw.get("to") or self.default_recipient
        if not self.is_configured() or not to:
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.sidecar_url}/send",
                    json={"to": to, "message": message},
                    headers={"X-Photon-Secret": self.shared_secret},
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("PhotonChannel: send failed: %s", e)
            return False


register_channel_if_configured("photon", PhotonChannel)
