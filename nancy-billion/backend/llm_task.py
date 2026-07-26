"""Real schema-validated one-off LLM calls -- ported from OpenClaw's
llm-task extension. For when a caller (a cron job, another tool, a workflow
step) needs a structured JSON answer back, not free-form prose -- e.g.
"classify this text as spam/not-spam" should return {"label": "spam"}, not a
paragraph explaining the reasoning.

Uses Nancy's existing llm_backend fallback chain (llm.py) rather than a
separate LLM client, and retry_util's real backoff for the one retry allowed
when the model's output doesn't parse/validate the first time.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

import jsonschema

from llm import llm_backend
from retry_util import retry_async

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', re.DOTALL)


def _extract_json(text: str) -> Any:
    """Models often wrap JSON in a markdown code fence or add a sentence
    before/after it even when told not to -- try the whole string first,
    then fall back to pulling the first fenced or brace-delimited block."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK_RE.search(text)
    if m:
        return json.loads(m.group(1))
    # Last resort: first { to last } (or [ to ]) in the text.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
    raise ValueError("no JSON object/array found in model output")


async def structured_llm_call(prompt: str, json_schema: Dict[str, Any], max_tokens: int = 512) -> Dict[str, Any]:
    """Calls the LLM, asking for JSON matching `json_schema`, validates the
    result, and retries once (via retry_util.retry_async) if the first
    attempt doesn't parse or doesn't validate. Returns
    {"success": True, "data": ...} or {"success": False, "error": ...} --
    never raises."""
    full_prompt = (
        f"{prompt}\n\n"
        f"Respond with ONLY a single valid JSON value matching this JSON Schema, "
        f"no prose, no markdown code fence:\n{json.dumps(json_schema)}"
    )

    async def _attempt() -> Dict[str, Any]:
        raw = await llm_backend.generate(full_prompt, max_tokens=max_tokens, temperature=0.0)
        data = _extract_json(raw)
        jsonschema.validate(instance=data, schema=json_schema)
        return data

    try:
        data = await retry_async(
            _attempt,
            max_attempts=2,
            should_retry=lambda e: isinstance(e, (ValueError, json.JSONDecodeError, jsonschema.ValidationError)),
        )
        return {"success": True, "data": data}
    except Exception as e:
        logger.warning("structured_llm_call failed: %s", e)
        return {"success": False, "error": str(e)}


UTILITY_TOOLS = [
    {
        "name": "llm_structured_task",
        "description": (
            "Run a one-off LLM call that must return structured JSON matching a schema you "
            "provide, instead of free-form prose -- use this for classification, extraction, or "
            "any sub-task where you need a machine-parseable answer back (e.g. "
            '{"label": "spam"} instead of a sentence explaining why).'
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "What to ask the model to do."},
                "json_schema": {"type": "object", "description": "A JSON Schema the response must validate against."},
            },
            "required": ["prompt", "json_schema"],
        },
    },
]
