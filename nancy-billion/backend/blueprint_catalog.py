"""Automation blueprints -- parameterized, pre-built cron job templates, so
"remind me every morning" doesn't require the user to hand-write a cron
expression and a prompt from scratch. Ported from Hermes's real
cron/blueprint_catalog.py design (one slot schema drives both a form and
the actual job spec, no second schema) and adapted to Nancy's own cron
shape: a filled blueprint becomes a real `agent_task` job routed through
the "dispatcher" agent (agent_service.py) with task_type="query", so the
prompt gets a genuine, synthesized answer each run -- not a canned string.

Nancy has one real delivery channel (Telegram, already wired into
_cron_execution_loop's agent_task handling), so the deliver/multi-channel
concept from Hermes's version -- which targets several gateway platforms --
isn't ported; every blueprint job just gets Telegram-notified on run like
any other agent_task cron job already is.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "BlueprintSlot", "AutomationBlueprint", "CATALOG", "get_blueprint",
    "blueprint_form_schema", "blueprint_catalog_entry", "fill_blueprint",
    "BlueprintFillError", "WEEKDAY_PRESETS",
]


class BlueprintFillError(ValueError):
    """Raised when supplied slot values fail validation."""


_SLOT_TYPES = frozenset({"time", "enum", "text", "weekdays"})

WEEKDAY_PRESETS: Dict[str, str] = {
    "everyday": "*",
    "weekdays": "1-5",
    "weekends": "0,6",
}


@dataclass(frozen=True)
class BlueprintSlot:
    name: str
    type: str
    label: str
    default: Any = None
    options: tuple = ()
    optional: bool = False
    help: str = ""

    def __post_init__(self) -> None:
        if self.type not in _SLOT_TYPES:
            raise ValueError(f"unknown slot type {self.type!r} (slot {self.name})")


@dataclass(frozen=True)
class AutomationBlueprint:
    key: str
    title: str
    description: str
    category: str
    # Cron expression with {slot} placeholders (e.g. "{minute} {hour} * * {dow}").
    schedule_template: str
    # Dual meaning based on action_type (still one schema, no second one --
    # matching this module's own design principle above): for the default
    # "agent_task", this is the seed prompt for the dispatcher agent (may
    # reference {slot}s). For "run_script", it's the script filename under
    # backend/scripts/ to run via run_script_tool.py instead -- a real,
    # deterministic action with no LLM call involved.
    prompt_template: str
    slots: List[BlueprintSlot] = field(default_factory=list)
    tags: tuple = ()
    action_type: str = "agent_task"


_TIME = lambda default="08:00": BlueprintSlot(  # noqa: E731
    name="time", type="time", label="What time?", default=default,
    help="24h local time, e.g. 08:00",
)


CATALOG: List[AutomationBlueprint] = [
    AutomationBlueprint(
        key="morning-brief", title="Morning briefing", category="daily",
        description="A short daily briefing: today's plan, the markets you watch, and anything urgent.",
        schedule_template="{minute} {hour} * * *",
        prompt_template=(
            "Produce a concise morning briefing for Sir: any urgent items, and a quick read on the pairs "
            "he actually watches (from real trading data, never invented). Keep it short and scannable."
        ),
        slots=[_TIME("08:00")],
        tags=("daily", "briefing"),
    ),
    AutomationBlueprint(
        key="weekly-review", title="Weekly review", category="weekly",
        description="A weekly recap: what got done, what's still open, and what's coming up.",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Produce a weekly review for Sir: real recent trades/performance, agent fleet activity, and "
            "anything still open. Pull from real backend data, keep it tight."
        ),
        slots=[
            _TIME("18:00"),
            BlueprintSlot(name="day", type="enum", label="Which day?", default="sunday",
                          options=("sunday", "monday", "friday", "saturday")),
        ],
        tags=("weekly", "review"),
    ),
    AutomationBlueprint(
        key="workday-start", title="Workday start reminder", category="daily",
        description="A weekday nudge with the day's real priorities.",
        schedule_template="{minute} {hour} * * 1-5",
        prompt_template=(
            "Give Sir a brief weekday start-of-day nudge: today's real system status and the 1-3 "
            "highest-priority things worth his attention right now. Short, one message."
        ),
        slots=[_TIME("09:00")],
        tags=("daily", "focus"),
    ),
    AutomationBlueprint(
        key="custom-reminder", title="Custom reminder", category="general",
        description="A recurring reminder in your own words, on your schedule.",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template="Remind Sir: {what}",
        slots=[
            BlueprintSlot(name="what", type="text", label="Remind me to…", default="take a break and stretch"),
            _TIME("14:00"),
            BlueprintSlot(name="recurrence", type="weekdays", label="Repeat on", default="everyday",
                          options=tuple(WEEKDAY_PRESETS.keys())),
        ],
        tags=("reminder",),
    ),
    AutomationBlueprint(
        key="evening-winddown", title="Evening wind-down", category="daily",
        description="An end-of-day check-in and a calm sign-off.",
        schedule_template="{minute} {hour} * * *",
        prompt_template=(
            "Give Sir a short evening wind-down: a one-line recap of today's real activity and a calm "
            "sign-off. Keep it brief -- one message."
        ),
        slots=[_TIME("21:00")],
        tags=("daily", "evening"),
    ),
    AutomationBlueprint(
        key="news-digest", title="Topic news digest", category="general",
        description="A recurring digest on a topic you care about via a real web search.",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Use the fetch_url tool / web-browsing skill to find new and noteworthy items about: {topic}. "
            "Deliver a tight digest of at most {count} bullets, each one line. If nothing genuinely new, "
            "say so plainly rather than repeating old items."
        ),
        slots=[
            BlueprintSlot(name="topic", type="text", label="What topic?", default="AI and technology"),
            _TIME("18:00"),
            BlueprintSlot(name="recurrence", type="weekdays", label="Repeat on", default="weekdays",
                          options=tuple(WEEKDAY_PRESETS.keys())),
            BlueprintSlot(name="count", type="enum", label="How many bullets?", default="5", options=("3", "5", "8")),
        ],
        tags=("digest", "research"),
    ),
    AutomationBlueprint(
        key="bill-renewal-watch", title="Bills & renewals reminder", category="general",
        description="A heads-up before a recurring payment or renewal.",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Remind Sir about an upcoming payment or renewal: {what}. Phrase it as an actionable "
            "heads-up, not just a notification. One short message."
        ),
        slots=[
            BlueprintSlot(name="what", type="text", label="What's due?", default="a subscription renews soon"),
            _TIME("10:00"),
            BlueprintSlot(name="recurrence", type="weekdays", label="Repeat on", default="everyday",
                          options=tuple(WEEKDAY_PRESETS.keys())),
        ],
        tags=("reminder", "finance"),
    ),
    AutomationBlueprint(
        key="habit-checkin", title="Habit check-in", category="general",
        description="A recurring nudge to keep a habit on track.",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Nudge Sir about his habit: {habit}. Ask whether he did it today, keep it warm and "
            "non-judgmental, one short message."
        ),
        slots=[
            BlueprintSlot(name="habit", type="text", label="Which habit?", default="20 minutes of reading"),
            _TIME("20:00"),
            BlueprintSlot(name="recurrence", type="weekdays", label="Repeat on", default="everyday",
                          options=tuple(WEEKDAY_PRESETS.keys())),
        ],
        tags=("habit", "wellbeing"),
    ),
    AutomationBlueprint(
        key="hydration-move", title="Hydration & movement nudge", category="general",
        description="A periodic nudge during the day to drink water and move.",
        # Cron minute-field steps (*/90) wrap per hour -- an hour-field step is
        # used instead so the chosen cadence is what actually fires.
        schedule_template="0 {start_hour}-{end_hour}/{interval_hours} * * 1-5",
        prompt_template=(
            "Send Sir a brief, friendly nudge to drink some water, stand up, and stretch. Vary the "
            "wording each time. One short line."
        ),
        slots=[
            BlueprintSlot(name="interval_hours", type="enum", label="How often?", default="1", options=("1", "2", "3"),
                          help="hours between nudges"),
            BlueprintSlot(name="start_hour", type="enum", label="Start hour", default="9", options=("7", "8", "9", "10")),
            BlueprintSlot(name="end_hour", type="enum", label="End hour", default="17", options=("16", "17", "18", "19")),
        ],
        tags=("wellbeing", "focus"),
    ),
    AutomationBlueprint(
        key="learn-daily", title="Daily learning drip", category="daily",
        description="One bite-sized lesson a day on a topic you want to learn.",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Teach Sir one bite-sized lesson about: {topic}. Keep it to a couple of short paragraphs "
            "with one concrete example, and end with a single question to check understanding."
        ),
        slots=[
            BlueprintSlot(name="topic", type="text", label="Learn about…", default="a topic of your choice"),
            _TIME("08:30"),
            BlueprintSlot(name="recurrence", type="weekdays", label="Repeat on", default="weekdays",
                          options=tuple(WEEKDAY_PRESETS.keys())),
        ],
        tags=("learning", "daily"),
    ),
    AutomationBlueprint(
        key="gratitude-journal", title="Gratitude & reflection prompt", category="general",
        description="A gentle evening prompt to reflect on the day.",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Send Sir a short, warm reflection prompt for the end of the day -- invite him to note one "
            "thing that went well and one small win. One message."
        ),
        slots=[
            _TIME("21:30"),
            BlueprintSlot(name="recurrence", type="weekdays", label="Repeat on", default="everyday",
                          options=tuple(WEEKDAY_PRESETS.keys())),
        ],
        tags=("wellbeing", "reflection"),
    ),
    AutomationBlueprint(
        key="on-this-day", title="On-this-day discovery", category="daily",
        description="A daily dose of curiosity.",
        schedule_template="{minute} {hour} * * *",
        prompt_template=(
            "Give Sir one interesting '{flavor}' item for today -- short, surprising, genuinely "
            "interesting. One or two sentences, no filler."
        ),
        slots=[
            BlueprintSlot(name="flavor", type="enum", label="What kind?", default="on this day in history",
                          options=("on this day in history", "word of the day", "science fact", "quote of the day")),
            _TIME("07:30"),
        ],
        tags=("daily", "curiosity"),
    ),
    AutomationBlueprint(
        key="disk-cleanup", title="Ephemeral file cleanup", category="maintenance",
        description="Deletes Nancy's own old throwaway files (backups/scratch output) on a schedule -- a real deterministic script, no LLM call.",
        schedule_template="{minute} {hour} * * *",
        prompt_template="disk_cleanup.py",
        action_type="run_script",
        slots=[_TIME("03:00")],
        tags=("maintenance", "cleanup"),
    ),
    AutomationBlueprint(
        key="memory-dreaming", title="Memory consolidation cycle", category="maintenance",
        description="Deduplicates near-identical memories and promotes recurring conversation themes into insights (see memory/dreaming.py).",
        schedule_template="{minute} {hour} * * *",
        prompt_template="",
        action_type="memory_consolidate",
        slots=[_TIME("04:00")],
        tags=("maintenance", "memory"),
    ),
    AutomationBlueprint(
        key="commitment-checkin", title="Open commitments check-in", category="general",
        description="A daily reminder of anything you (or Nancy) committed to that's still open (see memory/commitments.py).",
        schedule_template="{minute} {hour} * * *",
        prompt_template="",
        action_type="commitment_checkin",
        slots=[_TIME("19:00")],
        tags=("reminder", "commitments"),
    ),
]

_CATALOG_BY_KEY = {b.key: b for b in CATALOG}


def get_blueprint(key: str) -> Optional[AutomationBlueprint]:
    return _CATALOG_BY_KEY.get(key)


def blueprint_form_schema(blueprint: AutomationBlueprint) -> Dict[str, Any]:
    return {
        "key": blueprint.key,
        "title": blueprint.title,
        "description": blueprint.description,
        "category": blueprint.category,
        "tags": list(blueprint.tags),
        "fields": [
            {"name": s.name, "type": s.type, "label": s.label, "default": s.default,
             "options": list(s.options), "optional": s.optional, "help": s.help}
            for s in blueprint.slots
        ],
    }


def _humanize_schedule(blueprint: AutomationBlueprint) -> str:
    sched = blueprint.schedule_template
    if "{interval_hours}" in sched:
        iv = next((s for s in blueprint.slots if s.name == "interval_hours"), None)
        every = str((iv.default if iv else None) or "1")
        return "weekdays, every hour" if every == "1" else f"weekdays, every {every} hours"
    time_slot = next((s for s in blueprint.slots if s.type == "time"), None)
    when = time_slot.default if time_slot else None
    if sched.endswith("* * 1-5"):
        return f"weekdays at {when}" if when else "every weekday"
    if "{dow}" in sched:
        day_slot = next((s for s in blueprint.slots if s.name in ("day", "recurrence")), None)
        scope = (day_slot.default if day_slot else "") or ""
        return f"{scope} at {when}" if scope and when else (f"at {when}" if when else "on a schedule")
    return f"daily at {when}" if when else "on a schedule"


def blueprint_catalog_entry(blueprint: AutomationBlueprint) -> Dict[str, Any]:
    return {**blueprint_form_schema(blueprint), "schedule": blueprint.schedule_template,
            "scheduleHuman": _humanize_schedule(blueprint)}


_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DAY_TO_DOW = {"sunday": "0", "monday": "1", "tuesday": "2", "wednesday": "3", "thursday": "4", "friday": "5", "saturday": "6"}


def _resolve_schedule(blueprint: AutomationBlueprint, values: Dict[str, Any]) -> str:
    sched = blueprint.schedule_template
    repl: Dict[str, str] = {}

    if "{minute}" in sched or "{hour}" in sched:
        time_val = values.get("time")
        if not time_val:
            raise BlueprintFillError("a time is required")
        m = _TIME_RE.match(str(time_val).strip())
        if not m:
            raise BlueprintFillError(f"invalid time {time_val!r} — use HH:MM (24h)")
        repl["hour"] = str(int(m.group(1)))
        repl["minute"] = str(int(m.group(2)))

    if "{dow}" in sched:
        if "recurrence" in values:
            preset = str(values.get("recurrence", "everyday")).lower()
            if preset not in WEEKDAY_PRESETS:
                raise BlueprintFillError(f"unknown recurrence {preset!r} — one of {', '.join(WEEKDAY_PRESETS)}")
            repl["dow"] = WEEKDAY_PRESETS[preset]
        elif "day" in values:
            day = str(values.get("day", "")).lower()
            if day not in _DAY_TO_DOW:
                raise BlueprintFillError(f"unknown day {day!r}")
            repl["dow"] = _DAY_TO_DOW[day]
        else:
            repl["dow"] = "*"

    for name in re.findall(r"\{(\w+)\}", sched):
        if name not in repl and name in values:
            repl[name] = str(values[name])

    try:
        return sched.format(**repl)
    except KeyError as e:
        raise BlueprintFillError(f"schedule template missing value for {e}") from e


def fill_blueprint(blueprint: AutomationBlueprint, values: Dict[str, Any]) -> Dict[str, Any]:
    """Validates `values` and returns real cron_store.create() kwargs
    (name, cron_expression, action_type="agent_task" routed through the
    dispatcher agent). Missing required slots / unknown slot names /
    invalid enum values all raise BlueprintFillError naming the problem."""
    known = {s.name for s in blueprint.slots}
    unknown = sorted(set(values) - known)
    if unknown:
        raise BlueprintFillError(f"unknown slot(s): {', '.join(unknown)} — valid: {', '.join(known)}")

    resolved: Dict[str, Any] = {}
    for s in blueprint.slots:
        raw = values.get(s.name, s.default)
        if raw in (None, ""):
            if s.optional:
                continue
            raise BlueprintFillError(f"missing required value: {s.name} ({s.label})")
        if s.type == "enum" and s.options and str(raw) not in {str(o) for o in s.options}:
            raise BlueprintFillError(f"{s.name}={raw!r} not allowed — one of {', '.join(map(str, s.options))}")
        resolved[s.name] = raw

    schedule = _resolve_schedule(blueprint, resolved)

    if blueprint.action_type == "run_script":
        return {
            "name": blueprint.title,
            "description": blueprint.description,
            "cron_expression": schedule,
            "action_type": "run_script",
            "action_payload": {"script": blueprint.prompt_template, "no_agent": True},
        }

    if blueprint.action_type in ("memory_consolidate", "commitment_checkin"):
        return {
            "name": blueprint.title,
            "description": blueprint.description,
            "cron_expression": schedule,
            "action_type": blueprint.action_type,
            "action_payload": {},
        }

    try:
        prompt = blueprint.prompt_template.format(**resolved)
    except KeyError as e:
        raise BlueprintFillError(f"blueprint prompt missing value for {e}") from e

    return {
        "name": blueprint.title,
        "description": blueprint.description,
        "cron_expression": schedule,
        "action_type": "agent_task",
        "action_payload": {"agent_key": "dispatcher", "task_type": "query", "payload": {"query": prompt}},
    }
