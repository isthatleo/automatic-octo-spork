"""Real voice-call channel -- ported from OpenClaw's voice-call extension.
Sits on top of the telephony provider registry (providers/telephony/*.py,
Twilio is the reference vendor) so `send()` places a REAL phone call that
speaks the message via TTS on the line, giving telephony a Channel-shaped
interface consistent with every other notification channel in this codebase.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)


class VoiceCallChannel(Channel):
    name = "voice_call"

    def __init__(self) -> None:
        self.default_to_number = os.getenv("VOICE_CALL_DEFAULT_TO")

    def is_configured(self) -> bool:
        from providers.registry import is_configured
        return is_configured("telephony")

    async def send(self, message: str, **kw: Any) -> bool:
        from providers.registry import get_ordered_providers
        providers = get_ordered_providers("telephony")
        if not providers:
            logger.warning("VoiceCallChannel: no telephony provider configured")
            return False
        to_number = kw.get("to") or self.default_to_number
        if not to_number:
            logger.warning("VoiceCallChannel: no 'to' number given and VOICE_CALL_DEFAULT_TO not set")
            return False
        result = await providers[0].place_call(to_number, message=message)
        return result.get("success", False)


register_channel_if_configured("voice_call", VoiceCallChannel)
