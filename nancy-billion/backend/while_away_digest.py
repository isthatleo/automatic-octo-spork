"""Real "while you were away" digest -- aggregates what the autonomous
fleet actually did since the user last looked, from already-persisted
sources only. Nothing here is generated for the occasion; every item is a
pointer to a real record that already existed before this module ran.

Deliberately reads main_new's live singletons (memory_manager, agent_service)
via a lazy import rather than a top-level one -- main_new.py imports this
module for its /digest/while-away routes, so a top-level `from main_new
import ...` here would be a circular import at module-load time. The same
lazy-import-inside-the-function idiom is already used by
agents/specialized/task_orchestrator_agent.py for the same reason.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Memory-graph node metadata["source"] values that represent real autonomous
# fleet output worth surfacing here -- NOT every memory (a raw conversation
# memory is not "something that happened while you were away", it's the
# conversation itself; including it would turn the digest into a second copy
# of the chat log).
_AUTONOMOUS_SOURCES = {
    "fleet_sweep": "fleet_sweep",
    "proactive_orchestrator": "proactive_orchestrator",
    "dreaming.deep_phase": "dreaming",
    "agent_collaboration": "agent_collaboration",
}


def _node_timestamp(node: Any) -> float:
    try:
        return datetime.fromisoformat(node.created_at).timestamp()
    except Exception:
        return 0.0


async def build_digest(since_ts: float) -> Dict[str, Any]:
    import main_new  # lazy -- see module docstring
    from memory import dreaming, wiki_store
    import achievements_store

    items: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    agent_keys_touched: set = set()

    # 1. Memory graph nodes written by the autonomous fleet since the cursor.
    graph = main_new.memory_manager.graph
    for node in graph.nodes.values():
        source = (node.metadata or {}).get("source")
        kind = _AUTONOMOUS_SOURCES.get(source)
        if kind is None:
            continue
        ts = _node_timestamp(node)
        if ts <= since_ts:
            continue
        agent_key = node.metadata.get("agent_key") or node.metadata.get("producer")
        if kind == "fleet_sweep" and agent_key:
            agent_keys_touched.add(agent_key)
        items.append({"kind": kind, "text": node.content, "at": ts, "agent_key": agent_key})
        counts[kind] = counts.get(kind, 0) + 1

    # 2. Dream diary entries (the narrative half of consolidation cycles --
    # distinct from the individual promoted-insight nodes already captured
    # above via source="dreaming.deep_phase").
    for entry in dreaming.get_dream_diary(limit=200):
        ts = float(entry.get("timestamp", 0.0) or 0.0)
        if ts <= since_ts:
            continue
        items.append({"kind": "dream_narrative", "text": entry.get("narrative", ""), "at": ts})
        counts["dream_narrative"] = counts.get("dream_narrative", 0) + 1

    # 3. New wiki pages.
    for page in wiki_store.list_pages():
        if page.created_at <= since_ts:
            continue
        items.append({
            "kind": "wiki_page", "text": f"{page.title} -- {page.claim}", "at": page.created_at,
        })
        counts["wiki_page"] = counts.get("wiki_page", 0) + 1

    # 4. Achievements newly unlocked since the cursor. Reads the persisted
    # unlock times only -- does not recompute/re-record here, that already
    # happens on every /achievements poll.
    unlock_times = achievements_store.get_unlock_times()
    by_key = {a.key: a for a in achievements_store.ACHIEVEMENTS}
    for key, unlocked_at in unlock_times.items():
        if unlocked_at <= since_ts:
            continue
        ach = by_key.get(key)
        if ach is None:
            continue
        items.append({"kind": "achievement", "text": f"Unlocked: {ach.title} -- {ach.description}", "at": unlocked_at})
        counts["achievement"] = counts.get("achievement", 0) + 1

    items.sort(key=lambda i: i["at"], reverse=True)

    total_agents = len(main_new.agent_service.list_agents()) if main_new.agent_service.is_ready() else 0
    total_new_memories = sum(v for k, v in counts.items() if k in ("fleet_sweep", "proactive_orchestrator", "dreaming", "agent_collaboration"))

    headline = (
        f"{len(items)} update{'s' if len(items) != 1 else ''} while you were away"
        if items else "Nothing new since you last checked"
    )

    return {
        "success": True,
        "since": since_ts,
        "generated_at": time.time(),
        "headline": headline,
        "counts": {
            **counts,
            "agents_touched": len(agent_keys_touched),
            "total_agents": total_agents,
            "new_memories": total_new_memories,
        },
        "items": items[:60],
    }
