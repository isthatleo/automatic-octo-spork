"""
Core Nancy/Billion AI Assistant Implementation
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from config.settings import Settings
from utils.logger import get_logger
from modules.system.monitor import SystemMonitor
from modules.system.diagnostics import SystemDiagnostics
from modules.system.recovery import AutoRecovery

class NancyBillionAssistant:
    """
    Main AI Assistant class implementing sovereign capabilities
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        
        # System state
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Core modules
        self.system_monitor = None
        self.system_diagnostics = None
        self.auto_recovery = None
        
        # Agent registry (to be expanded)
        self.agents = {}
        
        # Knowledge base (to be expanded)
        self.knowledge_base = {}
        
    async def start(self):
        """Start the assistant and all subsystems"""
        self.logger.info("Initializing Nancy/Billion AI Assistant...")
        
        try:
            # Initialize core system modules
            await self._initialize_system_modules()
            
            # Start monitoring and recovery systems
            await self._start_core_systems()
            
            # Load and initialize agents
            await self._initialize_agents()
            
            # Start API server (if enabled)
            if self.settings.api.enabled:
                await self._start_api_server()
            
            self._running = True
            self.logger.info("Nancy/Billion AI Assistant started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start assistant: {e}", exc_info=True)
            await self.shutdown()
            raise
    
    async def _initialize_system_modules(self):
        """Initialize system monitoring, diagnostics, and recovery modules"""
        self.logger.info("Initializing system modules...")
        
        # System monitoring
        self.system_monitor = SystemMonitor(
            log_dir=self.settings.system.log_dir
        )
        
        # System diagnostics
        self.system_diagnostics = SystemDiagnostics()
        
        # Auto-recovery system
        self.auto_recovery = AutoRecovery(
            log_dir=self.settings.system.recovery_log_dir
        )
        
        self.logger.info("System modules initialized")
    
    async def _start_core_systems(self):
        """Start core monitoring and recovery systems"""
        self.logger.info("Starting core systems...")
        
        # Start auto-recovery monitoring in background
        if self.settings.system.auto_recovery_enabled:
            self.auto_recovery.start_monitoring(
                check_interval=self.settings.system.monitoring_interval
            )
            self.logger.info("Auto-recovery monitoring started")
        
        # Start periodic system logging
        asyncio.create_task(self._periodic_system_logging())
        
    async def _periodic_system_logging(self):
        """Periodically log system status"""
        while self._running and not self._shutdown_event.is_set():
            try:
                # Take system snapshot and log it
                snapshot = self.system_monitor.get_system_snapshot()
                self.system_monitor.log_snapshot(snapshot)
                
                # Check for alerts
                alerts = self.system_monitor.check_alerts(snapshot)
                if alerts:
                    self.logger.warning(f"System alerts detected: {len(alerts)} issues")
                    
                # Wait for next interval
                await asyncio.sleep(self.settings.system.logging_interval)
                
            except Exception as e:
                self.logger.error(f"Error in periodic system logging: {e}")
                await asyncio.sleep(30)  # Wait longer on error
    
    async def _initialize_agents(self):
        """Initialize and register AI agents"""
        self.logger.info("Initializing AI agents...")
        
        # This will be expanded with actual agent implementations
        # For now, we'll register placeholder agents
        
        from agents.chief_autonomy import ChiefAutonomyAgent
        from agents.knowledge_synthesis import KnowledgeSynthesisAgent
        from agents.strategic_planning import StrategicPlanningAgent
        
        # Register agents
        self.agents['chief_autonomy'] = ChiefAutonomyAgent(self.settings)
        self.agents['knowledge_synthesis'] = KnowledgeSynthesisAgent(self.settings)
        self.agents['strategic_planning'] = StrategicPlanningAgent(self.settings)
        
        # Initialize all agents
        for name, agent in self.agents.items():
            try:
                await agent.initialize()
                self.logger.info(f"Initialized agent: {name}")
            except Exception as e:
                self.logger.error(f"Failed to initialize agent {name}: {e}")
    
    async def _start_api_server(self):
        """Start the API server for external communication"""
        self.logger.info("Starting API server...")
        
        # Import and start the API server
        try:
            from api.server import create_app
            import uvicorn
            
            app = create_app(self)
            
            config = uvicorn.Config(
                app,
                host=self.settings.api.host,
                port=self.settings.api.port,
                log_level="info"
            )
            
            server = uvicorn.Server(config)
            
            # Run server in background task
            asyncio.create_task(server.serve())
            self.logger.info(f"API server started on {self.settings.api.host}:{self.settings.api.port}")
            
        except ImportError as e:
            self.logger.warning(f"Could not start API server: {e}")
            self.logger.warning("API server dependencies may not be installed")
    
    async def shutdown(self):
        """Gracefully shutdown the assistant and all subsystems"""
        if not self._running:
            return
            
        self.logger.info("Shutting down Nancy/Billion AI Assistant...")
        self._running = False
        self._shutdown_event.set()
        
        # Shutdown all agents
        for name, agent in self.agents.items():
            try:
                await agent.shutdown()
                self.logger.info(f"Shutdown agent: {name}")
            except Exception as e:
                self.logger.error(f"Error shutting down agent {name}: {e}")
        
        # Stop monitoring systems
        if self.auto_recovery:
            self.auto_recovery.stop_monitoring()
        
        self.logger.info("Nancy/Billion AI Assistant shutdown complete")
    
    async def wait_for_shutdown(self):
        """Wait for shutdown signal"""
        await self._shutdown_event.wait()
    
    # Public interface methods
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get current system status"""
        if self.system_monitor:
            return self.system_monitor.get_system_snapshot()
        return {}
    
    async def run_diagnostics(self) -> Dict[str, Any]:
        """Run full system diagnostics"""
        if self.system_diagnostics:
            return self.system_diagnostics.run_full_diagnostics()
        return {}
    
    async def process_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a user query through the appropriate agents
        This is the main interface for user interaction
        """
        self.logger.info(f"Processing query: {query[:100]}...")
        
        # Route query to appropriate agents based on content
        # This is a simplified version - will be expanded with NLP understanding
        
        try:
            # For now, use the chief autonomy agent for general queries
            if 'chief_autonomy' in self.agents:
                result = await self.agents['chief_autonomy'].process_query(query, context)
                return result
            else:
                return {
                    'response': "Assistant is initializing...",
                    'agents_used': [],
                    'confidence': 0.1
                }
        except Exception as e:
            self.logger.error(f"Error processing query: {e}")
            return {
                'response': f"I encountered an error processing your request: {str(e)}",
                'agents_used': [],
                'confidence': 0.0,
                'error': str(e)
            }

# Export for easy importing
__all__ = ['NancyBillionAssistant']