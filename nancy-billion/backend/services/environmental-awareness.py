"""
Environmental Awareness Service for JARVIS-like Contextual Understanding
Analyzes environmental data to provide context-aware suggestions and adaptations
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class LightingCondition(Enum):
    DARK = "dark"
    DIM = "dim"
    MODERATE = "moderate"
    BRIGHT = "bright"
    GLARY = "glary"

class ActivityLevel(Enum):
    INACTIVE = "inactive"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"

@dataclass
class EnvironmentalContext:
    timestamp: datetime
    lighting: LightingCondition
    activity_level: ActivityLevel
    obstacle_proximity: str  # "close", "medium", "far", "none"
    suggested_adaptations: List[str]
    confidence: float

class EnvironmentalAwarenessService:
    def __init__(self):
        self.context_history: List[EnvironmentalContext] = []
        self.is_monitoring = False
        self._task: Optional[asyncio.Task] = None
        self.last_environmental_data: Optional[Dict] = None
        
    async def start_monitoring(self):
        """Start environmental monitoring"""
        if self.is_monitoring:
            return
            
        self.is_monitoring = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("Environmental Awareness Service started")
        
    async def stop_monitoring(self):
        """Stop environmental monitoring"""
        self.is_monitoring = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Environmental Awareness Service stopped")
        
    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.is_monitoring:
            try:
                # In a real implementation, this would get data from sensors/APIs
                # For now, we'll simulate or use mock data
                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in environmental monitoring loop: {e}")
                await asyncio.sleep(2)
                
    def update_environmental_data(self, environmental_data: Dict[str, Any]):
        """Update with new environmental data from frontend sensors"""
        try:
            context = self._analyze_environmental_data(environmental_data)
            self.last_environmental_data = environmental_data
            self.context_history.append(context)
            
            # Keep history limited
            if len(self.context_history) > 100:
                self.context_history = self.context_history[-50:]
                
            logger.debug(f"Environmental context updated: {context.lighting.value}, {context.activity_level.value}")
            
        except Exception as e:
            logger.error(f"Error updating environmental data: {e}")
            
    def _analyze_environmental_data(self, data: Dict[str, Any]) -> EnvironmentalContext:
        """Analyze raw environmental data to derive meaningful context"""
        # Analyze lighting
        lighting_ambient = data.get('lighting', {}).get('ambient', 0.5)
        if lighting_ambient < 0.2:
            lighting = LightingCondition.DARK
        elif lighting_ambient < 0.4:
            lighting = LightingCondition.DIM
        elif lighting_ambient < 0.7:
            lighting = LightingCondition.MODERATE
        elif lighting_ambient < 0.9:
            lighting = LightingCondition.BRIGHT
        else:
            lighting = LightingCondition.GLARY
            
        # Analyze activity level based on obstacles and movement
        obstacles = data.get('obstacles', [])
        close_obstacles = [o for o in obstacles if o.get('distance', 999) < 1.0]
        
        if len(close_obstacles) == 0:
            activity_level = ActivityLevel.INACTIVE
        elif len(close_obstacles) <= 2:
            activity_level = ActivityLevel.LOW
        elif len(close_obstacles) <= 4:
            activity_level = ActivityLevel.MODERATE
        elif len(close_obstacles) <= 6:
            activity_level = ActivityLevel.HIGH
        else:
            activity_level = ActivityLevel.VERY_HIGH
            
        # Determine obstacle proximity
        if obstacles:
            min_distance = min([o.get('distance', 999) for o in obstacles])
            if min_distance < 0.5:
                proximity = "close"
            elif min_distance < 2.0:
                proximity = "medium"
            else:
                proximity = "far"
        else:
            proximity = "none"
            
        # Generate suggested adaptations
        adaptations = self._generate_adaptations(lighting, activity_level, proximity)
        
        return EnvironmentalContext(
            timestamp=datetime.now(),
            lighting=lighting,
            activity_level=activity_level,
            obstacle_proximity=proximity,
            suggested_adaptations=adaptations,
            confidence=0.8  # Base confidence
        )
        
    def _generate_adaptations(self, lighting: LightingCondition, activity: ActivityLevel, proximity: str) -> List[str]:
        """Generate interface and behavior adaptations based on environmental context"""
        adaptations = []
        
        # Lighting adaptations
        if lighting == LightingCondition.DARK:
            adaptations.append("increase_interface_brightness")
            adaptations.append("enable_high_contrast_mode")
        elif lighting == LightingCondition.DIM:
            adaptations.append("slight_brightness_increase")
        elif lighting == LightingCondition.BRIGHT:
            adaptations.append("reduce_interface_brightness")
            adaptations.append("enable_glare_reduction")
        elif lighting == LightingCondition.GLARY:
            adaptations.append("significant_brightness_reduction")
            adaptations.append("enable_polarization_mode")
            
        # Activity level adaptations
        if activity == ActivityLevel.INACTIVE:
            adaptations.append("enable_ambient_information_display")
            adaptations.append("reduce_notification_frequency")
        elif activity == ActivityLevel.LOW:
            adaptations.append("standard_notification_handling")
        elif activity == ActivityLevel.MODERATE:
            adaptations.append("prioritize_important_notifications")
        elif activity == ActivityLevel.HIGH:
            adaptations.append("minimize_distractions")
            adaptations.append("enable_voice_only_mode")
        elif activity == ActivityLevel.VERY_HIGH:
            adaptations.append("enter_do_not_disturb_mode")
            adaptations.append("activate_emergency_protocols_only")
            
        # Proximity adaptations
        if proximity == "close":
            adaptations.append("increase_interface_element_size")
            adaptations.append("enable_gesture_controls")
        elif proximity == "far":
            adaptations.append("decrease_interface_density")
            adaptations.append("optimize_for_distance_viewing")
            
        return adaptations
        
    def get_current_context(self) -> Optional[EnvironmentalContext]:
        """Get the most recent environmental context"""
        if self.context_history:
            return self.context_history[-1]
        return None
        
    def get_context_for_suggestions(self) -> Dict[str, Any]:
        """Get environmental context formatted for proactive suggestions"""
        context = self.get_current_context()
        if not context:
            return {}
            
        return {
            "lighting": context.lighting.value,
            "activity_level": context.activity_level.value,
            "obstacle_proximity": context.obstacle_proximity,
            "suggested_adaptations": context.suggested_adaptations,
            "timestamp": context.timestamp.isoformat()
        }
        
    def should_suggest_environmental_adaptation(self) -> bool:
        """Determine if we should suggest environmental adaptations to the user"""
        context = self.get_current_context()
        if not context:
            return False
            
        # Suggest adaptations when conditions significantly deviate from ideal
        ideal_lighting = [LightingCondition.MODERATE, LightingCondition.BRIGHT]
        ideal_activity = [ActivityLevel.LOW, ActivityLevel.MODERATE]
        ideal_proximity = ["medium", "far"]
        
        needs_adaptation = (
            context.lighting not in ideal_lighting or
            context.activity_level not in ideal_activity or
            context.obstacle_proximity not in ideal_proximity
        )
        
        return needs_adaptation and len(context.suggested_adaptations) > 0

# Global instance
environmental_awareness_service = EnvironmentalAwarenessService()