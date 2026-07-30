"""Check that a picked model actually gets the tool-using turns.

main_new.py imports the whole world (fastapi, agents, browser tooling), which
makes it unimportable in a bare checkout -- so instead of mocking all of that,
this lifts the real source text of the tool-routing helpers and the ordering
expression out of the file and executes those. If someone edits the routing,
this test sees the edit.

    python backend/test_tool_backend_order.py
"""
from __future__ import annotations

import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Optional

SRC = (Path(__file__).parent / "main_new.py").read_text(encoding="utf-8")


def _extract(start_marker: str, end_marker: str) -> str:
    """Pull the source between two anchors, keeping it honest about drift."""
    i = SRC.index(start_marker)
    j = SRC.index(end_marker, i)
    return SRC[i:j]


# --- the helpers, verbatim -------------------------------------------------
helpers_src = _extract("_OLLAMA_LOCAL_SENTINEL = ", "def _any_tool_backend_configured")
ns: dict = {"os": os, "Optional": Optional}
exec(compile(helpers_src, "main_new.py:helpers", "exec"), ns)

TOOL_FALLBACK_BACKENDS = ns["TOOL_FALLBACK_BACKENDS"]
_tool_backend_key = ns["_tool_backend_key"]
_tool_backend_base_url = ns["_tool_backend_base_url"]
_tool_backend_class = ns["_tool_backend_class"]

# --- the ordering expression, verbatim -------------------------------------
order_src = textwrap.dedent(_extract("        _compat_classes = {t[4]", "        logger.info("))


def order_for(primary_cls: str):
    """Run the real ordering code for a given live-chain primary."""
    scope = dict(ns)
    scope["_primary_cls"] = _tool_backend_class(primary_cls)
    exec(compile(order_src, "main_new.py:order", "exec"), scope)
    return scope["claude_first"], [t[4] for t in scope["ordered_fallbacks"]]


# --- assertions ------------------------------------------------------------
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok  {label}")
    else:
        failures.append(f"{label}{': ' + detail if detail else ''}")
        print(f"  FAIL {label}{': ' + detail if detail else ''}")


print("tool-backend routing")

# 1. Every provider a user can pick as primary must be routable for tools.
for cls in ("OpenRouterLLM", "GroqLLM", "OpenCodeLLM", "OpenAILLM",
            "OllamaCloudLLM", "OllamaLLM", "OllamaAutoModelsLLM"):
    claude_first, order = order_for(cls)
    expected = _tool_backend_class(cls)
    check(f"{cls} leads its own tool turns",
          not claude_first and order[0] == expected,
          f"claude_first={claude_first} order={order}")

# 2. A primary with no OpenAI-compatible tool dialect still falls to Claude.
claude_first, _ = order_for("GeminiLLM")
check("unsupported primary falls back to Claude", claude_first)

claude_first, _ = order_for("AnthropicLLM")
check("Claude primary keeps Claude first", claude_first)

# 3. Key resolution: the two entries that can't just read their own env var.
saved = {k: os.environ.get(k) for k in
         ("OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY", "OLLAMA_BASE_URL", "GROQ_API_KEY")}
for k in saved:
    os.environ.pop(k, None)
try:
    os.environ["OLLAMA_API_KEY"] = "cli-written-key"
    check("Ollama Cloud accepts the CLI's OLLAMA_API_KEY name",
          _tool_backend_key("OLLAMA_CLOUD_API_KEY") == "cli-written-key")

    os.environ["OLLAMA_CLOUD_API_KEY"] = "explicit-key"
    check("explicit OLLAMA_CLOUD_API_KEY wins",
          _tool_backend_key("OLLAMA_CLOUD_API_KEY") == "explicit-key")

    check("local Ollama is skipped when not configured",
          _tool_backend_key("OLLAMA_LOCAL") is None)

    os.environ["OLLAMA_BASE_URL"] = "http://192.168.1.7:11434/"
    check("local Ollama becomes reachable once configured",
          _tool_backend_key("OLLAMA_LOCAL") == "ollama")
    check("local Ollama base url gets the /v1 suffix, no double slash",
          _tool_backend_base_url("OLLAMA_LOCAL", "") == "http://192.168.1.7:11434/v1",
          _tool_backend_base_url("OLLAMA_LOCAL", ""))

    check("a normal provider reads its own env var",
          _tool_backend_key("GROQ_API_KEY") is None)
    os.environ["GROQ_API_KEY"] = "gsk-test"
    check("...and sees it once set", _tool_backend_key("GROQ_API_KEY") == "gsk-test")
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

