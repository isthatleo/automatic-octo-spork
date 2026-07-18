"""
Nancy Intelligent Personalized Greeting System

Nancy doesn't give generic greetings like "Good morning, the weather is 21 degrees."

Nancy knows YOU - your projects, trades, meetings, systems.

She greets you with CONTEXT about what matters to you.

Example:
  "Morning. You have two meetings today, your overnight Docker build finished
   successfully, EUR/USD is approaching the level you've been watching, and
   Roxan's latest deployment completed without errors."
"""

import logging
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PersonalContext:
    """User's personal context for intelligent greetings"""
    meetings_today: List[str] = field(default_factory=list)
    build_status: Optional[str] = None  # "completed", "running", "failed"
    market_alerts: List[str] = field(default_factory=list)  # "EUR/USD approaching 1.0850"
    project_updates: List[str] = field(default_factory=list)  # "Roxan deployment successful"
    active_trades: List[str] = field(default_factory=list)
    tasks_due: List[str] = field(default_factory=list)
    # Real live agent-fleet status (see main_new.py's _build_real_personal_context),
    # already phrased as a full clause -- always present once the agent service
    # is ready, so the greeting never has to fall back to a single bare word
    # just because there are no meetings/trades/projects to report yet.
    system_status: Optional[str] = None


class ContextualGreetingEngine:
    """
    Generates intelligent, personalized greetings based on user context.

    Nancy pulls from:
    - Calendar/meetings
    - Build/deployment status
    - Market alerts (forex, crypto, stocks)
    - Project updates
    - Active trades
    - Task list

    And weaves them into a natural, conversational greeting.
    """

    def __init__(self, persona: str = "nancy"):
        self.persona = persona.lower()

    async def generate_personalized_greeting(self, context: PersonalContext) -> str:
        """
        Generate intelligent, personalized greeting.

        Returns greeting like:
        "Morning. You have two meetings today, your overnight Docker build finished
         successfully, EUR/USD is approaching the level you've been watching, and
         Roxan's latest deployment completed without errors."
        """

        greeting_parts = []

        # Time of day greeting
        time_greeting = self._get_time_greeting()

        # Extract priority context items
        context_items = self._extract_context_items(context)

        # Build natural greeting
        if not context_items:
            # Fallback if no context (e.g. agent service still initialising)
            return f"{time_greeting}. Systems are still coming online -- give me just a moment."

        # Combine greeting naturally
        return self._combine_greeting(time_greeting, context_items)

    def _get_time_greeting(self) -> str:
        """Get a full time-appropriate opening address, always as 'sir' --
        a proper JARVIS-style opening line, not a single clipped word."""
        hour = datetime.now().hour

        if hour < 5:
            greeting = "Good evening, Sir — burning the midnight oil, I see"
        elif hour < 12:
            greeting = "Good morning, Sir"
        elif hour < 17:
            greeting = "Good afternoon, Sir"
        elif hour < 21:
            greeting = "Good evening, Sir"
        else:
            greeting = "Good evening, Sir — it's rather late"

        # Persona flavor, layered onto the address rather than replacing it.
        if self.persona == "billion":
            if hour < 12:
                greeting += "; the markets open shortly"
            elif hour < 17:
                greeting += "; the session's got some momentum"

        return greeting

    def _extract_context_items(self, context: PersonalContext) -> List[str]:
        """
        Extract priority context items for greeting.
        Orders by importance: system status → meetings → builds → projects → trades → tasks
        """
        items = []

        # 0. SYSTEM STATUS (real live agent-fleet data -- always available once
        # the agent service is ready, so the greeting has real substance even
        # on a fresh session with no meetings/trades/projects recorded yet)
        if context.system_status:
            items.append(context.system_status)

        # 1. MEETINGS (Usually highest priority)
        if context.meetings_today:
            count = len(context.meetings_today)
            items.append(f"you have {count} meeting{'s' if count > 1 else ''} today")
            # Optionally add first meeting time
            if len(context.meetings_today) > 0:
                items[-1] += f": {context.meetings_today[0]}"

        # 2. BUILD STATUS (Critical - overnight builds)
        if context.build_status == "completed":
            items.append("your overnight Docker build finished successfully")
        elif context.build_status == "running":
            items.append("your Docker build is currently running")
        elif context.build_status == "failed":
            items.append("your Docker build encountered errors - check logs")

        # 3. PROJECT UPDATES (Deployments, releases)
        if context.project_updates:
            for update in context.project_updates[:2]:  # Top 2
                items.append(update)

        # 4. MARKET ALERTS (For traders - important if watching specific levels)
        if context.market_alerts:
            for alert in context.market_alerts[:2]:  # Top 2
                items.append(alert)

        # 5. ACTIVE TRADES (Ongoing positions)
        if context.active_trades:
            count = len(context.active_trades)
            items.append(f"you have {count} open trade{'s' if count > 1 else ''}")

        # 6. TASKS DUE (Lower priority, but still important)
        if context.tasks_due:
            count = len(context.tasks_due)
            items.append(f"{count} task{'s' if count > 1 else ''} due today")

        return items

    def _combine_greeting(self, time_greeting: str, items: List[str]) -> str:
        """Combine time greeting with context items into a fuller, warmer
        briefing -- a real paragraph rather than a single clipped clause,
        closing with an invitation so it never just trails off."""

        if len(items) == 1:
            body = f"{items[0]}."
        elif len(items) == 2:
            body = f"{items[0]}, and {items[1]}."
        else:
            # Multiple items: join with commas, last with "and"
            body = ", ".join(items[:-1]) + ", and " + items[-1] + "."

        # Items are phrased to read naturally mid-sentence ("you have 2
        # meetings today"); as the first thing after the time greeting's
        # full stop it needs a capital to read as a proper new sentence.
        if body:
            body = body[0].upper() + body[1:]

        closing = self._closing_line(items)
        return f"{time_greeting}. {body} {closing}"

    def _closing_line(self, items: List[str]) -> str:
        """Pick a closing invitation that reflects whether there's anything
        actually waiting on the user, instead of a single static stock line."""
        joined = " ".join(items).lower()
        if "awaiting your" in joined or "approval" in joined:
            return "Shall we start with what's waiting on you?"
        if "open trade" in joined:
            return "Markets are live whenever you want a closer look."
        return "Everything's yours to command whenever you're ready, Sir."


