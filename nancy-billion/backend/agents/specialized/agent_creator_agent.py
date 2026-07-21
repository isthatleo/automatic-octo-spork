"""
Agent Creator Agent for Nancy/Billion Backend

Exposes agent creation/deployment as a normal task-driven specialized agent
(reachable via /agents/run like any other), instead of only through Claude's
chat tool-use loop (see main_new.py's CREATE_SUBAGENT_TOOL /
_execute_create_subagent_tool, and subagent_factory.py, which this agent
wraps rather than re-implements).

Same risk tier and same two safeguards as the chat path, both mandatory:
  1. subagent_factory.validate_agent_code() -- static syntax/denylist check,
     run on every generated or caller-supplied module before it touches disk.
  2. Files are written ONLY to agents/specialized/dynamic/ (never anywhere
     else), matching dynamic_registry.py's discovery directory, and only
     take effect on the NEXT BACKEND RESTART -- there is no hot-reload.

Difference from the chat path: this agent is invoked as a deliberate,
explicit task call (POST /agents/run with agent_key="agent_creator") rather
than an autonomous decision Nancy makes mid-conversation, so it does not
gate on a Telegram approval round-trip the way _execute_create_subagent_tool
does -- the caller invoking this task IS the approval. The static safety
validation is not optional either way.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

_SCAFFOLD_TEMPLATE = '''"""
{class_name} -- created via the Agent Creator Agent (agent_creator_agent.py).
Domain: {domain}
{description}
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from agents.specialized.base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)


class {class_name}(SpecializedAgent):
    """{description}"""

    def __init__(self, settings):
        super().__init__(settings, "{display_name}", "{domain}")
        self.capabilities.update({{
            "description": "{description}",
            "confidence": 0.7,
            "specializations": {specializations!r},
            "tools": ["llm-chain"],
        }})

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "query")
        text = task_data.get("query") or task_data.get("task") or ""
        if not str(text).strip():
            return {{"success": False, "error": "A 'query' (or 'task') is required"}}
        answer = await self._llm_answer(str(text))
        if answer is None:
            return {{"success": False, "task_type": task_type, "query": text, "error": "LLM backend unavailable"}}
        return {{"success": True, "task_type": task_type, "query": text, "response": answer}}
