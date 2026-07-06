"""
Base Agent Class for Nancy/Billion AI Assistant
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from utils.logger import get_logger

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
__all__ = ['BaseAgent']