"""Imports every vendor adapter module so its module-level
`register_if_configured(...)` call actually runs. A vendor module is never
auto-discovered (no directory scan, matching this codebase's explicit-import
convention used everywhere else -- e.g. agents/specialized/registry.py) --
it just needs to be imported once, here, for its self-registration to take
effect. Each import is wrapped so one vendor's missing optional dependency
(e.g. a package not yet pip-installed) can't prevent every other vendor from
registering.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_VENDOR_MODULES = [
    "providers.web_search.brave",
    "providers.web_search.tavily",
    "providers.web_search.searxng",
    "providers.image.fal",
    "providers.image.deepinfra",
    "providers.tts.elevenlabs",
    "providers.transcription.deepgram",
    "memory.providers.mem0",
    "memory.providers.supermemory",
    "memory.providers.honcho",
    "memory.providers.hindsight",
    "memory.providers.byterover",
    "memory.providers.openviking",
    "memory.providers.retaindb",
    "providers.telephony.twilio",
    "providers.sandbox.crabbox",
]


def load_all_providers() -> None:
    for module_name in _VENDOR_MODULES:
        try:
            __import__(module_name)
        except Exception as e:
            logger.warning("providers.bootstrap: failed to import %s: %s", module_name, e)
