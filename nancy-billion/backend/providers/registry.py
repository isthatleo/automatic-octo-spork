"""Central registry every vendor adapter self-registers into at import time --
mirrors llm.py's get_llm_backends() (`if os.getenv("X_API_KEY"): register(...)`)
generalized past LLM text generation to every other pluggable-vendor capability
(web search, image/video/TTS/transcription generation, browser sessions,
telephony, memory). A vendor module that imports cleanly but whose API key
isn't set never calls register() -- so an unconfigured vendor is simply never
offered to Claude, exactly like an unconfigured LLM backend today.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Type

logger = logging.getLogger(__name__)

# capability -> {vendor_name: instance}
PROVIDER_REGISTRIES: Dict[str, Dict[str, Any]] = {}


def register(capability: str, vendor: str, instance: Any) -> None:
    PROVIDER_REGISTRIES.setdefault(capability, {})[vendor] = instance
    logger.info("providers: registered %s vendor %r", capability, vendor)


def register_if_configured(capability: str, vendor: str, env_var: str, factory: Type) -> None:
    """The one-line idiom every vendor module's import-time code should use:
    `register_if_configured("web_search", "brave", "BRAVE_API_KEY", BraveSearchProvider)`.
    Constructs and registers `factory()` only if `env_var` is set; on any
    construction error, warns and skips rather than crashing the whole
    process at import time (a bad/expired key shouldn't take down startup)."""
    if not os.getenv(env_var):
        return
    try:
        register(capability, vendor, factory())
    except Exception as e:
        logger.warning("providers: %s vendor %r failed to initialize, skipping: %s", capability, vendor, e)


def get_ordered_providers(capability: str) -> List[Any]:
    """Configured vendor instances for a capability, in priority order.
    Priority: an explicit `<CAPABILITY>_PROVIDER_ORDER` env var (comma-separated
    vendor names) if set, else registration order (import order) -- same
    "explicit env var wins, else registration order" idiom as llm.py's
    backend chain."""
    vendors = PROVIDER_REGISTRIES.get(capability, {})
    if not vendors:
        return []
    order_env = os.getenv(f"{capability.upper()}_PROVIDER_ORDER")
    if order_env:
        names = [n.strip() for n in order_env.split(",") if n.strip()]
        ordered = [vendors[n] for n in names if n in vendors]
        # Any configured-but-unlisted vendor still gets appended at the end,
        # so setting an explicit order for two vendors doesn't silently drop
        # a third one you also configured.
        ordered += [v for name, v in vendors.items() if name not in names]
        return ordered
    return list(vendors.values())


def get_provider(capability: str, vendor: str) -> Any:
    return PROVIDER_REGISTRIES.get(capability, {}).get(vendor)


def is_configured(capability: str) -> bool:
    return bool(PROVIDER_REGISTRIES.get(capability))
