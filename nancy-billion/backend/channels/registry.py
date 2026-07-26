"""Registry of configured Channel instances -- same self-register-if-configured
idiom as providers/registry.py, applied to notification channels instead of
generation/search vendors. A cron job's `channel_message` action (see
cron_store.py) resolves its target channel through this registry by name.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from channels.base import Channel

logger = logging.getLogger(__name__)

_CHANNELS: Dict[str, Channel] = {}


def register_channel(name: str, instance: Channel) -> None:
    _CHANNELS[name] = instance
    logger.info("channels: registered %r", name)


def register_channel_if_configured(name: str, factory: Type[Channel]) -> None:
    try:
        instance = factory()
    except Exception as e:
        logger.warning("channels: %r failed to initialize, skipping: %s", name, e)
        return
    if not instance.is_configured():
        return
    register_channel(name, instance)


def get_channel(name: str) -> Optional[Channel]:
    return _CHANNELS.get(name)


def list_channels() -> Dict[str, Channel]:
    return dict(_CHANNELS)
