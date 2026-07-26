"""Real Slack channel -- gives thread_ownership.py a genuine caller (Slack
threads are exactly the "two instances might both reply" scenario that
extension models). Outbound uses Slack's real Web API (chat.postMessage);
before replying in a *thread* specifically, it consults thread_ownership's
claim so a second instance of this backend (if one is ever run) won't double-
reply. A plain top-level channel message (no thread_ts) has no ownership
race to arbitrate, so it skips the claim check.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from channels.base import Channel
from channels.registry import register_channel_if_configured
from channels.thread_ownership import claim, INSTANCE_ID

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackChannel(Channel):
    name = "slack"

    def __init__(self) -> None:
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.signing_secret = os.getenv("SLACK_SIGNING_SECRET")
        self.default_channel = os.getenv("SLACK_DEFAULT_CHANNEL")

    def is_configured(self) -> bool:
        return bool(self.bot_token)

    async def send(self, message: str, **kw: Any) -> bool:
        if not self.bot_token:
            return False
        channel = kw.get("channel") or self.default_channel
        thread_ts = kw.get("thread_ts")
        if not channel:
            logger.warning("SlackChannel: no channel specified and no SLACK_DEFAULT_CHANNEL set")
            return False

        if thread_ts:
            owned = claim("slack", f"{channel}:{thread_ts}", INSTANCE_ID)
            if not owned:
                logger.info("SlackChannel: another instance owns thread %s:%s, skipping reply", channel, thread_ts)
                return False

        payload = {"channel": channel, "text": message}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{SLACK_API_BASE}/chat.postMessage",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    logger.warning("SlackChannel: send failed: %s", data.get("error"))
                    return False
            return True
        except Exception as e:
            logger.warning("SlackChannel: send failed: %s", e)
            return False


register_channel_if_configured("slack", SlackChannel)
