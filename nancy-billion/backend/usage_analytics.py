"""Real LLM usage/cost/latency analytics -- ported from OpenClaw's usage
insights. UsagePanel (admin-panels.tsx) already tracks real agent task
volume/success rate but explicitly says "Nancy doesn't meter LLM token
spend per-request yet" -- this fills that exact gap.

Two data-quality tiers, both real, neither fabricated:
- "exact": a backend's own raw API response actually reports token counts
  (and, for some providers, a real prompt-processing/decode time split) --
  extracted directly from that response before it's discarded down to a
  plain string. Anthropic, Groq, OpenAI-compatible APIs (OpenRouter,
  OpenCode, ClawRouter), Gemini, and Ollama all expose this in their raw
  JSON/SDK response.
- "estimated": a plain chars/4 heuristic, used only for backends that
  genuinely don't report usage at all (e.g. a bare local completion with no
  metadata) -- always labeled as an estimate, never presented as exact.

Inference speed (tokens/sec) is only computed where a real decode-time
denominator exists -- never estimated, since a fabricated rate would be
actively misleading rather than just imprecise.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "usage_analytics.json"


def estimate_tokens(text: str) -> int:
    """Standard rough estimate (~4 chars/token for English text) -- real,
    disclosed as an estimate everywhere it's surfaced, never presented as
    an exact provider-reported count."""
    return max(1, len(text) // 4)


def _load() -> Dict[str, Any]:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: Dict[str, Any]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _fresh_entry() -> Dict[str, Any]:
    return {
        "call_count": 0,
        "success_count": 0,
        "total_latency_s": 0.0,
        # Exact, provider-reported (only incremented when a real number was given).
        "exact_prompt_tokens": 0,
        "exact_completion_tokens": 0,
        "exact_token_calls": 0,  # how many calls contributed exact (not estimated) tokens
        "total_prompt_time_s": 0.0,   # real prompt-processing/prefill time, when reported
        "total_decode_time_s": 0.0,   # real decode/generation time, when reported
        "timed_calls": 0,             # how many calls contributed real prompt/decode timing
        # Fallback estimate, used only when a call didn't report real usage.
        "est_prompt_tokens": 0,
        "est_completion_tokens": 0,
        "estimated_token_calls": 0,
        # The real reason the most recent failed call actually failed --
        # without this, a backend with a 0% success rate (e.g. an
        # out-of-credit key) was only visible as a suspiciously low number
        # here, with the actual cause buried in a backend log line no
        # frontend surfaced. Overwritten on every failure, so it's always
        # the latest, not a stale first-ever error.
        "last_error": None,
        "last_error_at": None,
    }


def record_call(
    backend_name: str,
    latency_s: float,
    prompt_text: str,
    response_text: str,
    success: bool,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    prompt_time_s: Optional[float] = None,
    decode_time_s: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Never raises -- a failure to record analytics should never break the
    real LLM call it's measuring. Pass prompt_tokens/completion_tokens when
    a backend's raw response actually reported them (exact); omit to fall
    back to the character-count estimate. Pass prompt_time_s/decode_time_s
    only when a provider's response actually broke total latency down that
    way (currently: Groq's x_groq.usage, Ollama's prompt_eval_duration/
    eval_duration) -- never estimated. Pass error (the real exception text)
    on a failed call so a chronically-failing backend is diagnosable from
    the Usage page instead of just showing a suspiciously low success rate."""
    try:
        data = _load()
        entry = data.setdefault(backend_name, _fresh_entry())
        for key in _fresh_entry():
            entry.setdefault(key, _fresh_entry()[key])

        entry["call_count"] += 1
        if success:
            entry["success_count"] += 1
        else:
            entry["last_error"] = error
            entry["last_error_at"] = time.time()
        entry["total_latency_s"] += latency_s

        if prompt_tokens is not None and completion_tokens is not None:
            entry["exact_prompt_tokens"] += prompt_tokens
            entry["exact_completion_tokens"] += completion_tokens
            entry["exact_token_calls"] += 1
        elif success:
            entry["est_prompt_tokens"] += estimate_tokens(prompt_text)
            entry["est_completion_tokens"] += estimate_tokens(response_text)
            entry["estimated_token_calls"] += 1

        if prompt_time_s is not None and decode_time_s is not None:
            entry["total_prompt_time_s"] += prompt_time_s
            entry["total_decode_time_s"] += decode_time_s
            entry["timed_calls"] += 1

        _save(data)
    except Exception as e:
        logger.warning("usage_analytics: failed to record call: %s", e)


def get_usage_summary() -> Dict[str, Any]:
    data = _load()
    overall_calls = sum(e.get("call_count", 0) for e in data.values())
    overall_success = sum(e.get("success_count", 0) for e in data.values())

    per_backend = []
    for name, e in data.items():
        call_count = e.get("call_count", 0)
        avg_latency = e["total_latency_s"] / call_count if call_count else 0.0

        exact_tokens = e.get("exact_prompt_tokens", 0) + e.get("exact_completion_tokens", 0)
        est_tokens = e.get("est_prompt_tokens", 0) + e.get("est_completion_tokens", 0)
        has_exact = e.get("exact_token_calls", 0) > 0

        decode_time = e.get("total_decode_time_s", 0.0)
        completion_tokens_for_speed = e.get("exact_completion_tokens", 0)
        tokens_per_sec = round(completion_tokens_for_speed / decode_time, 1) if decode_time > 0 else None

        avg_prompt_time = e["total_prompt_time_s"] / e["timed_calls"] if e.get("timed_calls") else None
        avg_decode_time = e["total_decode_time_s"] / e["timed_calls"] if e.get("timed_calls") else None

        per_backend.append({
            "backend": name,
            "call_count": call_count,
            "success_count": e.get("success_count", 0),
            "avg_latency_s": round(avg_latency, 2),
            "prompt_tokens": e.get("exact_prompt_tokens", 0) if has_exact else e.get("est_prompt_tokens", 0),
            "completion_tokens": e.get("exact_completion_tokens", 0) if has_exact else e.get("est_completion_tokens", 0),
            "total_tokens": exact_tokens if has_exact else est_tokens,
            "tokens_exact": has_exact,
            "avg_prompt_time_s": round(avg_prompt_time, 3) if avg_prompt_time is not None else None,
            "avg_decode_time_s": round(avg_decode_time, 3) if avg_decode_time is not None else None,
            "tokens_per_sec": tokens_per_sec,
            "last_error": e.get("last_error"),
            "last_error_at": e.get("last_error_at"),
        })
    per_backend.sort(key=lambda x: x["call_count"], reverse=True)

    overall_tokens = sum(b["total_tokens"] for b in per_backend)

    return {
        "overall_calls": overall_calls,
        "overall_success": overall_success,
        "overall_tokens": overall_tokens,
        "per_backend": per_backend,
        "note": "prompt_tokens/completion_tokens/tokens_per_sec are exact provider-reported values when tokens_exact=true, otherwise a disclosed ~chars/4 estimate. avg_prompt_time_s/avg_decode_time_s and tokens_per_sec are only shown when a provider actually reported that timing split (Groq, Ollama) -- never estimated.",
    }
