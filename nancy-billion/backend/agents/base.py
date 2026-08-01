"""
Base Agent Class for Nancy/Billion AI Assistant
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import Dict, Any, Optional
from utils.logger import get_logger

# Real recent conversation history for whichever turn is currently routing
# to a specialized agent -- set by main_new.py right before dispatching to
# agent_service.run() (the "query" task type from _generate_response_via_hierarchy_impl's
# keyword-routed branch), read by SpecializedAgent._llm_answer
# (base_specialized_agent.py) so a routed agent's generic LLM-backed
# fallback actually continues the conversation instead of answering the
# current message in total isolation.
#
# Confirmed live: a real Telegram conversation asked to continue a topic,
# got one coherent reply, then the very next message -- whose wording
# happened to match a specialized agent's routing keywords -- got a
# completely unrelated answer, because that agent's own prompt-building
# (_llm_answer) never had access to anything said before it. A ContextVar
# is the same pattern main_new.py already uses for per-turn voice_match/
# speaker_profile_id/turn_audio: it reaches every agent's _llm_answer call
# without needing every one of the ~70 specialized agent files to thread a
# new parameter through their own process_task/_general methods.
_current_conversation_context: ContextVar[str] = ContextVar("_current_conversation_context", default="")


class BaseAgent(ABC):
    """
    Base class for all AI agents in the Nancy/Billion system
    """
    
    def __init__(self, settings):
        self.settings = settings
        self.logger = get_logger(self.__class__.__name__)
        self._initialized = False
        self._running = False
        
    @abstractmethod
    async def initialize(self):
        """Initialize the agent"""
        pass
    
    @abstractmethod
    async def process_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a query and return a response
        
        Args:
            query: The user query or command
            context: Optional context information
            
        Returns:
            Dictionary containing response and metadata
        """
        pass
    
    async def startup(self):
        """Start the agent (called after initialization)"""
        self._running = True
        self.logger.info(f"Agent {self.__class__.__name__} started")
    
    async def shutdown(self):
        """Shutdown the agent gracefully"""
        self._running = False
        self.logger.info(f"Agent {self.__class__.__name__} shutdown")
    
    def is_ready(self) -> bool:
        """Check if agent is initialized and ready"""
        return self._initialized and self._running
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status information"""
        return {
            'name': self.__class__.__name__,
            'initialized': self._initialized,
            'running': self._running,
            'ready': self.is_ready()
        }

# Export for easy importing
__all__ = ['BaseAgent', '_current_conversation_context']