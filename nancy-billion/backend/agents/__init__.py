"""
Agents Package for Nancy Billion
Contains the base agent system, specialized domain agents, and agent orchestration.
"""

from .base import BaseAgent
from .specialized import (
    SpecializedAgent,
    SPECIALIZED_AGENTS,
    get_available_agents,
    create_agent,
)
from .chief_autonomy import ChiefAutonomyAgent
from .knowledge_synthesis import KnowledgeSynthesisAgent
from .strategic_planning import StrategicPlanningAgent

__all__ = [
    "BaseAgent",
    "SpecializedAgent",
    "SPECIALIZED_AGENTS",
    "get_available_agents",
    "create_agent",
    "ChiefAutonomyAgent",
    "KnowledgeSynthesisAgent",
    "StrategicPlanningAgent",
]
