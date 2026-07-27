"""Real gamified achievements -- ported from Hermes' Hermes-Achievements
plugin. Badges are computed from real, already-persisted activity (agent
task history via agent_service.py's stats, real terminal/file executions
via evidence_ledger.py, real skill usage via skill_loader.py's usage store)
-- nothing here is a fake counter incremented for its own sake; every badge
reflects something that genuinely already happened.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Achievement:
    key: str
    title: str
    description: str
    tier: str  # copper, bronze, silver, gold, olympian
    check: Callable[[Dict[str, Any]], bool]


def _stat(activity: Dict[str, Any], key: str, default: int = 0) -> int:
    return int(activity.get(key, default) or 0)


ACHIEVEMENTS: List[Achievement] = [
    Achievement("first_task", "First Steps", "Ran your first agent task.", "copper",
                lambda a: _stat(a, "total_tasks") >= 1),
    Achievement("ten_tasks", "Getting Going", "Ran 10 agent tasks.", "bronze",
                lambda a: _stat(a, "total_tasks") >= 10),
    Achievement("hundred_tasks", "Fleet Commander", "Ran 100 agent tasks.", "silver",
                lambda a: _stat(a, "total_tasks") >= 100),
    Achievement("thousand_tasks", "Automation Olympian", "Ran 1,000 agent tasks.", "olympian",
                lambda a: _stat(a, "total_tasks") >= 1000),
    Achievement("perfect_streak", "Flawless", "100% success rate over at least 20 tasks.", "gold",
                lambda a: _stat(a, "total_tasks") >= 20 and _stat(a, "failed_tasks") == 0),
    Achievement("first_command", "Hands on the Wheel", "Ran your first real terminal command.", "copper",
                lambda a: _stat(a, "terminal_commands") >= 1),
    Achievement("fifty_commands", "Power User", "Ran 50 real terminal commands.", "bronze",
                lambda a: _stat(a, "terminal_commands") >= 50),
    Achievement("first_file_write", "Builder", "Wrote your first real file.", "copper",
                lambda a: _stat(a, "file_writes") >= 1),
    Achievement("skill_explorer", "Skill Explorer", "Used 5 different skills.", "bronze",
                lambda a: _stat(a, "distinct_skills_used") >= 5),
    Achievement("skill_master", "Skill Master", "Used every skill in the library at least once.", "gold",
                lambda a: _stat(a, "distinct_skills_used") > 0 and _stat(a, "distinct_skills_used") >= _stat(a, "total_skills")),
    Achievement("memory_keeper", "Memory Keeper", "Stored 50 real memories.", "bronze",
                lambda a: _stat(a, "total_memories") >= 50),
    Achievement("wiki_contributor", "Wiki Contributor", "Created your first memory wiki page.", "copper",
                lambda a: _stat(a, "wiki_pages") >= 1),
    Achievement("dreamer", "Dreamer", "Ran a memory consolidation cycle.", "bronze",
                lambda a: _stat(a, "dream_cycles") >= 1),
    Achievement("night_owl", "Uptime Champion", "Backend has been running for 24+ hours straight.", "silver",
                lambda a: _stat(a, "uptime_hours") >= 24),
]


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


def all_achievements() -> List[Dict[str, Any]]:
    return [{"key": a.key, "title": a.title, "description": a.description, "tier": a.tier} for a in ACHIEVEMENTS]
