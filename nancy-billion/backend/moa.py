"""Mixture-of-Agents (MoA): real parallel-reference-model reasoning, not just
a fallback chain. Calls several distinct, already-configured LLM backends on
the SAME prompt in parallel, then asks the best-quality backend to critically
synthesize their answers into one final response -- catches blind spots or
errors a single model might miss, the same real technique Hermes's `/moa`
command implements (agent/moa_loop.py in the cloned reference repo).

Natively reimplemented against Nancy's own FallbackLLM backend chain rather
than porting Hermes's 2000+-line module, which is solving problems (PII
redaction across saved multi-user trace files, live-updating UI panes) that
don't apply to Nancy's single-user, non-persisted use of this.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MOA_REFERENCE_TIMEOUT_S = 25.0
MOA_AGGREGATION_TIMEOUT_S = 30.0
DEFAULT_REFERENCE_COUNT = 3

_AGGREGATION_PROMPT = """You were asked: {prompt}

Multiple AI models independently answered this question. Critically evaluate their answers -- where they agree, where they disagree, and which is most accurate and complete -- then write ONE final answer that reflects the best synthesis. Do not just concatenate them or mention that this is a synthesis of other models; answer as if you're giving the single best response yourself.

{references}
"""


def _usable_backends(llm_backend: Any, reference_count: int) -> List[Any]:
    """Same "skip if no api_key configured" rule FallbackLLM.generate()
    applies -- a backend that will always fail immediately shouldn't burn
    one of the limited reference slots."""
    backends = list(getattr(llm_backend, "backends", None) or [llm_backend])
    usable = [b for b in backends if not (hasattr(b, "api_key") and not b.api_key)]
    return usable[:max(1, reference_count)]


async def run_moa(
    llm_backend: Any,
    prompt: str,
    *,
    reference_count: int = DEFAULT_REFERENCE_COUNT,
    max_tokens: int = 800,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """Runs the real Mixture-of-Agents pattern: up to `reference_count`
    distinct backends answer the same prompt in parallel (references), then
    the highest-priority configured backend (first in the chain, matching
    FallbackLLM's own try-order) synthesizes them into one final answer."""
    backends = _usable_backends(llm_backend, reference_count)
    if not backends:
        return {"success": False, "error": "No LLM backends with a configured API key are available"}

    async def _ask_one(backend: Any) -> Optional[Dict[str, str]]:
        name = backend.__class__.__name__
        try:
            text = await asyncio.wait_for(
                backend.generate(prompt, max_tokens=max_tokens, temperature=temperature),
                timeout=MOA_REFERENCE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("MoA reference backend %s timed out after %.0fs", name, MOA_REFERENCE_TIMEOUT_S)
            return None
        except Exception as e:
            logger.warning("MoA reference backend %s failed: %s", name, e)
            return None
        text = (text or "").strip()
        if not text:
            logger.warning("MoA reference backend %s returned empty text", name)
            return None
        return {"backend": name, "text": text}

    raw_results = await asyncio.gather(*[_ask_one(b) for b in backends])
    references = [r for r in raw_results if r is not None]

    if not references:
        return {"success": False, "error": "Every reference model failed to respond"}
    if len(references) == 1:
        # Nothing to synthesize -- one real answer beats a "synthesis" of one voice.
        return {"success": True, "response": references[0]["text"], "references": references, "aggregated": False}

    references_text = "\n\n".join(f"[{r['backend']}]\n{r['text']}" for r in references)
    aggregation_prompt = _AGGREGATION_PROMPT.format(prompt=prompt, references=references_text)
    # Aggregate with a backend that just PROVED it works this round (the
    # first successful reference), not blindly the static top-priority one
    # -- if that one just failed as a reference (confirmed live: an
    # exhausted Anthropic credit balance), it's the same account/API issue
    # either way, so trusting it again as the aggregator would just fail a
    # second time for the identical reason instead of ever synthesizing.
    aggregator_name = references[0]["backend"]
    aggregator = next((b for b in backends if b.__class__.__name__ == aggregator_name), backends[0])
    try:
        synthesis = await asyncio.wait_for(
            aggregator.generate(aggregation_prompt, max_tokens=max_tokens, temperature=0.5),
            timeout=MOA_AGGREGATION_TIMEOUT_S,
        )
        synthesis = (synthesis or "").strip()
        if not synthesis:
            raise ValueError("aggregator returned empty text")
    except Exception as e:
        logger.warning("MoA aggregation failed, returning best single reference instead: %s", e)
        return {
            "success": True, "response": references[0]["text"], "references": references,
            "aggregated": False, "aggregation_error": str(e),
        }

    return {"success": True, "response": synthesis, "references": references, "aggregated": True}
