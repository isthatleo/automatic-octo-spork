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

import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Real, randomly-picked structural directions for the LLM composition below --
# confirmed live as the actual fix for "every greeting feels scripted": temperature
# alone wasn't enough because the prompt anchored the SAME opening phrase and the
# SAME "weave the facts in" instruction on every call, so the model kept
# reproducing near-identical structure even at temperature=0.9. Picking a real
# structural instruction at random, in code, forces genuine variation in shape
# (what comes first, how long, how it's tied together) rather than just
# word-choice variation within a fixed shape.
_STYLE_DIRECTIONS = [
    "Lead with whichever single fact matters most right now, then fill in the rest.",
    "Open with a brief, warm personal check-in line before getting into the facts.",
    "Keep it tight and efficient -- short sentences, no throat-clearing, straight to what matters.",
    "Tell it a little like a story: what's been happening, then what's coming up.",
    "Group the facts by theme (systems, markets, tasks) rather than listing them in a fixed order.",
    "Start with the most surprising or noteworthy fact, saving routine status for later in the greeting.",
]


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
        Generate intelligent, personalized greeting -- composed fresh by a
        real LLM call from the real facts below, not a fixed template.

        The facts (system status, real market prices for pairs the user
        actually trades, real trades/tasks) come entirely from
        _extract_context_items(), unchanged -- only the *phrasing* is now
        LLM-generated, specifically so it varies turn to turn and doesn't
        read as scripted (confirmed live complaint: the deterministic
        template produced the literal same sentence structure every time).
        Falls back to the deterministic template only if the LLM call
        itself fails, so a greeting is never lost to a backend hiccup.
        """
        time_greeting = self._get_time_greeting()
        context_items = self._extract_context_items(context)

        if not context_items:
            # No real data yet (e.g. agent service still initialising) --
            # nothing to compose from, so don't invent facts.
            return f"{time_greeting}. Systems are still coming online -- give me just a moment."

        try:
            return await self._compose_via_llm(time_greeting, context_items)
        except Exception as e:
            logger.warning("LLM greeting composition failed, using templated fallback: %s", e)
            return self._combine_greeting(time_greeting, context_items)

    async def _compose_via_llm(self, time_greeting: str, facts: List[str]) -> str:
        from llm import llm_backend

        # Real, read-fresh ground truth for THIS call -- confirmed live as the
        # actual cause of the greeting stating a wrong clock time: this prompt
        # previously never contained a real date/time value anywhere, only the
        # vague morning/afternoon/evening bucket below, so the model was free to
        # invent a specific-sounding time as flavor text with nothing to check it
        # against. Same fix as main_new.py's _live_datetime_prompt_block, applied
        # here since this module composes its greeting independently of that
        # chat-turn prompt path.
        now = datetime.now().astimezone()
        real_time_line = (
            f"The REAL current date and time is {now.strftime('%A, %B %d, %Y')} at "
            f"{now.strftime('%I:%M %p').lstrip('0')} ({now.strftime('%Z')}). This is ground "
            "truth. If you mention a specific time or date anywhere in the greeting, it must "
            "match this exactly -- never state a different one, and never invent one for "
            "flavor. If you don't need to state a specific time, don't; the opening tone "
            "below already carries the time-of-day."
        )
        style_direction = random.choice(_STYLE_DIRECTIONS)

        facts_block = "\n".join(f"- {f}" for f in facts)
        prompt = (
            "You are Nancy, a JARVIS-style British AI assistant. Compose ONE short, "
            "warm, natural-sounding greeting for your user using ONLY the real facts "
            "below -- never invent or add anything not listed. Always address the user "
            "as \"Sir\" (capitalized). This is a recurring greeting he hears often, so it "
            "must NOT feel scripted or reuse the same structure every time -- genuinely "
            "vary sentence structure, word choice, opening line, and closing line call to "
            f"call. For THIS greeting specifically: {style_direction}\n\n"
            "The real boundaries for time-of-day (so you can reason about this yourself, "
            "not just take a label on faith): 05:00-11:59 is morning, 12:00-16:59 is "
            "afternoon, 17:00-20:59 is evening, and 21:00-04:59 is late night. Given the "
            f"real current time below, that makes right now: \"{time_greeting}\" -- this "
            "classification is GROUND TRUTH and must never be changed or contradicted; "
            "getting this wrong (e.g. saying \"good morning\" when it is actually evening) "
            "is a hard factual error, not a stylistic choice. You MAY and SHOULD vary the "
            "exact WORDING used to convey it (\"Good evening, Sir\" / \"Evening, Sir\" / "
            "\"Hope the evening's treating you well, Sir\" / etc. are all fine variations of "
            "the SAME real evening) -- vary the phrasing, never the underlying time-of-day "
            "itself.\n\n"
            f"{real_time_line}\n\n"
            # The user asked explicitly for the COMPLETE brief and said he
            # would rather wait than be short-changed. An earlier version
            # capped this to one fact / 25 words purely to cut synthesis
            # time; that traded away the thing he actually wanted, so
            # completeness wins here over time-to-first-word.
            "Address him and set the time-of-day tone in a SHORT opening sentence, then "
            "deliver his COMPLETE brief: every single real fact listed below, none omitted "
            "or summarised away, woven into flowing conversational prose rather than read "
            "out as a flat list. This is his morning/evening briefing -- thoroughness is "
            "the point of it. ALWAYS end on a short closing line that invites him to engage "
            "-- vary it (an offer to help, a question about what to focus on first, a "
            "simple readiness line, a light observation) rather than reusing the same "
            "sign-off -- it should feel complete and rounded off, never trail off after the "
            "last fact with no sign-off.\n\n"
            f"Real facts to weave in:\n{facts_block}\n\n"
            "Write only the greeting itself -- no preamble, no quotation marks, no "
            "explanation of what you're doing."
        )
        # Generous token headroom above what a 2-4 sentence greeting + closing
        # line actually needs -- confirmed live that a tighter cap could
        # truncate the response mid-sentence right before its closing line
        # (the real fix for that turned out to be llm.py's GeminiLLM
        # disabling "thinking" tokens, which were eating the budget before
        # any of it reached visible text -- max_tokens alone wasn't the
        # cause). The WALL-CLOCK timeout here is deliberately tight, though:
        # this fires on every boot for a voice-first product where "how long
        # until I hear her say anything" matters more than word-choice
        # variety, and _combine_greeting's template below is a real,
        # complete, good-sounding greeting on its own -- worth falling back
        # to quickly rather than making the user wait out a slow LLM call.
        text = await asyncio.wait_for(
            llm_backend.generate(prompt, max_tokens=350, temperature=0.9),
            timeout=5.0,
        )
        return text.strip()

    def _get_time_greeting(self) -> str:
        """Get a full time-appropriate opening address, always as 'sir' --
        a proper JARVIS-style opening line, not a single clipped word."""
        hour = datetime.now().hour

        # The BUCKET boundaries here are the real, accurate classification --
        # never touch these to add variety. Only the PHRASING within each
        # bucket is randomized (real Python randomness, not left to the LLM),
        # so even the deterministic template fallback doesn't say the exact
        # same sentence every single time. 00:00-04:59 is the small hours of
        # a *new* day, not "evening" -- confirmed live this used to say "Good
        # evening" at 4am, which reads as flatly wrong rather than informal.
        if hour < 5:
            greeting = random.choice([
                "Still up, Sir — burning the midnight oil, I see",
                "You're still awake, Sir — the small hours suit you, it seems",
                "Late one, Sir",
            ])
        elif hour < 12:
            greeting = random.choice(["Good morning, Sir", "Morning, Sir"])
        elif hour < 17:
            greeting = random.choice(["Good afternoon, Sir", "Afternoon, Sir"])
        elif hour < 21:
            greeting = random.choice(["Good evening, Sir", "Evening, Sir"])
        else:
            greeting = random.choice([
                "Good evening, Sir — it's rather late",
                "Evening, Sir — burning the midnight oil a little early tonight",
            ])

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
        closing with an invitation so it never just trails off.

        Deliberately reports EVERY real item, not a truncated subset: the
        user wants the complete morning brief, and accepts that a longer
        greeting takes proportionally longer to synthesize (see neu_tts.py
        -- roughly 1.7x slower than realtime). Completeness is the explicit
        priority here over time-to-first-word.
        """
        if len(items) == 1:
            body = f"{items[0]}."
        elif len(items) == 2:
            body = f"{items[0]}, and {items[1]}."
        else:
            # Multiple items: join with commas, last with "and"
            body = ", ".join(items[:-1]) + ", and " + items[-1] + "." if items else ""

        # Items are phrased to read naturally mid-sentence ("you have 2
        # meetings today"); as the first thing after the time greeting's
        # full stop it needs a capital to read as a proper new sentence.
        if body:
            body = body[0].upper() + body[1:]

        closing = self._closing_line(items)
        return f"{time_greeting}. {body} {closing}"

    def _closing_line(self, items: List[str]) -> str:
        """Pick a closing invitation that reflects whether there's anything
        actually waiting on the user, with real variety within each case so
        the deterministic fallback doesn't read identically every time it's
        used (see _STYLE_DIRECTIONS' docstring for why sameness was the
        actual complaint, not just the LLM path's phrasing)."""
        joined = " ".join(items).lower()
        if "awaiting your" in joined or "approval" in joined:
            return random.choice([
                "Shall we start with what's waiting on you?",
                "Want to tackle what's pending first, Sir?",
                "That approval's the obvious place to start, whenever you're ready.",
            ])
        if "open trade" in joined:
            return random.choice([
                "Markets are live whenever you want a closer look.",
                "Say the word and I'll pull up the open positions.",
                "The desk's ready whenever you are, Sir.",
            ])
        return random.choice([
            "Everything's yours to command whenever you're ready, Sir.",
            "Ready when you are, Sir.",
            "Just say where you'd like to start.",
            "What would you like to focus on first?",
        ])


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

