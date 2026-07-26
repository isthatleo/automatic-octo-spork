"""Defensive coercion for LLM-supplied tool-call arguments -- even through a
real structured function-calling API (Claude's native tool_use, the only
path Nancy's tool-use loop goes through), a model can still hand back a
number as a string ("5" instead of 5), a boolean as a string ("true"), or a
JSON object/array as a string instead of already-parsed data. A tool
function written with normal Python type hints (e.g. computer_use_tool.py's
click_screen(x: int, y: int)) would otherwise raise or silently misbehave
on these. Ported in spirit from OpenClaw's packages/normalization-core.

Text-based tool-call parsing (repairing a model that "talks" tool calls as
plain text instead of using a real function-calling API, per OpenClaw's
packages/tool-call-repair) is deliberately NOT ported: Nancy's only
tool-use path is Claude's native structured API, which doesn't have that
failure mode. It would only become relevant if a non-function-calling
backend were ever wired into the tool-use loop -- there's nothing to fix
in the architecture as it exists today.
"""
from __future__ import annotations

import json
from typing import Any, Dict


def _coerce_value(value: Any, schema: Dict[str, Any]) -> Any:
    expected = schema.get("type")
    if expected == "integer" and isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    if expected == "number" and isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    if expected == "boolean" and isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "1"):
            return True
        if low in ("false", "no", "0"):
            return False
        return value
    if expected in ("object", "array") and isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def coerce_tool_input(tool_input: Dict[str, Any], input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a new dict with each property coerced toward its declared
    JSON-schema type when the model handed back a same-meaning value in the
    wrong shape. Never raises -- a value that doesn't coerce cleanly is
    passed through unchanged so the tool itself produces a real, specific
    error instead of this layer guessing wrong."""
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    if not isinstance(tool_input, dict) or not properties:
        return tool_input
    out = dict(tool_input)
    for key, val in tool_input.items():
        prop_schema = properties.get(key)
        if isinstance(prop_schema, dict):
            out[key] = _coerce_value(val, prop_schema)
    return out
