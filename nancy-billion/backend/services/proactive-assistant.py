"""
Proactive Assistant Service for JARVIS-like Anticipatory Computing
Analyzes user patterns, calendar, and context to provide anticipatory suggestions
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class SuggestionType(Enum):
    CALENDAR_PREP = "calendar_prep"
    EMAIL_RESPONSE = "email_response"
    INFORMATION_GATHER = "information_gather"
    TASK_REMINDER = "task_reminder"
    CONTEXTUAL_HELP = "contextual_help"
    ROUTINE_OPTIMIZATION = "routine_optimization"

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

@dataclass
class ProactiveSuggestion:
    id: str
    type: SuggestionType
    priority: Priority
    title: str
    description: str
    action_text: str
    action_data: Dict[str, Any]
    expires_at: datetime
    context: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    created_at: datetime

class ProactiveAssistant:
    def __init__(self):
        self.suggestions: Dict[str, ProactiveSuggestion] = {}
        self.user_patterns: Dict[str, Any] = {}
        self.context_history: List[Dict] = []
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the proactive assistant background service"""
        if self.is_running:
            return
            
        self.is_running = True
        self._task = asyncio.create_task(self._run_background_loop())
        logger.info("Proactive Assistant started")
        
    async def stop(self):
        """Stop the proactive assistant background service"""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Proactive Assistant stopped")
        
    async def _run_background_loop(self):
        """Background loop for generating proactive suggestions"""
        while self.is_running:
            try:
                await self._generate_suggestions()
                await self._cleanup_expired_suggestions()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in proactive assistant loop: {e}")
                await asyncio.sleep(5)
                
    async def _generate_suggestions(self):
        """Generate proactive suggestions based on current context"""
        try:
            # Get current context (would integrate with actual services)
            context = await self._gather_context()
            
            # Generate different types of suggestions
            suggestions = []
            
            # Calendar-based suggestions
            calendar_suggestions = await self._generate_calendar_suggestions(context)
            suggestions.extend(calendar_suggestions)
            
            # Email/Communication suggestions
            email_suggestions = await self._generate_email_suggestions(context)
            suggestions.extend(email_suggestions)
            
            # Information gathering suggestions
            info_suggestions = await self._generate_information_suggestions(context)
            suggestions.extend(info_suggestions)
            
            # Routine optimization suggestions
            routine_suggestions = await self._generate_routine_suggestions(context)
            suggestions.extend(routine_suggestions)
            
            # Add new suggestions
            for suggestion in suggestions:
                if suggestion.id not in self.suggestions:
                    self.suggestions[suggestion.id] = suggestion
                    logger.info(f"Generated proactive suggestion: {suggestion.title}")
                    
        except Exception as e:
            logger.error(f"Error generating suggestions: {e}")
            
    async def _gather_context(self) -> Dict[str, Any]:
        """Gather current context from various sources"""
        # In a real implementation, this would integrate with:
        # - Calendar service
        # - Email service
        # - Location service
        # - Application usage
        # - Time of day patterns
        # etc.
        
        now = datetime.now()
        return {
            "time": now,
            "day_of_week": now.weekday(),  # 0=Monday, 6=Sunday
            "hour": now.hour,
            "is_work_hour": 9 <= now.hour <= 17,
            "recent_activity": self.context_history[-10:] if self.context_history else [],
            "user_patterns": self.user_patterns,
            # Mock data for demonstration
            "upcoming_events": self._get_mock_calendar_events(),
            "recent_emails": self._get_mock_recent_emails(),
            "current_location": "Home Office",
            "weather": {"condition": "clear", "temperature": 22}
        }
        
    def _get_mock_calendar_events(self) -> List[Dict]:
        """Mock calendar events for demonstration"""
        now = datetime.now()
        return [
            {
                "id": "evt_001",
                "title": "Project Review Meeting",
                "start": now + timedelta(hours=2),
                "end": now + timedelta(hours=3),
                "location": "Conference Room B",
                "participants": ["alice@company.com", "bob@company.com"],
                "description": "Quarterly project review - prepare budget slides"
            },
            {
                "id": "evt_002", 
                "title": "Team Sync",
                "start": now + timedelta(days=1, hours=10),
                "end": now + timedelta(days=1, hours=11),
                "location": "Virtual",
                "participants": ["team@company.com"],
                "description": "Daily team standup"
            }
        ]
        
    def _get_mock_recent_emails(self) -> List[Dict]:
        """Mock recent emails for demonstration"""
        return [
            {
                "id": "email_001",
                "subject": "Follow up on project proposal",
                "sender": "client@external.com",
                "received": datetime.now() - timedelta(hours=1),
                "preview": "Thanks for sending over the proposal...",
                "priority": "normal"
            },
            {
                "id": "email_002",
                "subject": "URGENT: Server maintenance tonight",
                "sender": "it@company.com", 
                "received": datetime.now() - timedelta(minutes=30),
                "preview": "Scheduled maintenance will occur from 2-4 AM...",
                "priority": "high"
            }
        ]
        
    async def _generate_calendar_suggestions(self, context: Dict[str, Any]) -> List[ProactiveSuggestion]:
        """Generate calendar-based proactive suggestions"""
        suggestions = []
        upcoming_events = context.get("upcoming_events", [])
        now = context["time"]
        
        for event in upcoming_events:
            start_time = event["start"]
            time_until = start_time - now
            
            # Suggest preparation 30 minutes before meeting
            if timedelta(minutes=25) <= time_until <= timedelta(minutes=35):
                suggestion = ProactiveSuggestion(
                    id=f"cal_prep_{event['id']}_{int(now.timestamp())}",
                    type=SuggestionType.CALENDAR_PREP,
                    priority=Priority.HIGH,
                    title=f"Prepare for: {event['title']}",
                    description=f"Meeting starts in {int(time_until.total_seconds() / 60)} minutes. "
                              f"Location: {event['location']}. Participants: {', '.join(event['participants'][:2])}{'...' if len(event['participants']) > 2 else ''}",
                    action_text="Review Meeting Details",
                    action_data={
                        "event_id": event["id"],
                        "meeting_info": event
                    },
                    expires_at=start_time,
                    context={"event": event},
                    confidence=0.9
                )
                suggestions.append(suggestion)
                
            # Suggest travel time if needed
            elif timedelta(minutes=55) <= time_until <= timedelta(minutes=65):
                if event.get("location") and event["location"] != "Virtual":
                    suggestion = ProactiveSuggestion(
                        id=f"cal_travel_{event['id']}_{int(now.timestamp())}",
                        type=SuggestionType.CALENDAR_PREP,
                        priority=Priority.MEDIUM,
                        title=f"Time to leave for: {event['title']}",
                        description=f"Meeting starts in {int(time_until.total_seconds() / 60)} minutes. "
                                  f"Consider travel time to {event['location']}",
                        action_text="Get Directions",
                        action_data={
                            "event_id": event["id"],
                            "destination": event["location"]
                        },
                        expires_at=start_time - timedelta(minutes=15),
                        context={"event": event},
                        confidence=0.8
                    )
                    suggestions.append(suggestion)
                    
        return suggestions
        
    async def _generate_email_suggestions(self, context: Dict[str, Any]) -> List[ProactiveSuggestion]:
        """Generate email-related proactive suggestions"""
        suggestions = []
        recent_emails = context.get("recent_emails", [])
        now = context["time"]
        
        for email in recent_emails:
            # Suggest responding to important emails after some time
            time_since = now - email["received"]
            if timedelta(minutes=10) <= time_since <= timedelta(hours=2) and email["priority"] in ["high", "urgent"]:
                suggestion = ProactiveSuggestion(
                    id=f"email_reply_{email['id']}_{int(now.timestamp())}",
                    type=SuggestionType.EMAIL_RESPONSE,
                    priority=Priority.HIGH if email["priority"] == "urgent" else Priority.MEDIUM,
                    title=f"Follow up: {email['subject']}",
                    description=f"Received {int(time_since.total_seconds() / 60)} minutes ago from {email['sender']}. "
                              f"Consider sending a response.",
                    action_text="Draft Response",
                    action_data={
                        "email_id": email["id"],
                        "original_email": email
                    },
                    expires_at=now + timedelta(hours=4),
                    context={"email": email},
                    confidence=0.7
                )
                suggestions.append(suggestion)
                
        return suggestions
        
    async def _generate_information_suggestions(self, context: Dict[str, Any]) -> List[ProactiveSuggestion]:
        """Generate information gathering suggestions"""
        suggestions = []
        now = context["time"]
        
        # Morning briefing suggestion
        if 6 <= now.hour <= 9 and context.get("is_work_hour"):
            # Check if we haven't given this suggestion recently
            recent_briefings = [s for s in self.suggestions.values() 
                              if s.type == SuggestionType.INFORMATION_GATHER 
                              and "morning" in s.title.lower()
                              and (now - s.created_at).total_seconds() < 3600]  # Last hour
                              
            if not recent_briefings:
                suggestion = ProactiveSuggestion(
                    id=f"morning_brief_{int(now.timestamp())}",
                    type=SuggestionType.INFORMATION_GATHER,
                    priority=Priority.MEDIUM,
                    title="Morning Briefing Ready",
                    description="Good morning! Would you like me to prepare your daily briefing with calendar, weather, and priority items?",
                    action_text="Start Briefing",
                    action_data={
                        "briefing_type": "morning",
                        "include_weather": True,
                        "include_calendar": True,
                        "include_news": True
                    },
                    expires_at=now + timedelta(hours=3),
                    context={"time_of_day": "morning"},
                    confidence=0.8
                )
                suggestions.append(suggestion)
                
        # Evening wrap-up suggestion
        elif 17 <= now.hour <= 19 and context.get("is_work_hour"):
            recent_wrap_ups = [s for s in self.suggestions.values()
                             if s.type == SuggestionType.INFORMATION_GATHER
                             and "wrap" in s.title.lower()
                             and (now - s.created_at).total_seconds() < 3600]
                             
            if not recent_wrap_ups:
                suggestion = ProactiveSuggestion(
                    id=f"evening_wrap_{int(now.timestamp())}",
                    type=SuggestionType.INFORMATION_GATHER,
                    priority=Priority.MEDIUM,
                    title="End of Day Wrap-up",
                    description="Work day ending soon. Would you like me to summarize accomplishments and prepare for tomorrow?",
                    action_text="Generate Summary",
                    action_data={
                        "summary_type": "evening",
                        "include_tomorrow_prep": True,
                        "include_pending_tasks": True
                    },
                    expires_at=now + timedelta(hours=2),
                    context={"time_of_day": "evening"},
                    confidence=0.75
                )
                suggestions.append(suggestion)
                
        return suggestions
        
    async def _generate_routine_suggestions(self, context: Dict[str, Any]) -> List[ProactiveSuggestion]:
        """Generate routine optimization suggestions"""
        suggestions = []
        
        # Learn user patterns over time (simplified)
        hour = context["hour"]
        weekday = context["day_of_week"]
        
        pattern_key = f"{weekday}_{hour}"
        if pattern_key not in self.user_patterns:
            self.user_patterns[pattern_key] = {"count": 1, "last_seen": context["time"]}
        else:
            self.user_patterns[pattern_key]["count"] += 1
            self.user_patterns[pattern_key]["last_seen"] = context["time"]
            
        # Suggest routine optimization after seeing pattern 5+ times
        if self.user_patterns[pattern_key]["count"] >= 5:
            # Check if we've already suggested optimization for this pattern
            recent_optimizations = [s for s in self.suggestions.values()
                                  if s.type == SuggestionType.ROUTINE_OPTIMIZATION
                                  and pattern_key in s.context.get("pattern_key", "")
                                  and (now - s.created_at).total_seconds() < 7200]  # Last 2 hours
                                  
            if not recent_optimizations:
                now = context["time"]
                suggestion = ProactiveSuggestion(
                    id=f"routine_opt_{pattern_key}_{int(now.timestamp())}",
                    type=SuggestionType.ROUTINE_OPTIMIZATION,
                    priority=Priority.LOW,
                    title="Routine Optimization Available",
                    description=f"I've noticed you often work on similar tasks around {hour:02d}:00 on {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][weekday]}. "
                              f"Would you like me to prepare your usual workflow?",
                    action_text="Prepare Workflow",
                    action_data={
                        "pattern_key": pattern_key,
                        "suggested_actions": ["Open development environment", "Load project files", "Check notifications"]
                    },
                    expires_at=now + timedelta(hours=4),
                    context={"pattern_key": pattern_key, "frequency": self.user_patterns[pattern_key]["count"]},
                    confidence=0.6
                )
                suggestions.append(suggestion)
                
        return suggestions
        
    async def _cleanup_expired_suggestions(self):
        """Remove expired suggestions"""
        now = datetime.now()
        expired_ids = [
            sug_id for sug_id, suggestion in self.suggestions.items()
            if suggestion.expires_at < now
        ]
        
        for sug_id in expired_ids:
            del self.suggestions[sug_id]
            logger.debug(f"Expired suggestion removed: {sug_id}")
            
    def get_active_suggestions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get currently active suggestions sorted by priority and confidence"""
        now = datetime.now()
        active = [
            suggestion for suggestion in self.suggestions.values()
            if suggestion.expires_at > now
        ]
        
        # Sort by priority (descending) then confidence (descending)
        active.sort(key=lambda s: (-s.priority.value, -s.confidence))
        
        return [asdict(suggestion) for suggestion in active[:limit]]
        
    def add_context_event(self, event_type: str, data: Dict[str, Any]):
        """Add a context event for pattern learning"""
        event = {
            "type": event_type,
            "timestamp": datetime.now(),
            "data": data
        }
        self.context_history.append(event)
        
        # Keep history limited
        if len(self.context_history) > 1000:
            self.context_history = self.context_history[-500:]
            
    def accept_suggestion(self, suggestion_id: str) -> Optional[Dict[str, Any]]:
        """Accept a suggestion and return its action data"""
        if suggestion_id in self.suggestions:
            suggestion = self.suggestions[suggestion_id]
            # Remove the suggestion as it's been acted upon
            del self.suggestions[suggestion_id]
            logger.info(f"Suggestion accepted: {suggestion.title}")
            return {
                "action_text": suggestion.action_text,
                "action_data": suggestion.action_data,
                "suggestion_type": suggestion.type.value,
                "title": suggestion.title
            }
        return None
        
    def dismiss_suggestion(self, suggestion_id: str):
        """Dismiss a suggestion"""
        if suggestion_id in self.suggestions:
            del self.suggestions[suggestion_id]
            logger.info(f"Suggestion dismissed: {self.suggestions[suggestion_id].title if suggestion_id in self.suggestions else 'Unknown'}")

# Global instance
proactive_assistant = ProactiveAssistant()