---
name: mixture-of-agents
description: Explain the real cross-model validation mode -- several distinct AI models answering in parallel, then synthesized -- not a hypothetical feature.
trigger_keywords:
  - second opinion
  - cross-check
  - mixture of agents
  - moa
  - multiple ais
  - multiple models
  - ai opinions
---

Nancy has a real Mixture-of-Agents mode (`moa.py`) -- when the user explicitly
asks for a second opinion or cross-model check ("get me a second opinion",
"cross-check that with multiple models", "mixture of agents"), the request is
sent to several distinct, already-configured LLM backends in real parallel
(not sequential fallback), and the best-performing one synthesizes their
answers into a single, critically-evaluated response (`POST /llm/moa`).

## Answering

- Only trigger this for an explicit ask -- it costs real extra latency
  (several parallel calls plus a synthesis call), so it should never fire
  silently on an ordinary question.
- If fewer than 2 backends succeed, there's nothing to synthesize -- present
  the single real answer honestly rather than claiming a "cross-check"
  happened.
- If the response includes an `aggregation_error`, mention plainly that
  synthesis itself failed (usually an account/quota issue with the
  top-priority backend) and that a single reference answer is being shown
  instead -- never hide that from the user.
