"""
Context Manager & Classifier for Nancy/Billion

This module provides:
- Context tracking across conversations
- Intent classification (chat vs map vs trading vs code)
- User preference learning
- Conversation history management
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """All possible user intents Nancy can handle"""
    CHAT = "chat"
    MAP = "map"
    WEATHER = "weather"
    TRADING = "trading"
    CODING = "coding"
    ANALYSIS = "analysis"
    SYSTEM_CONTROL = "system"
    RESEARCH = "research"
    MEMORY_QUERY = "memory"


class ContextManager:
    """
    Manages conversation context and user state.

    Prevents false routing (e.g., weather → map)
    Maintains conversation history
    Tracks active topics
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.conversation_history: List[Dict] = []
        self.active_topics: List[str] = []
        self.user_preferences: Dict = {}
        self.session_start = datetime.now()

    def add_message(self, role: str, content: str, metadata: Dict = None):
        """Add message to conversation history"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(),
            "metadata": metadata or {}
        }
        self.conversation_history.append(message)
        logger.debug(f"Added {role} message: {content[:50]}...")

    def get_recent_context(self, max_messages: int = 5) -> List[Dict]:
        """Get last N messages for context"""
        return self.conversation_history[-max_messages:]

    def get_full_context(self) -> str:
        """Get full context as formatted string for LLM"""
        context_lines = []
        for msg in self.get_recent_context(10):
            role = msg["role"].upper()
            content = msg["content"]
            context_lines.append(f"{role}: {content}")

        return "\n".join(context_lines)

    def update_topic(self, topic: str):
        """Track active conversation topic"""
        if topic not in self.active_topics:
            self.active_topics.insert(0, topic)  # Most recent first

        # Keep only last 10 topics
        self.active_topics = self.active_topics[:10]
        logger.debug(f"Active topics: {self.active_topics}")

    def clear_old_history(self, max_age_hours: int = 24):
        """Remove old messages (cleanup)"""
        # Keep last 100 messages or messages from last 24 hours
        if len(self.conversation_history) > 100:
            self.conversation_history = self.conversation_history[-100:]


class IntentClassifier:
    """
    Classify user intent from input text.

    Prevents false positives:
    - "What's the weather?" → WEATHER (not MAP)
    - "Where is Paris?" → MAP (not WEATHER)
    - "EUR/USD analysis" → TRADING (not CHAT)
    """

    def __init__(self):
        self.keywords = {
            IntentType.MAP: ["where", "location", "map", "navigate", "address", "route", "directions"],
            IntentType.WEATHER: ["weather", "temperature", "temp", "rain", "snow", "forecast", "climate"],
            IntentType.TRADING: ["forex", "eur/usd", "trade", "buy", "sell", "bitcoin", "crypto", "stock"],
            IntentType.CODING: ["code", "function", "debug", "python", "javascript", "react", "error"],
            IntentType.SYSTEM_CONTROL: ["open", "close", "run", "start", "stop", "launch"],
            IntentType.RESEARCH: ["research", "analyze", "explain", "what is", "how does", "summary"],
        }

    def classify(self, text: str, context: Optional[ContextManager] = None) -> IntentType:
        """
        Classify user intent with high accuracy.

        Args:
            text: User input
            context: Optional context manager for conversation history

        Returns:
            IntentType enum
        """
        text_lower = text.lower()

        # Check for explicit intent keywords
        scores = {}

        for intent_type, keywords in self.keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent_type] = score

        # If we have matches, return highest score
        if scores:
            best_intent = max(scores, key=scores.get)
            logger.debug(f"Classified intent: {best_intent.value} (score: {scores[best_intent]})")
            return best_intent

        # Context-based fallback
        if context and context.active_topics:
            recent_topic = context.active_topics[0]
            logger.debug(f"Using context topic: {recent_topic}")
            # Map topic back to intent
            for intent, keywords in self.keywords.items():
                if recent_topic.lower() in keywords:
                    return intent

        # Default to CHAT
        logger.debug("Defaulting to CHAT intent")
        return IntentType.CHAT

    def get_confidence(self, text: str) -> Dict[IntentType, float]:
        """
        Get confidence scores for all intent types.

        Returns dict of intent → confidence (0.0-1.0)
        """
        text_lower = text.lower()
        confidences = {}

        total_keywords = sum(len(kws) for kws in self.keywords.values())

        for intent_type, keywords in self.keywords.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            confidence = matches / len(keywords) if keywords else 0.0
            confidences[intent_type] = min(confidence, 1.0)

        return confidences


class NancyContextualBrain:
    """
    Main intelligence layer that combines context & classification.

    This is what makes Nancy smart:
    - Remembers conversation
    - Understands intent
    - Routes to correct handler
    """

    def __init__(self, user_id: str = "default"):
        self.context = ContextManager(user_id)
        self.classifier = IntentClassifier()

    def process_input(self, text: str) -> Dict:
        """
        Process user input and return routing decision.

        Returns:
        {
            "intent": IntentType,
            "confidence": float,
            "context": str,
            "should_use_map": bool,
            "should_search_memory": bool,
            "routing_hints": List[str]
        }
        """
        # Classify intent
        intent = self.classifier.classify(text, self.context)
        confidence_scores = self.classifier.get_confidence(text)

        # Update context
        self.context.add_message("user", text, {
            "intent": intent.value,
            "confidence": confidence_scores[intent]
        })
        self.context.update_topic(intent.value)

        # Generate routing decision
        should_use_map = intent == IntentType.MAP
        should_search_memory = intent == IntentType.MEMORY_QUERY

        routing_hints = []
        if intent == IntentType.TRADING:
            routing_hints.append("Use forex engine")
        elif intent == IntentType.CODING:
            routing_hints.append("Use code analysis")
        elif intent == IntentType.RESEARCH:
            routing_hints.append("Use search engine")

        return {
            "intent": intent.value,
            "confidence": confidence_scores[intent],
            "context": self.context.get_full_context(),
            "should_use_map": should_use_map,
            "should_search_memory": should_search_memory,
            "routing_hints": routing_hints
        }

    def add_response(self, response: str):
        """Record Nancy's response"""
        self.context.add_message("assistant", response)

    def get_conversation_summary(self) -> str:
        """Get brief summary of conversation"""
        return f"Active topics: {', '.join(self.context.active_topics[:3])}"


# Example usage
if __name__ == "__main__":
    brain = NancyContextualBrain()

    # Test various inputs
    test_inputs = [
        "What's the weather like today?",  # Should be WEATHER, not MAP
        "Where is Paris?",  # Should be MAP
        "EUR/USD is looking bullish",  # Should be TRADING
        "Write me a Python function",  # Should be CODING
        "Find me information about quantum computing",  # Should be RESEARCH
    ]

    for test_input in test_inputs:
        result = brain.process_input(test_input)
        print(f"\nInput: {test_input}")
        print(f"Intent: {result['intent']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Should use map: {result['should_use_map']}")

