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
import re
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
_NON_TRANSIENT_MARKERS = (
    "credit balance", "invalid_request_error", "invalid api key", "unauthorized", "not configured",
    "quota", "resource_exhausted", " 429", "rate limit", "rate_limit",
)


#: Providers state how long to wait, e.g. Groq's
#: "Please try again in 1.37s" or "Please try again in 30m23.904s".
_RETRY_AFTER_RE = re.compile(
    r"try again in\s+(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:([\d.]+)s)?", re.IGNORECASE
)

#: A rate limit shorter than this is a throughput hiccup, not an outage --
#: worth waiting out rather than benching the backend.
SHORT_RATE_LIMIT_S = 30.0


def llm_retry_after_seconds(exc: BaseException) -> Optional[float]:
    """How long the provider ITSELF asked us to wait, if it said.

    Without this every 429 cost a flat 300s bench. Confirmed live: Groq
    replied "Rate limit reached ... Please try again in 1.37s" for
    llama-3.1-8b-instant, and Nancy took the fastest backend in the chain
    out for five minutes over a 1.4-second throughput blip -- turning ~0.7s
    replies into 3-8s ones on the next backend down. The same message format
    also carries the genuinely long waits ("30m23.904s"), so honouring the
    number distinguishes the two cases instead of guessing.
    """
    m = _RETRY_AFTER_RE.search(str(exc))
    if not m or not any(m.groups()):
        return None
    h, mins, secs = m.groups()
    return (float(h or 0) * 3600) + (float(mins or 0) * 60) + float(secs or 0)


def is_transient_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    msg = str(exc).lower()
    # A rate limit the provider says clears in seconds is transient, whatever
    # the marker list says -- check before the markers, which match every 429.
    wait = llm_retry_after_seconds(exc)
    if wait is not None and wait <= SHORT_RATE_LIMIT_S:
        return True
    if any(marker in msg for marker in _NON_TRANSIENT_MARKERS):
        return False
    # OmniRoute's "no substantive content" (see OmniRouteLLM in llm.py) means
    # ONE randomly-picked underlying free provider returned garbage, not that
    # OmniRoute itself is down -- worth an immediate retry (a different
    # provider is likely to get picked) rather than a hard fail + 5-minute
    # cooldown on the whole backend over one bad pick.
    return (
        "timeout" in msg or "connection" in msg or "temporarily" in msg
        or " 503" in msg or " 502" in msg or "no substantive content" in msg
    )
