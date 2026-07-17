"""Registry for agents Nancy creates herself (see backend/subagent_factory.py).

Kept entirely separate from registry.py's curated SPECIALIZED_AGENTS so
creating a new agent never means programmatically editing that file's
source -- text-surgery on a hand-written registry is exactly the kind of
thing that silently corrupts a working file. Instead, self-created agents
live in agents/specialized/dynamic/ as their own *_agent.py files; this
module scans that directory, imports each one, and picks out its
SpecializedAgent subclass automatically.

New agents only take effect on the next backend restart -- there is no
hot-reload of a running AgentService, which would risk destabilizing agents
already in use.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Dict, Type

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

DYNAMIC_DIR = Path(__file__).parent / "dynamic"


def _discover_dynamic_agents() -> Dict[str, Type[SpecializedAgent]]:
    agents: Dict[str, Type[SpecializedAgent]] = {}
    if not DYNAMIC_DIR.is_dir():
        return agents

    for _finder, module_name, is_pkg in pkgutil.iter_modules([str(DYNAMIC_DIR)]):
        if is_pkg or not module_name.endswith("_agent"):
            continue
        try:
            module = importlib.import_module(f"agents.specialized.dynamic.{module_name}")
        except Exception as e:
            logger.warning("Dynamic agent module '%s' failed to import, skipping: %s", module_name, e)
            continue

        found = None
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj is SpecializedAgent:
                continue
            if issubclass(obj, SpecializedAgent) and obj.__module__ == module.__name__:
                found = obj
                break

        if found is None:
            logger.warning(
                "Dynamic agent module '%s' has no SpecializedAgent subclass, skipping", module_name
            )
            continue

        key = module_name[: -len("_agent")]
        agents[key] = found
        logger.info("Discovered dynamic agent '%s' -> %s", key, found.__name__)

    return agents


DYNAMIC_AGENTS: Dict[str, Type[SpecializedAgent]] = _discover_dynamic_agents()
