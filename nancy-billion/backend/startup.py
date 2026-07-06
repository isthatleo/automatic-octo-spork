"""
Nancy Startup & Greeting System

Handles:
- Initial boot greeting
- Personality selection
- Status messages
- Welcome flows
"""

import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class NancyGreeting:
    """
    Nancy's personality-driven greeting system.

    Nancy has multiple personas:
    - Nancy: Professional, helpful
    - Billion: Ambitious, growth-focused
    - Jarvis: Formal, commanding
    """

    GREETINGS = {
        "nancy": {
            "boot": "✨ Nancy initializing... All systems coming online.",
            "ready": "Hello! I'm Nancy. Ready to assist with whatever you need. What's on your mind?",
            "accent": "friendly, capable, always helpful"
        },
        "billion": {
            "boot": "💰 Billion OS booting... Systems optimizing for maximum efficiency.",
            "ready": "Billion here. Let's build something extraordinary. What's our next move?",
            "accent": "ambitious, driven, growth-oriented"
        },
        "jarvis": {
            "boot": "🎩 Jarvis protocol activating... Neural networks synchronizing.",
            "ready": "Jarvis at your service, sir. How may I be of assistance?",
            "accent": "formal, precise, commanding"
        }
    }

    def __init__(self, persona: str = "nancy"):
        """Initialize with persona"""
        self.persona = persona.lower()
        if self.persona not in self.GREETINGS:
            self.persona = "nancy"

        self.greeting = self.GREETINGS[self.persona]

    def get_boot_message(self) -> str:
        """Get boot sequence message"""
        return self.greeting["boot"]

    def get_ready_message(self) -> str:
        """Get ready/online message"""
        return self.greeting["ready"]

    def get_startup_sequence(self) -> Dict:
        """Get full startup sequence with timing"""
        return {
            "stage_1": {
                "duration_ms": 1200,
                "message": self.get_boot_message(),
                "action": "Systems coming online"
            },
            "stage_2": {
                "duration_ms": 1200,
                "message": "🧠 Loading memory... Past conversations and insights retrieved.",
                "action": "Memory loaded"
            },
            "stage_3": {
                "duration_ms": 1200,
                "message": "🔗 Building context... Understanding your environment.",
                "action": "Context established"
            },
            "stage_4": {
                "duration_ms": 800,
                "message": self.get_ready_message(),
                "action": "Ready"
            }
        }

    def get_context_aware_greeting(self, time_of_day: Optional[str] = None, last_seen: Optional[str] = None) -> str:
        """
        Get context-aware greeting based on time and history.

        Args:
            time_of_day: "morning", "afternoon", "evening", "night"
            last_seen: When user was last active
        """
        hour = datetime.now().hour

        if time_of_day is None:
            if hour < 12:
                time_of_day = "morning"
            elif hour < 17:
                time_of_day = "afternoon"
            elif hour < 21:
                time_of_day = "evening"
            else:
                time_of_day = "night"

        # Persona-specific time-aware greetings
        if self.persona == "nancy":
            if time_of_day == "morning":
                return "Good morning! Refreshed and ready to go. What's first on your agenda?"
            elif time_of_day == "afternoon":
                return "Good afternoon! How's your day going? Need any help?"
            elif time_of_day == "evening":
                return "Good evening! Perfect time to reflect and plan. What can I help with?"
            else:
                return "Burning the midnight oil? I'm here to help. What do you need?"

        elif self.persona == "billion":
            if time_of_day == "morning":
                return "Morning! The market's waking up. Let's identify opportunities."
            elif time_of_day == "afternoon":
                return "Afternoon momentum's building. Time to execute?"
            elif time_of_day == "evening":
                return "Evening analysis time. Let's review what we've learned today."
            else:
                return "Late night grind. That's when the best deals happen. What's the play?"

        else:  # jarvis
            if time_of_day == "morning":
                return "Good morning, sir. Your briefing is ready."
            elif time_of_day == "afternoon":
                return "The afternoon update awaits, sir."
            elif time_of_day == "evening":
                return "Evening, sir. Your situation report is prepared."
            else:
                return "Burning midnight oil, sir? Quite industrious."

    def get_memory_recall_message(self) -> str:
        """Get message when Nancy recalls recent memories"""
        if self.persona == "nancy":
            return "I remember we were working on something interesting. Shall we continue?"
        elif self.persona == "billion":
            return "I've been analyzing our previous session. Ready to capitalize?"
        else:
            return "Your previous session is recalled, sir. Shall we resume?"

    def get_error_message(self) -> str:
        """Get personality-specific error message"""
        if self.persona == "nancy":
            return "Hmm, I hit a snag. Give me a moment to recover."
        elif self.persona == "billion":
            return "Unexpected obstacle. Recalibrating approach..."
        else:
            return "A minor setback, sir. Recalibrating systems."

    def get_offline_message(self) -> str:
        """Get message when going offline"""
        if self.persona == "nancy":
            return "Thanks for today. I'll remember everything. See you next time!"
        elif self.persona == "billion":
            return "Great work today. Tomorrow we scale. Until then!"
        else:
            return "I shall await your return, sir. Safe travels."


class StartupCoordinator:
    """
    Coordinates Nancy's startup sequence.

    Manages:
    - Persona selection
    - Boot sequence
    - Initial state
    - First interaction setup
    """

    def __init__(self):
        self.persona = "nancy"
        self.greeting = NancyGreeting(self.persona)
        self.is_first_boot = True

    def set_persona(self, persona: str):
        """Change Nancy's persona"""
        self.persona = persona.lower()
        self.greeting = NancyGreeting(self.persona)
        logger.info(f"Persona set to: {self.persona}")

    def start_up(self) -> Dict:
        """Execute full startup sequence"""
        logger.info("Nancy starting up...")

        sequence = self.greeting.get_startup_sequence()

        return {
            "startup_sequence": sequence,
            "persona": self.persona,
            "is_first_boot": self.is_first_boot,
            "timestamp": datetime.now().isoformat()
        }

    def first_run_setup(self) -> Dict:
        """Setup for first-time users"""
        return {
            "greeting": self.greeting.get_ready_message(),
            "offer_personas": True,
            "personas": ["nancy", "billion", "jarvis"],
            "suggestions": [
                "Ask me about your projects",
                "Check your trading status",
                "Try a voice command"
            ]
        }

    def returning_user_setup(self) -> Dict:
        """Setup for returning users"""
        return {
            "greeting": self.greeting.get_memory_recall_message(),
            "show_recent_context": True,
            "quick_actions": [
                "Continue project work",
                "Check market analysis",
                "Review yesterday's summary"
            ]
        }


# Example usage
if __name__ == "__main__":
    # Initialize Nancy
    coordinator = StartupCoordinator()

    # Start up
    startup_data = coordinator.start_up()
    print("STARTUP SEQUENCE:")
    for stage, data in startup_data["startup_sequence"].items():
        print(f"\n{stage}:")
        print(f"  Message: {data['message']}")
        print(f"  Duration: {data['duration_ms']}ms")

    # Time-aware greeting
    greeting = coordinator.greeting
    print(f"\n\nCONTEXT-AWARE GREETING:")
    print(f"  {greeting.get_context_aware_greeting()}")

    # Test different personas
    print("\n\nDIFFERENT PERSONAS:")
    for persona in ["nancy", "billion", "jarvis"]:
        coordinator.set_persona(persona)
        print(f"\n{persona.upper()}:")
        print(f"  Boot: {coordinator.greeting.get_boot_message()}")
        print(f"  Ready: {coordinator.greeting.get_ready_message()}")