# 4. Cloud entries keep their published base urls.
by_env = {t[0]: t for t in TOOL_FALLBACK_BACKENDS}
check("Ollama Cloud points at the OpenAI-compatible /v1 endpoint",
      by_env["OLLAMA_CLOUD_API_KEY"][1] == "https://ollama.com/v1")

# --- 5. The picked primary survives a restart ------------------------------
# Same trick against llm.py: lift the real functions rather than restate them.
LLM_SRC = (Path(__file__).parent / "llm.py").read_text(encoding="utf-8")
i = LLM_SRC.index("def matches_backend_name")
j = LLM_SRC.index("\n\n\n", LLM_SRC.index("def apply_primary_preference"))
llm_ns: dict = {"os": os, "logger": type("L", (), {
    "info": lambda *a, **k: None, "warning": lambda *a, **k: None})()}
exec(compile(LLM_SRC[i:j], "llm.py:primary", "exec"), llm_ns)
apply_primary_preference = llm_ns["apply_primary_preference"]
matches_backend_name = llm_ns["matches_backend_name"]


def chain(*names):
    return [type(n, (), {})() for n in names]


saved_primary = os.environ.get("LLM_PRIMARY")
try:
    os.environ.pop("LLM_PRIMARY", None)
    order = [b.__class__.__name__ for b in
             apply_primary_preference(chain("AnthropicLLM", "GroqLLM", "OpenCodeLLM"))]
    check("no saved primary leaves the catalog order alone",
          order == ["AnthropicLLM", "GroqLLM", "OpenCodeLLM"], str(order))

    os.environ["LLM_PRIMARY"] = "OpenCodeLLM"
    order = [b.__class__.__name__ for b in
             apply_primary_preference(chain("AnthropicLLM", "GroqLLM", "OpenCodeLLM"))]
    check("a saved primary leads the rebuilt chain",
          order == ["OpenCodeLLM", "AnthropicLLM", "GroqLLM"], str(order))

    os.environ["LLM_PRIMARY"] = "groq"
    order = [b.__class__.__name__ for b in
             apply_primary_preference(chain("AnthropicLLM", "GroqLLM", "OpenCodeLLM"))]
    check("a bare provider stem also matches", order[0] == "GroqLLM", str(order))

    os.environ["LLM_PRIMARY"] = "ollama"
    order = [b.__class__.__name__ for b in
             apply_primary_preference(chain("AnthropicLLM", "OllamaAutoModelsLLM"))]
    check("'ollama' matches a local auto-models daemon",
          order[0] == "OllamaAutoModelsLLM", str(order))

    os.environ["LLM_PRIMARY"] = "MistralLLM"
    order = [b.__class__.__name__ for b in
             apply_primary_preference(chain("AnthropicLLM", "GroqLLM"))]
    check("a primary that isn't in the chain degrades to default order",
          order == ["AnthropicLLM", "GroqLLM"], str(order))

    check("an empty chain doesn't explode", apply_primary_preference([]) == [])
finally:
    if saved_primary is None:
        os.environ.pop("LLM_PRIMARY", None)
    else:
        os.environ["LLM_PRIMARY"] = saved_primary

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all tool-backend routing checks passed")
