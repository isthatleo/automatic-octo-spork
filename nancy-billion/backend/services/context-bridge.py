"""
Context Bridge Service
Connects frontend environmental and usage data to backend proactive intelligence
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import importlib as _il
proactiveAssistant = _il.import_module('backend.services.proactive-assistant' if False else 'proactive_assistant_stub')
environmentAwarenessService = None
try:
    from .proactive_assistant import proactiveAssistant  # type: ignore
except ImportError:
    proactiveAssistant = None
try:
    from .environmental_awareness import environmentalAwarenessService  # type: ignore
except ImportError:
    environmentalAwarenessService = None

logger = logging.getLogger(__name__)

class ContextBridge:
    def __init__(self):
        self.is_connected = False
        self.last_frontend_update: Optional[Dict[str, Any]] = None
        
    async def start(self):
        """Start the context bridge"""
        if self.is_connected:
            return
            
        self.is_connected = True
        # Start backend services if not already started
        await proactiveAssistant.start()
        await environmentalAwarenessService.start_monitoring()
        logger.info("Context Bridge started")
        
    async def stop(self):
        """Stop the context bridge"""
        if not self.is_connected:
            return
            
        self.is_connected = False
        await proactiveAssistant.stop()
        await environmentalAwarenessService.stop_monitoring()
        logger.info("Context Bridge stopped")
        
    def update_from_frontend(self, frontend_data: Dict[str, Any]):
        """Update context from frontend data (environmental, usage patterns, etc.)"""
        try:
            self.last_frontend_update = {
                "timestamp": datetime.now().isoformat(),
                "data": frontend_data
            }
            
            # Update environmental awareness service
            if "environmental" in frontend_data:
                environmentalAwarenessService.update_environmental_data(
                    frontend_data["environmental"]
                )
                
            # Add context events to proactive assistant
            if "usage" in frontend_data:
                for event in frontend_data["usage"]:
                    proactiveAssistant.add_context_event(
                        event.get("type", "unknown"),
                        event.get("data", {})
                    )
                    
            # Check if we should generate context-aware suggestions
            self._maybe_generate_contextual_suggestions(frontend_data)
            
            logger.debug(f"Context bridge updated with frontend data: {list(frontend_data.keys())}")
            
        except Exception as e:
            logger.error(f"Error updating context from frontend: {e}")
            
    def _maybe_generate_contextual_suggestions(self, frontend_data: Dict[str, Any]):
        """Generate suggestions based on combined frontend and backend context"""
        try:
            # Get environmental context
            env_context = environmentalAwarenessService.get_context_for_suggestions()
            
            # Get time-based context
            now = datetime.now()
            hour = now.hour
            weekday = now.weekday()
            
            # Environmental-based suggestions
            if env_context:
                lighting = env_context.get("lighting", "moderate")
                activity = env_context.get("activity_level", "low")
                proximity = env_context.get("obstacle_proximity", "medium")
                
                # Lighting-based suggestions
                if lighting == "dark" or lighting == "dim":
                    # Suggest interface adjustments for low light
                    proactiveAssistant.add_context_event("interface_suggestion", {
                        "type": "lighting_adjustment",
                        "suggestion": "Increase interface brightness for better visibility in low light conditions",
                        "priority": "medium",
                        "action": "adjust_brightness",
                        "value": 0.8
                    })
                elif lighting == "bright" or lighting == "glary":
                    # Suggest interface adjustments for bright light
                    proactiveAssistant.add_context_event("interface_suggestion", {
                        "type": "lighting_adjustment",
                        "suggestion": "Reduce interface brightness to minimize glare",
                        "priority": "medium",
                        "action": "adjust_brightness",
                        "value": 0.4
                    })
                    
                # Activity-based suggestions
                if activity == "very_high":
                    proactiveAssistant.add_context_event("interface_suggestion", {
                        "type": "activity_adjustment",
                        "suggestion": "High activity detected - consider enabling focus mode",
                        "priority": "high",
                        "action": "suggest_focus_mode",
                        "reason": "High environmental activity"
                    })
                elif activity == "inactive" and 9 <= hour <= 17:
                    # Suggest productive activities during work hours when inactive
                    proactiveAssistant.add_context_event("interface_suggestion", {
                        "type": "productivity_suggestion",
                        "suggestion": "You've been inactive during work hours - would you like to review your task list?",
                        "priority": "low",
                        "action": "suggest_task_review",
                        "reason": "Work hour inactivity"
                    })
                    
                # Proximity-based suggestions
                if proximity == "close":
                    proactiveAssistant.add_context_event("interface_suggestion", {
                        "type": "proximity_adjustment",
                        "suggestion": "Objects detected close to device - consider increasing interface element size",
                        "priority": "low",
                        "action": "suggest_interface_scaling",
                        "factor": 1.2
                    })
                    
        except Exception as e:
            logger.error(f"Error generating contextual suggestions: {e}")
            
    def get_shared_context(self) -> Dict[str, Any]:
        """Get shared context for debugging or monitoring"""
        return {
            "bridge_status": "connected" if self.is_connected else "disconnected",
            "last_frontend_update": self.last_frontend_update,
            "environmental_context": environmentalAwarenessService.get_context_for_suggestions(),
            "proactive_suggestions_count": len(proactiveAssistant.get_active_suggestions()),
            "timestamp": datetime.now().isoformat()
        }

# Global instance
context_bridge = ContextBridge()