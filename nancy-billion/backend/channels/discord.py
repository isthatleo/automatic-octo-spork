"""Real Discord channel -- a bot-token-authenticated call against Discord's
actual REST API (POST /channels/{id}/messages), the same real-HTTP-call
shape as slack.py's chat.postMessage. Requires a real Discord bot
application (discord.com/developers/applications) invited to your server
with the "Send Messages" permission -- no gateway/websocket connection is
opened here, this is outbound-only, same tier as ntfy/ClickClack.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordChannel(Channel):
    name = "discord"

    def __init__(self) -> None:
        self.bot_token = os.getenv("DISCORD_BOT_TOKEN")
        self.default_channel_id = os.getenv("DISCORD_CHANNEL_ID")

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.default_channel_id)

    async def send(self, message: str, **kw: Any) -> bool:
        if not self.bot_token:
            return False
        channel_id = kw.get("channel_id") or self.default_channel_id
        if not channel_id:
            logger.warning("DiscordChannel: no channel_id specified and no DISCORD_CHANNEL_ID set")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                    json={"content": message[:2000]},  # Discord's real hard message-length cap
                    headers={"Authorization": f"Bot {self.bot_token}"},
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("DiscordChannel: send failed: %s", e)
            return False


register_channel_if_configured("discord", DiscordChannel)