'''


class AgentCreatorAgent(SpecializedAgent):
    """Meta-agent: designs, validates, and deploys new specialized agents into agents/specialized/dynamic/"""

    def __init__(self, settings):
        super().__init__(settings, "Agent Creator Agent", "agent-creator")
        self.capabilities.update({
            "description": (
                "Meta-agent that scaffolds, validates, and deploys new specialized agents into "
                "agents/specialized/dynamic/ -- the same static-safety-checked pipeline used by Nancy's "
                "own chat-driven agent creation (subagent_factory.py), exposed as a normal task."
            ),
            "confidence": 0.85,
            "specializations": [
                "agent-scaffolding",
                "agent-code-validation",
                "agent-deployment",
                "registry-introspection",
            ],
            "tools": ["subagent_factory", "dynamic_registry"],
            # New agents only take effect after a backend restart -- there is
            # no hot-reload of a running AgentService.
            "mode": "requires-restart-to-activate",
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "list_registry")
        try:
            if task_type == "list_registry":
                return self._list_registry()
            elif task_type == "scaffold":
                return self._scaffold(task_data)
            elif task_type == "validate":
                return self._validate(task_data)
            elif task_type == "deploy":
                return self._deploy(task_data)
            else:
                return await self._general_query(task_data)
        except Exception as e:
            logger.exception("AgentCreatorAgent task '%s' error: %s", task_type, e)
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def _list_registry(self) -> Dict[str, Any]:
        from .registry import SPECIALIZED_AGENTS
        from .dynamic_registry import DYNAMIC_AGENTS

        return {
            "success": True,
            "task_type": "list_registry",
            "curated_agents": sorted(SPECIALIZED_AGENTS.keys()),
            "curated_count": len(SPECIALIZED_AGENTS),
            "dynamic_agents": sorted(DYNAMIC_AGENTS.keys()),
            "dynamic_count": len(DYNAMIC_AGENTS),
            "dynamic_agents_directory": "agents/specialized/dynamic/",
            "note": "Dynamic agents only appear in the live AgentService after the backend has been "
                    "restarted since they were deployed.",
        }

    # ------------------------------------------------------------------
    # Deterministic code scaffolding (no LLM call -- a fixed, always-valid
    # template, so 'scaffold' output reliably passes validate_agent_code())
    # ------------------------------------------------------------------

    def _scaffold(self, params: Dict[str, Any]) -> Dict[str, Any]:
        key, class_name, domain, description, err = self._parse_agent_spec(params)
        if err:
            return {"success": False, "task_type": "scaffold", "error": err}

        display_name = str(params.get("display_name") or class_name.replace("Agent", " Agent")).strip()
        specializations: List[str] = list(params.get("specializations", []))

        code = _SCAFFOLD_TEMPLATE.format(
            class_name=class_name,
            domain=domain,
            description=description,
            display_name=display_name,
            specializations=specializations,
        )

        import subagent_factory  # deferred: top-level backend module, avoid import-order coupling
        validation = subagent_factory.validate_agent_code(key, class_name, code)

        return {
            "success": validation["ok"],
            "task_type": "scaffold",
            "key": key,
            "class_name": class_name,
            "domain": domain,
            "code": code,
            "validation": validation,
            "next_step": "Call this agent again with type='deploy' and the same key/class_name/domain/"
                         "description (or pass this 'code' directly) to write the file." if validation["ok"] else None,
        }

    # ------------------------------------------------------------------
    # Validation only (caller-supplied code, e.g. LLM-generated elsewhere)
    # ------------------------------------------------------------------

    def _validate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        key = str(params.get("key", "")).strip()
        class_name = str(params.get("class_name", "")).strip()
        code = str(params.get("code", ""))
        if not key or not class_name or not code:
            return {"success": False, "task_type": "validate", "error": "'key', 'class_name', and 'code' are all required"}

        import subagent_factory
        validation = subagent_factory.validate_agent_code(key, class_name, code)
        return {"success": validation["ok"], "task_type": "validate", "key": key, "validation": validation}

    # ------------------------------------------------------------------
    # Deploy: validate, then actually write the file to
    # agents/specialized/dynamic/<key>_agent.py
    # ------------------------------------------------------------------

    def _deploy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        import subagent_factory

        code = params.get("code")
        if code:
            key = str(params.get("key", "")).strip()
            class_name = str(params.get("class_name", "")).strip()
            if not key or not class_name:
                return {"success": False, "task_type": "deploy", "error": "'key' and 'class_name' are required alongside 'code'"}
            code = str(code)
        else:
            key, class_name, domain, description, err = self._parse_agent_spec(params)
            if err:
                return {"success": False, "task_type": "deploy", "error": err}
            scaffold_result = self._scaffold(params)
            if not scaffold_result["success"]:
                return {"success": False, "task_type": "deploy", "error": scaffold_result["validation"]["error"]}
            code = scaffold_result["code"]

        validation = subagent_factory.validate_agent_code(key, class_name, code)
        if not validation["ok"]:
            return {"success": False, "task_type": "deploy", "key": key, "error": validation["error"]}

        write_result = subagent_factory.write_agent_file(key, code)
        if write_result.get("success"):
            logger.info("AgentCreatorAgent: deployed new dynamic agent '%s' -> %s", key, write_result["path"])

        return {
            **write_result,
            "task_type": "deploy",
            "key": key,
            "class_name": class_name,
            "activation_note": "Written to agents/specialized/dynamic/ -- restart the backend to bring "
                                "this agent online; there is no hot-reload of a running AgentService.",
        }

    # ------------------------------------------------------------------
    # Shared validation of the (key, class_name, domain, description) spec
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_agent_spec(params: Dict[str, Any]) -> tuple[str, str, str, str, Optional[str]]:
        key = str(params.get("key", "")).strip()
        class_name = str(params.get("class_name", "")).strip()
        domain = str(params.get("domain", "")).strip()
        description = str(params.get("description", "")).strip()

        if not key:
            return key, class_name, domain, description, "'key' is required (lowercase_snake_case, e.g. 'weather_forecaster')"
        if not class_name:
            return key, class_name, domain, description, "'class_name' is required (PascalCase, e.g. 'WeatherForecasterAgent')"
        if not domain:
            domain = key.replace("_", "-")
        if not description:
            description = f"Specialized agent for {domain}"
        return key, class_name, domain, description, None

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        if not str(query).strip():
            return {
                "success": True,
                "task_type": "info",
                "response": (
                    "I create and deploy new specialized agents. Task types: list_registry, scaffold "
                    "(key, class_name, domain, description, specializations), validate (key, class_name, "
                    "code), deploy (either key+class_name+domain+description, or key+class_name+code)."
                ),
            }
        answer = await self._llm_answer(str(query))
        return {
            "success": True,
            "task_type": "query",
            "query": query,
            **({"response": answer} if answer else {}),
        }
