"""Real gamified achievements -- ported from Hermes' Hermes-Achievements
plugin. Badges are computed from real, already-persisted activity (agent
task history via agent_service.py's stats, real terminal/file executions
via evidence_ledger.py, real skill usage via skill_loader.py's usage store)
-- nothing here is a fake counter incremented for its own sake; every badge
reflects something that genuinely already happened.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_UNLOCKS_PATH = os.path.join(os.path.dirname(__file__), "data", "achievement_unlocks.json")


@dataclass(frozen=True)
class Achievement:
    key: str
    title: str
    description: str
    tier: str  # copper, bronze, silver, gold, olympian
    check: Callable[[Dict[str, Any]], bool]
    stat_key: Optional[str] = None  # activity dict key this badge tracks, for a real progress bar
    target: Optional[int] = None  # threshold on stat_key; None + stat_key set means "dynamic" (see _dynamic_target)


def _stat(activity: Dict[str, Any], key: str, default: int = 0) -> int:
    return int(activity.get(key, default) or 0)


def _dynamic_target(key: str, activity: Dict[str, Any]) -> Optional[int]:
    """A handful of badges don't have a fixed target -- skill_master's goal
    is "every skill", which moves as skills are added/removed."""
    if key == "skill_master":
        return _stat(activity, "total_skills")
    return None


ACHIEVEMENTS: List[Achievement] = [
    Achievement("first_task", "First Steps", "Ran your first agent task.", "copper",
                lambda a: _stat(a, "total_tasks") >= 1, "total_tasks", 1),
    Achievement("ten_tasks", "Getting Going", "Ran 10 agent tasks.", "bronze",
                lambda a: _stat(a, "total_tasks") >= 10, "total_tasks", 10),
    Achievement("hundred_tasks", "Fleet Commander", "Ran 100 agent tasks.", "silver",
                lambda a: _stat(a, "total_tasks") >= 100, "total_tasks", 100),
    Achievement("thousand_tasks", "Automation Olympian", "Ran 1,000 agent tasks.", "olympian",
                lambda a: _stat(a, "total_tasks") >= 1000, "total_tasks", 1000),
    Achievement("perfect_streak", "Flawless", "100% success rate over at least 20 tasks.", "gold",
                lambda a: _stat(a, "total_tasks") >= 20 and _stat(a, "failed_tasks") == 0),
    Achievement("first_command", "Hands on the Wheel", "Ran your first real terminal command.", "copper",
                lambda a: _stat(a, "terminal_commands") >= 1, "terminal_commands", 1),
    Achievement("fifty_commands", "Power User", "Ran 50 real terminal commands.", "bronze",
                lambda a: _stat(a, "terminal_commands") >= 50, "terminal_commands", 50),
    Achievement("first_file_write", "Builder", "Wrote your first real file.", "copper",
                lambda a: _stat(a, "file_writes") >= 1, "file_writes", 1),
    Achievement("skill_explorer", "Skill Explorer", "Used 5 different skills.", "bronze",
                lambda a: _stat(a, "distinct_skills_used") >= 5, "distinct_skills_used", 5),
    Achievement("skill_master", "Skill Master", "Used every skill in the library at least once.", "gold",
                lambda a: _stat(a, "distinct_skills_used") > 0 and _stat(a, "distinct_skills_used") >= _stat(a, "total_skills"),
                "distinct_skills_used", None),
    Achievement("memory_keeper", "Memory Keeper", "Stored 50 real memories.", "bronze",
                lambda a: _stat(a, "total_memories") >= 50, "total_memories", 50),
    Achievement("wiki_contributor", "Wiki Contributor", "Created your first memory wiki page.", "copper",
                lambda a: _stat(a, "wiki_pages") >= 1, "wiki_pages", 1),
    Achievement("dreamer", "Dreamer", "Ran a memory consolidation cycle.", "bronze",
                lambda a: _stat(a, "dream_cycles") >= 1, "dream_cycles", 1),
    Achievement("night_owl", "Uptime Champion", "Backend has been running for 24+ hours straight.", "silver",
                lambda a: _stat(a, "uptime_hours") >= 24, "uptime_hours", 24),
]


def _progress_for(ach: Achievement, activity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if ach.stat_key is None:
        return None
    target = ach.target if ach.target is not None else _dynamic_target(ach.key, activity)
    if not target:
        return None
    current = activity.get(ach.stat_key, 0) or 0
    return {"current": round(current, 1) if isinstance(current, float) else current, "target": target}


def _load_unlock_times() -> Dict[str, float]:
    try:
        with open(_UNLOCKS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_unlock_times(times: Dict[str, float]) -> None:
    try:
        os.makedirs(os.path.dirname(_UNLOCKS_PATH), exist_ok=True)
        with open(_UNLOCKS_PATH, "w") as f:
            json.dump(times, f, indent=2)
    except Exception as e:
        logger.warning("achievements_store: failed saving unlock times: %s", e)


def record_unlocks(unlocked_keys: List[str]) -> tuple[Dict[str, float], List[str]]:
    """Persist the first moment each badge went true -- badges are
    recomputed live from current stats every call, so without this the
    exact unlock time is lost the instant the underlying stat changes
    again. Returns (full key -> unix-timestamp map, keys newly unlocked on
    *this* call) -- the second lets a caller fire a real "just happened"
    event (e.g. an achievement_unlocked webhook) exactly once per badge,
    on whichever poll first observes it, rather than re-firing on every
    subsequent call now that the badge is persisted as unlocked."""
    times = _load_unlock_times()
    newly: List[str] = []
    now = time.time()
    for key in unlocked_keys:
        if key not in times:
            times[key] = now
            newly.append(key)
    if newly:
        _save_unlock_times(times)
    return times, newly


def compute_unlocked(activity: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Real, deterministic evaluation against real activity numbers --
    never raises (a bad/missing stat just means that achievement's check
    evaluates False rather than crashing the whole computation)."""
    unlocked = []
    for ach in ACHIEVEMENTS:
        try:
            if ach.check(activity):
                unlocked.append({"key": ach.key, "title": ach.title, "description": ach.description, "tier": ach.tier})
        except Exception as e:
            logger.warning("achievements_store: check for %s failed: %s", ach.key, e)
    return unlocked


def all_achievements(activity: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    activity = activity or {}
    return [
        {
            "key": a.key, "title": a.title, "description": a.description, "tier": a.tier,
            "progress": _progress_for(a, activity),
        }
        for a in ACHIEVEMENTS
    ]
