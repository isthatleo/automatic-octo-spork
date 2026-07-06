import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _registry_path() -> str:
    # Keep it under nancy-billion/data so it persists with the service.
    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    return os.path.join(root, "agent_registry.json")


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    category: str
    role: str
    description: str
    system_prompt: str
    tool_ids: List[str]
    memory_domains: List[str]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AgentSpec":
        return AgentSpec(
            key=str(d.get("key") or d.get("id") or ""),
            name=str(d.get("name") or d.get("key") or ""),
            category=str(d.get("category") or ""),
            role=str(d.get("role") or ""),
            description=str(d.get("description") or ""),
            system_prompt=str(d.get("system_prompt") or d.get("systemPrompt") or ""),
            tool_ids=list(d.get("tool_ids") or d.get("tools") or []),
            memory_domains=list(d.get("memory_domains") or d.get("memory") or []),
        )


class AgentRegistry:
    def __init__(self, spec_by_key: Dict[str, AgentSpec]):
        self._spec_by_key = spec_by_key

    @property
    def keys(self) -> List[str]:
        return sorted(self._spec_by_key.keys())

    def has(self, agent_key: str) -> bool:
        return agent_key in self._spec_by_key

    def get(self, agent_key: str) -> AgentSpec:
        if agent_key not in self._spec_by_key:
            raise KeyError(f"Unknown agent_key: {agent_key}")
        return self._spec_by_key[agent_key]


def load_registry(registry_path: Optional[str] = None) -> AgentRegistry:
    path = registry_path or _registry_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"Agent registry not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Accept shapes:
    # - {"agents": [ ... ]}
    # - {"agents_by_key": {"k": {...}}}
    # - {"...": ...} fallback
    spec_by_key: Dict[str, AgentSpec] = {}

    if isinstance(raw, dict) and "agents_by_key" in raw:
        for k, v in (raw.get("agents_by_key") or {}).items():
            v2 = dict(v or {})
            v2.setdefault("key", k)
            spec = AgentSpec.from_dict(v2)
            if spec.key:
                spec_by_key[spec.key] = spec
    else:
        agents = None
        if isinstance(raw, dict):
            agents = raw.get("agents") or raw.get("data")
        if agents is None:
            # If file itself is a list, accept that.
            agents = raw if isinstance(raw, list) else []

        if not isinstance(agents, list):
            raise ValueError(f"Unsupported registry format in {path}")

        for d in agents:
            if not isinstance(d, dict):
                continue
            spec = AgentSpec.from_dict(d)
            if spec.key:
                spec_by_key[spec.key] = spec

    if not spec_by_key:
        raise ValueError(f"Agent registry loaded but no agents found: {path}")

    logger.info(f"Loaded agent registry: {len(spec_by_key)} agents from {path}")
    return AgentRegistry(spec_by_key)


def sanitize_tool_ids(tool_ids: List[str]) -> List[str]:
    # Ensure unique & stable order.
    seen = set()
    out: List[str] = []
    for t in tool_ids or []:
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def filter_tools_by_ids(all_tools: List[Any], tool_ids: List[str]) -> List[Any]:
    """Filter Fury tools by tool.id if present."""
    allowed = set(sanitize_tool_ids(tool_ids))
    if not allowed:
        return all_tools

    filtered = []
    for tool in all_tools:
        tid = getattr(tool, "id", None)
        if tid in allowed:
            filtered.append(tool)

    if not filtered:
        # If agent declares tool ids that don't exist, fall back to all tools.
        logger.warning(
            "No tools matched tool_ids=%s; falling back to all registered tools", tool_ids
        )
        return all_tools

    return filtered

