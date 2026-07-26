"""Real multi-credential rotation/failover -- ported from Hermes' credential
pool (`agent/credential_pool.py`): several API keys for the *same* provider,
rotated round-robin and failed over automatically when one hits a rate limit
or gets rejected, instead of a single key that just stops working under load.

Distinct from retry_util.py's same-key retry-with-backoff: this is for when
you have *multiple* keys and want to spread load / survive one key's quota
running out, not for retrying a single call against a single key.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# How long a key that just failed with a rate-limit/auth error is skipped
# before being tried again -- long enough to ride out a typical per-minute
# rate-limit window, short enough that a transient blip doesn't permanently
# retire a good key.
_COOLDOWN_S = 60.0


class CredentialPool:
    """Construct with the provider's key env-var name, e.g.
    `CredentialPool("OPENAI_API_KEY")`. Reads `OPENAI_API_KEY_POOL` (a
    comma-separated list) if set; otherwise falls back to the single
    `OPENAI_API_KEY` as a pool of one, so any existing single-key caller keeps
    working unchanged."""

    def __init__(self, env_var: str) -> None:
        self.env_var = env_var
        pool_raw = os.getenv(f"{env_var}_POOL")
        if pool_raw:
            self._keys: List[str] = [k.strip() for k in pool_raw.split(",") if k.strip()]
        else:
            single = os.getenv(env_var)
            self._keys = [single] if single else []
        self._index = 0
        self._cooldown_until: Dict[str, float] = {}

    def has_keys(self) -> bool:
        return bool(self._keys)

    def _available_keys(self) -> List[str]:
        now = time.monotonic()
        return [k for k in self._keys if self._cooldown_until.get(k, 0.0) <= now]

    def get_key(self) -> Optional[str]:
        """Round-robins across keys not currently in cooldown. Returns None
        if every key is either absent or cooling down (caller should treat
        this exactly like a missing API key)."""
        available = self._available_keys()
        if not available:
            return None
        # Round-robin over the *full* key list so rotation order stays
        # stable even as individual keys enter/leave cooldown.
        for _ in range(len(self._keys)):
            key = self._keys[self._index % len(self._keys)]
            self._index += 1
            if key in available:
                return key
        return available[0]

    def report_failure(self, key: str, retry_after_s: Optional[float] = None) -> None:
        """Call when a request using `key` fails with a rate-limit (429) or
        auth (401) error -- puts that key in cooldown so the next
        `get_key()` call skips it and tries another."""
        cooldown = retry_after_s if retry_after_s is not None else _COOLDOWN_S
        self._cooldown_until[key] = time.monotonic() + cooldown
        logger.warning(
            "credential_pool: %s key ending ...%s put in cooldown for %.0fs",
            self.env_var, key[-4:] if len(key) >= 4 else "****", cooldown,
        )
