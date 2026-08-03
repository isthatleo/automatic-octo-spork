"""Regression tests for the LLM chain's ordering and failure handling.

Every test here exists because the bug it guards actually happened and was
expensive to notice, since all three failed *silently* -- Nancy kept
answering, just slower or wrong, with nothing surfaced to the user:

  * a 5-item stop list made Groq 400 on every call, benching the fastest
    backend and taking replies from 0.7s to 4-8s;
  * a 429 saying "try again in 1.37s" was classed as a hard quota failure
    and cost a 300s bench;
  * local backends ahead of cloud ones meant CPU inference competing with
    TTS for the same cores.

No network, no model load -- these gate a commit.

Run:  python backend/tests/test_llm_chain.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retry_util import (  # noqa: E402
    SHORT_RATE_LIMIT_S,
    is_transient_llm_error,
    llm_retry_after_seconds,
)

# Verbatim from backend.log on 2026-08-03.
GROQ_TPM_429 = (
    "Groq error: 429 - Rate limit reached for model `llama-3.1-8b-instant` in "
    "organization `org_01kpjk5mmee9a9b7rf5khhma3g` service tier `on_demand` on "
    "tokens per minute (TPM): Limit 6000, Used 3052, Requested 3085. "
    "Please try again in 1.37s."
)
GROQ_TPD_429 = (
    "Groq error: 429 - Rate limit reached for model `llama-3.3-70b-versatile` "
    "on tokens per day (TPD): Limit 100000, Used 98926, Requested 3185. "
    "Please try again in 30m23.904s."
)
ANTHROPIC_CREDIT = "Anthropic error: 400 - your credit balance is too low"


def test_stop_list_fits_groqs_four_item_cap() -> None:
    """Groq rejects a longer list with HTTP 400, and because that reads as an
    invalid_request_error it triggers a cooldown -- so an over-long list
    removes the fastest backend from the chain entirely."""
    from llm import TRANSCRIPT_STOP

    assert len(TRANSCRIPT_STOP) <= 4, f"Groq allows at most 4, got {len(TRANSCRIPT_STOP)}"
    assert all(s.startswith("\n") for s in TRANSCRIPT_STOP), (
        "a stop must be anchored to a line start, or it truncates mid-sentence "
        "on any innocent occurrence of the word"
    )
    # The prompt is built lowercase (main_new.py: f"{history}\nuser: {text}"),
    # so the lowercase pair is the one that actually has to be present.
    assert "\nuser:" in TRANSCRIPT_STOP and "\nassistant:" in TRANSCRIPT_STOP


def test_short_rate_limit_is_transient() -> None:
    assert llm_retry_after_seconds(Exception(GROQ_TPM_429)) == 1.37
    assert is_transient_llm_error(Exception(GROQ_TPM_429)), (
        "a 1.37s throughput blip must not bench a backend"
    )


def test_long_rate_limit_is_not_transient() -> None:
    wait = llm_retry_after_seconds(Exception(GROQ_TPD_429))
    assert wait is not None and abs(wait - 1823.904) < 0.01
    assert wait > SHORT_RATE_LIMIT_S
    assert not is_transient_llm_error(Exception(GROQ_TPD_429))


def test_credit_exhaustion_stays_non_transient() -> None:
    assert llm_retry_after_seconds(Exception(ANTHROPIC_CREDIT)) is None
    assert not is_transient_llm_error(Exception(ANTHROPIC_CREDIT))


def test_local_backends_are_ordered_last() -> None:
    """Local inference competes with TTS for the same CPU cores -- confirmed
    live when llama-server pushed identical synthesis from ~1s to 47s."""
    from llm import _is_local_backend

    for name in ("OllamaAutoModelsLLM", "FuryLLM", "LlamaCppLLM", "VLLMLLM"):
        assert _is_local_backend(name), f"{name} should be treated as local"
    for name in ("GroqLLM", "OpenCodeLLM", "GeminiLLM", "OmniRouteLLM", "AnthropicLLM"):
        assert not _is_local_backend(name), f"{name} should be treated as cloud"


def test_chain_order_moves_vendor_siblings_together() -> None:
    """Groq exposes two models as two backends. Promoting "groq" must move
    both, or the 8b sibling is stranded behind slower providers."""
    from llm import apply_chain_order

    def make(name):
        return type(name, (), {})()

    backends = [make(n) for n in
                ("AnthropicLLM", "GroqLLM", "OllamaAutoModelsLLM", "GroqLLM", "OpenCodeLLM")]
    os.environ["LLM_ORDER"] = "groq,opencode"
    try:
        names = [b.__class__.__name__ for b in apply_chain_order(backends)]
    finally:
        os.environ.pop("LLM_ORDER", None)

    assert names[:2] == ["GroqLLM", "GroqLLM"], f"siblings not adjacent: {names}"
    assert names[2] == "OpenCodeLLM", f"explicit order not honoured: {names}"
    assert names[-1] == "OllamaAutoModelsLLM", f"local not last: {names}"


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - harness reports, never raises
            failed += 1
            print(f"  FAIL  {test.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
