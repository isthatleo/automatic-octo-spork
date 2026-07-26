"""Real "Journey" timeline -- ported from Hermes' learning_graph/journey
feature. Builds a single chronological timeline from two real, already-
persisted data sources: MemoryGraph/LanceDBMemoryGraph nodes (memories, each
with a real created_at) and skill_loader.py's skill_usage.json (each skill's
most recent match time + total match count -- the usage store only tracks
the latest match per skill, not a full per-match history, so this
represents "skill X last used at time Y (used N times total)" rather than
fabricating individual historical events the data doesn't actually contain).
"""
from __future__ import annotations

from typing import Any, Dict, List


def build_timeline(graph: Any, limit: int = 100) -> List[Dict[str, Any]]:
    """Returns a chronological (newest-first) list of
    {"timestamp", "kind", "label", "detail"} entries merged from memory
    nodes and skill usage."""
    import skill_loader

    events: List[Dict[str, Any]] = []

    for node in graph.nodes.values():
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(node.created_at).timestamp()
        except Exception:
            continue
        events.append({
            "timestamp": ts,
            "kind": "memory",
            "label": f"{node.type.value}: {node.content[:60]}",
            "detail": {"id": node.id, "importance": node.importance, "type": node.type.value},
        })

    for skill in skill_loader.list_skills():
        usage = skill_loader._USAGE.get(skill.name)
        if not usage or not usage.get("last_matched_at"):
            continue
        events.append({
            "timestamp": usage["last_matched_at"],
            "kind": "skill",
            "label": f"Used skill: {skill.name}",
            "detail": {"match_count": usage.get("match_count", 0), "description": skill.description},
        })

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events[:limit]


def summary_stats(graph: Any) -> Dict[str, Any]:
    import skill_loader

    by_type: Dict[str, int] = {}
    for node in graph.nodes.values():
        by_type[node.type.value] = by_type.get(node.type.value, 0) + 1

    skill_usage_total = sum(int(u.get("match_count", 0)) for u in skill_loader._USAGE.values())

    return {
        "total_memories": len(graph.nodes),
        "memories_by_type": by_type,
        "skills_used_count": len([u for u in skill_loader._USAGE.values() if u.get("match_count", 0) > 0]),
        "skill_uses_total": skill_usage_total,
    }