class IntelligentStartupCoordinator:
    """
    Coordinates Nancy's startup with personalized context.

    Replaces generic startup with intelligent greeting that pulls
    real context about the user's day.
    """

    def __init__(self, persona: str = "nancy"):
        self.persona = persona.lower()
        self.greeting_engine = ContextualGreetingEngine(persona)

    async def startup_with_context(self, context: PersonalContext) -> Dict:
        """
        Startup Nancy with personalized context greeting.

        Returns full startup data including personalized greeting.
        """

        # Generate personalized greeting
        greeting = await self.greeting_engine.generate_personalized_greeting(context)

        logger.info("🎉 NANCY PERSONALIZED STARTUP")
        logger.info(f"  Persona: {self.persona.upper()}")
        logger.info(f"  Greeting: {greeting}")

        return {
            "persona": self.persona,
            "greeting": greeting,
            "context_summary": {
                "meetings": len(context.meetings_today),
                "build_status": context.build_status,
                "market_alerts": len(context.market_alerts),
                "project_updates": len(context.project_updates),
                "active_trades": len(context.active_trades),
                "tasks_due": len(context.tasks_due),
            },
            "timestamp": datetime.now().isoformat(),
            "next_question": "What would you like to focus on first?",
            "quick_actions": self._generate_quick_actions(context)
        }

    def _generate_quick_actions(self, context: PersonalContext) -> List[str]:
        """Generate smart quick actions based on context"""
        actions = []

        if context.meetings_today:
            actions.append(f"📅 {context.meetings_today[0]}")

        if context.project_updates:
            actions.append("📊 Review project updates")

        if context.market_alerts:
            actions.append("📈 Check market alerts")

        if context.active_trades:
            actions.append("💹 Review open trades")

        if not actions:
            actions = ["💬 Chat with me", "📊 Check status", "🎯 Plan your day"]

        return actions


# Example usage
if __name__ == "__main__":
    import asyncio

    async def demo():
        print("=" * 80)
        print("NANCY INTELLIGENT GREETING SYSTEM DEMO")
        print("=" * 80)

        # Create coordinator
        coordinator = IntelligentStartupCoordinator(persona="nancy")

        # Example personalized context
        context = PersonalContext(
            meetings_today=[
                "10am: Team sync",
                "2pm: Product review",
                "4pm: 1-on-1 with manager"
            ],
            build_status="completed",
            market_alerts=[
                "EUR/USD approaching 1.0850 (level you've been watching)",
                "Resistance at 1.0900 broken yesterday"
            ],
            project_updates=[
                "Roxan deployment completed without errors",
                "Database migration successful"
            ],
            active_trades=[
                "EUR/USD LONG @ 1.0825",
                "GBP/USD SHORT @ 1.2740"
            ],
            tasks_due=[
                "Review PR #234",
                "Update documentation",
                "Approve feature release"
            ]
        )

        print("\n📋 CONTEXT:")
        print(f"  ├─ Meetings: {len(context.meetings_today)}")
        print(f"  ├─ Build: {context.build_status}")
        print(f"  ├─ Market alerts: {len(context.market_alerts)}")
        print(f"  ├─ Projects: {len(context.project_updates)}")
        print(f"  ├─ Trades: {len(context.active_trades)}")
        print(f"  └─ Tasks: {len(context.tasks_due)}")

        # Generate greeting
        startup_data = await coordinator.startup_with_context(context)

        print("\n🎤 NANCY'S PERSONALIZED GREETING:")
        print("─" * 80)
        print(f"  {startup_data['greeting']}")
        print("─" * 80)

        print("\n⚡ QUICK ACTIONS:")
        for action in startup_data['quick_actions']:
            print(f"  • {action}")

    asyncio.run(demo())

