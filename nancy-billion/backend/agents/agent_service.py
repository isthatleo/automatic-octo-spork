"""
AgentService — Runtime singleton that owns all 29 specialized agents.

Usage (from main_new.py):
    from agents.agent_service import agent_service
    await agent_service.initialize()
    result = await agent_service.run("quantum_reasoning", {"type": "qrng", "n_bits": 128})
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auto-routing keyword → agent key table
# ---------------------------------------------------------------------------
_ROUTE_RULES: List[tuple[list[str], str]] = [
    (["consciousness", "awareness", "introspect", "qualia", "sentien"],           "artificial_consciousness"),
    (["self-improv", "evolve", "distill", "meta-learn", "nas", "neural arch"],   "self_improvement"),
    (["ethic", "moral", "governance", "policy", "consent", "fairness"],          "ethical_governance"),
    (["robot", "arm", "kinematics", "haptic", "embodied", "sensor", "actuator"], "embodied_cognition"),
    (["forecast", "predict", "future", "temporal", "causal", "counterfactual"],  "temporal_prediction"),
    (["swarm", "multi-agent", "coordinate", "consensus", "fleet"],               "swarm_coordinator"),
    (["quantum", "qrng", "qubit", "circuit", "vqe", "qaoa", "qkd"],             "quantum_reasoning"),
    (["data sci", "ml", "machine learn", "model train", "dataset", "feature"],   "data_science"),
    (["crypto", "bitcoin", "ethereum", "defi", "blockchain", "token", "nft"],    "crypto_trading"),
    (["email", "message", "sms", "communicate", "draft", "reply"],               "communication"),
    (["design", "ui", "ux", "figma", "prototype", "wireframe", "brand"],         "creative_design"),
    (["devops", "deploy", "docker", "kubernetes", "ci/cd", "pipeline", "infra"], "devops"),
    (["test", "qa", "coverage", "unit test", "integration", "bug"],              "qa_testing"),
    (["health", "medical", "patient", "clinical", "diagnosis", "drug"],          "healthcare_analytics"),
    (["business intell", "kpi", "dashboard", "report", "metric", "bi"],         "business_intelligence"),
    (["market research", "competitive", "survey", "segment", "consumer"],        "market_research"),
    (["operations", "supply chain", "logistics", "optim", "scheduling"],         "operations_research"),
    (["legal", "contract", "compliance", "regulation", "law", "gdpr"],           "legal_compliance"),
    (["monitor", "alert", "cpu", "memory", "system health", "uptime"],           "system_monitoring"),
    (["security", "threat", "vulnerab", "pentest", "firewall", "malware"],       "security"),
    (["file", "folder", "document", "storage", "backup", "organise"],            "file_management"),
    (["astrophys", "star", "galaxy", "cosmolog", "telescope", "orbit"],          "astrophysics"),
    (["quantum comput", "quant circuit", "grover", "shor", "quantum gate"],      "quantum_computing"),
    (["nano", "nanomater", "molecular", "atomic scale", "nanotech"],             "nanotechnology"),
    (["bioinformat", "genome", "protein", "dna", "rna", "sequence", "blast"],    "bioinformatics"),
    (["nuclear", "radioactiv", "isotope", "reactor", "fission", "fusion", "half-life", "radiation dose", "fuel cycle", "iaea"], "nuclear_research"),
    (["physics research", "chemistry research", "biology research", "physical constant", "unit conversion", "experiment design", "sample size", "power analysis"], "science_research"),
    (["research brief", "look up", "fact find", "compare topics", "related topics"], "general_research"),
    (["create agent", "new agent", "deploy agent", "scaffold agent", "spawn agent", "subagent"], "agent_creator"),
    (["research", "literature", "paper", "study", "academic", "survey"],         "research"),
    (["neural interface", "brain-computer", "bci", "eeg", "neuroprosth"],        "neural_interface"),
    (["holograph", "display", "ar ", "mixed reality", "spatial"],                "holographic_display"),
    (["environment", "climate", "hvac", "smart home", "iot", "sensor"],          "environmental_control"),
]


def _auto_route(text: str) -> Optional[str]:
    """Return best agent key for a natural-language text, or None."""
    lower = text.lower()
    best_key: Optional[str] = None
    best_score = 0
    for keywords, agent_key in _ROUTE_RULES:
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            best_key = agent_key
    return best_key if best_score > 0 else None


# ---------------------------------------------------------------------------
# AgentService
# ---------------------------------------------------------------------------

class AgentService:
    """Singleton service that owns and manages all specialized agents."""

    def __init__(self) -> None:
        self._agents: Dict[str, Any] = {}
        self._initialized = False
        self._init_errors: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, settings=None) -> None:
        """Instantiate every agent registered in SPECIALIZED_AGENTS."""
        if self._initialized:
            return

        logger.info("AgentService: initialising all specialized agents…")
        from agents.specialized.registry import SPECIALIZED_AGENTS
        from agents.specialized.dynamic_registry import DYNAMIC_AGENTS

        if DYNAMIC_AGENTS:
            logger.info("Loading %d self-created dynamic agent(s): %s",
                        len(DYNAMIC_AGENTS), list(DYNAMIC_AGENTS.keys()))

        all_agents = {**SPECIALIZED_AGENTS}
        for key, cls in DYNAMIC_AGENTS.items():
            if key in all_agents:
                logger.warning("Dynamic agent key '%s' collides with a curated agent, skipping", key)
                continue
            all_agents[key] = cls

        tasks = []
        for key, cls in all_agents.items():
            tasks.append(self._init_one(key, cls, settings))

        await asyncio.gather(*tasks, return_exceptions=True)

        ok  = len(self._agents)
        err = len(self._init_errors)
        logger.info("AgentService ready: %d agents OK, %d errors.", ok, err)
        if self._init_errors:
            for k, e in self._init_errors.items():
                logger.warning("  [SKIP] %s: %s", k, e)

        self._initialized = True

    async def _init_one(self, key: str, cls, settings) -> None:
        try:
            agent = cls(settings=settings)
            await agent.initialize()
            self._agents[key] = agent
            logger.debug("  [OK] %s (%s)", key, cls.__name__)
        except Exception as exc:
            self._init_errors[key] = str(exc)
            logger.warning("  [FAIL] %s: %s", key, exc)

    async def shutdown(self) -> None:
        """Shutdown all agents gracefully."""
        tasks = [a.shutdown() for a in self._agents.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._agents.clear()
        self._initialized = False
        logger.info("AgentService shut down.")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(
        self,
        agent_key: str,
        task_data: Dict[str, Any],
        *,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Execute a task on the given agent and return its result.

        Args:
            agent_key:  Key from SPECIALIZED_AGENTS (e.g. "quantum_reasoning")
            task_data:  Dict with at least {"type": <str>} plus agent-specific fields.
            timeout:    Max seconds to wait.

        Returns:
            Dict with at least {"success": bool, "agent_key": str, ...}
        """
        agent = self._agents.get(agent_key)
        if agent is None:
            available = list(self._agents.keys())
            err = (f"Agent '{agent_key}' not found or failed to initialise. "
                   f"Available: {available}")
            logger.error(err)
            return {"success": False, "error": err, "agent_key": agent_key}

        start = time.time()
        try:
            result = await asyncio.wait_for(
                agent.run_task(task_data),
                timeout=timeout,
            )
            result.setdefault("agent_key", agent_key)
            result.setdefault("latency_ms", round((time.time() - start) * 1000, 2))
            return result
        except asyncio.TimeoutError:
            return {
                "success":   False,
                "error":     f"Agent '{agent_key}' timed out after {timeout}s",
                "agent_key": agent_key,
                "latency_ms": round((time.time() - start) * 1000, 2),
            }
        except Exception as exc:
            logger.exception("AgentService.run error [%s]: %s", agent_key, exc)
            return {
                "success":   False,
                "error":     str(exc),
                "agent_key": agent_key,
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

    async def auto_run(
        self,
        text: str,
        fallback_key: str = "research",
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Auto-route natural language `text` to the best agent and run it.
        Falls back to `fallback_key` if routing fails.
        """
        key = _auto_route(text) or fallback_key
        task_data = {"type": "query", "query": text}
        result = await self.run(key, task_data, timeout=timeout)
        result["routed_to"] = key
        return result

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_agents(self) -> List[Dict[str, Any]]:
        """Return lightweight info dicts for all initialised agents."""
        agents = []
        for key, agent in self._agents.items():
            try:
                info = agent.get_info()
            except Exception:
                info = {"name": key, "domain": key, "status": "error"}
            info["key"] = key
            agents.append(info)
        # Failed agents appear as offline entries
        for key, err in self._init_errors.items():
            agents.append({
                "key":    key,
                "name":   key,
                "domain": key,
                "status": "offline",
                "error":  err,
                "load":   0,
                "confidence": 0.0,
                "specializations": [],
                "total_tasks": 0,
            })
        agents.sort(key=lambda x: x.get("name", ""))
        return agents

    def get_agent_status(self, agent_key: str) -> Dict[str, Any]:
        """Full status for a single agent."""
        agent = self._agents.get(agent_key)
        if agent is None:
            return {"error": f"Agent '{agent_key}' not found", "status": "offline"}
        try:
            return agent.get_status()
        except Exception as exc:
            return {"error": str(exc), "status": "error"}

    def get_service_stats(self) -> Dict[str, Any]:
        """Aggregate stats across all agents."""
        total   = sum(getattr(a, "_total_tasks",  0) for a in self._agents.values())
        failed  = sum(getattr(a, "_failed_tasks", 0) for a in self._agents.values())
        queued  = sum(len(getattr(a, "task_queue", [])) for a in self._agents.values())
        return {
            "agents_online":  len(self._agents),
            "agents_offline": len(self._init_errors),
            "total_tasks":    total,
            "failed_tasks":   failed,
            "queued_tasks":   queued,
            "success_rate":   round((total - failed) / max(total, 1), 4),
        }

    def is_ready(self) -> bool:
        return self._initialized and bool(self._agents)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
agent_service = AgentService()
