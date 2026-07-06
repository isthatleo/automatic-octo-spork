"""
Chief Autonomy Agent for Nancy Billion
Orchestrates autonomous decision-making across the agent ecosystem.
"""
from .specialized.base_specialized_agent import SpecializedAgent
from .specialized.registry import SPECIALIZED_AGENTS, create_agent
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ChiefAutonomyAgent:
    """Chief Autonomy Agent - orchestrates specialized agents for autonomous task execution"""

    def __init__(self, settings):
        self.settings = settings
        self.name = "Chief Autonomy Agent"
        self.domain = "chief-autonomy"
        self._initialized = False
        self._delegated_agents: Dict[str, Any] = {}

    async def initialize(self):
        logger.info("Initializing Chief Autonomy Agent")
        self._initialized = True

    async def process_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()
        ctx = context or {}
        task_keywords = {
            "data": "data_science", "crypto": "crypto_trading", "trade": "crypto_trading",
            "communicate": "communication", "email": "communication",
            "design": "creative_design", "ui": "creative_design", "ux": "creative_design",
            "deploy": "devops", "infrastructure": "devops", "ci/cd": "devops",
            "test": "qa_testing", "healthcare": "healthcare_analytics",
            "business": "business_intelligence", "market": "market_research",
            "optimize": "operations_research", "legal": "legal_compliance",
            "monitor": "system_monitoring", "security": "security",
            "file": "file_management", "astrophysics": "astrophysics",
            "quantum": "quantum_computing", "nano": "nanotechnology",
            "bio": "bioinformatics", "research": "research",
            "neural": "neural_interface", "holographic": "holographic_display",
            "environment": "environmental_control", "consciousness": "artificial_consciousness",
            "improve": "self_improvement", "ethical": "ethical_governance",
            "embodied": "embodied_cognition", "predict": "temporal_prediction",
            "swarm": "swarm_coordinator", "reason": "quantum_reasoning"
        }
        query_lower = query.lower()
        matched_agents = []
        for keyword, agent_key in task_keywords.items():
            if keyword in query_lower and agent_key in SPECIALIZED_AGENTS:
                matched_agents.append(agent_key)
        if not matched_agents:
            matched_agents = ["data_science"]

        for agent_key in matched_agents[:3]:
            try:
                agent = create_agent(agent_key, self.settings)
                result = await agent.process_task({"type": ctx.get("task_type", "general"), "query": query, **ctx})
                self._delegated_agents[agent_key] = result
            except Exception as e:
                logger.error(f"Error delegating to {agent_key}: {e}")

        return {
            "response": f"Processed query across {len(matched_agents)} domain(s): {', '.join(matched_agents)}",
            "agents_used": matched_agents,
            "confidence": 0.85,
            "results": {k: v for k, v in self._delegated_agents.items() if k in matched_agents}
        }

    async def shutdown(self):
        logger.info("Shutting down Chief Autonomy Agent")
        self._initialized = False
