"""Imports every channel module so its module-level
`register_channel_if_configured(...)` call runs -- same explicit-import
convention as providers/bootstrap.py. Each new channel module gets added
to _CHANNEL_MODULES here as it's built.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CHANNEL_MODULES: list[str] = [
    "channels.ntfy",
    "channels.home_assistant",
    "channels.photon",
    "channels.reef",
    "channels.clickclack",
    "channels.slack",
    "channels.voice_call",
    "channels.discord",
    "channels.whatsapp",
]


def load_all_channels() -> None:
    for module_name in _CHANNEL_MODULES:
        try:
            __import__(module_name)
        except Exception as e:
            logger.warning("channels.bootstrap: failed to import %s: %s", module_name, e)
