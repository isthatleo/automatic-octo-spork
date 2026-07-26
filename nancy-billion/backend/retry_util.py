"""Real exponential-backoff-with-jitter retry engine -- ported from
OpenClaw's packages/retry. Used to give a real transient failure (a
momentary network blip, a connection reset) one more real chance before
giving up on it, instead of every caller hand-rolling its own sleep loop.

Deliberately NOT a blanket "retry everything" wrapper -- retrying a
non-transient failure (an invalid API key, an exhausted credit balance,
per this session's own live-confirmed Anthropic/Gemini account issues)
just adds latency for a call that will never succeed. Callers pass
`should_retry` to say which real exception types are worth a second try.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def compute_backoff(
    attempt: int,
    *,
    base_delay_s: float = 0.4,
    factor: float = 2.0,
    max_delay_s: float = 20.0,
    jitter: str = "full",
) -> float:
    """base * factor^attempt, capped, then jittered. jitter="full" picks
    uniformly in [0, delay] (the generally-recommended default -- spreads
    concurrent retries out the most); "none" returns the capped delay
    unchanged."""
    delay = min(base_delay_s * (factor ** attempt), max_delay_s)
    if jitter == "full":
        return random.uniform(0, delay)
    if jitter == "symmetric":
        spread = delay * 0.5
        return max(0.0, delay + random.uniform(-spread, spread))
    return delay


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 2,
    base_delay_s: float = 0.4,
    factor: float = 2.0,
    max_delay_s: float = 20.0,
    jitter: str = "full",
    should_retry: Optional[Callable[[BaseException], bool]] = None,
    retry_after_from: Optional[Callable[[BaseException], Optional[float]]] = None,
) -> T:
    """Calls `fn()` (a zero-arg async callable -- wrap real args in a
    closure at the call site), retrying with exponential backoff.
    `should_retry(exc)` decides whether a given exception is worth
    retrying at all (default: retry everything passed to this function --
    the caller is expected to already only call this for transient error
    types); `retry_after_from` lets a caller honor a real server-supplied
    retry delay (e.g. a 429's Retry-After) instead of guessing."""
    last_exc: Optional[BaseException] = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as e:
            last_exc = e
            if should_retry is not None and not should_retry(e):
                raise
            if attempt == max_attempts - 1:
                raise
            delay = retry_after_from(e) if retry_after_from is not None else None
            if delay is None:
                delay = compute_backoff(attempt, base_delay_s=base_delay_s, factor=factor, max_delay_s=max_delay_s, jitter=jitter)
            logger.info("retry_async: attempt %d/%d failed (%s), retrying in %.2fs", attempt + 1, max_attempts, e, delay)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


# Real, narrow transience check for LLM backend calls specifically -- a
# timeout or connection-level failure is worth one more try; a 4xx-shaped
# auth/credit/quota error (confirmed live this session: an exhausted
# Anthropic credit balance, a 429 quota error) never succeeds on retry, so
# retrying it would only add latency for a call that's going to fail again
# regardless of the fallback chain's own real per-backend timeout budget.
_NON_TRANSIENT_MARKERS = ("credit balance", "invalid_request_error", "invalid api key", "unauthorized", "not configured")


def is_transient_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    msg = str(exc).lower()
    if any(marker in msg for marker in _NON_TRANSIENT_MARKERS):
        return False
    return "timeout" in msg or "connection" in msg or "temporarily" in msg or " 503" in msg or " 502" in msg
