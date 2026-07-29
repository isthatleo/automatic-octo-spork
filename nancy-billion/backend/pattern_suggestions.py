"""Real adaptive automation suggestions, mined from the memory graph's own
real mention_count/last_mentioned_at data (see memory/graph.py's
add_or_merge_memory) -- "you've mentioned X 4 times, want a standing watch/
macro for that?" rather than a fixed rule list. Deliberately simple: no ML,
just a real recurrence threshold over data that's already there.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "suggested_patterns.json"

# A topic needs to have come up at least this many times before it's worth
# suggesting automation for -- below this, it's just normal conversation,
# not a real recurring pattern.
MIN_MENTIONS_FOR_SUGGESTION = 3


def _load_suggested() -> Set[str]:
    if not STORE_PATH.exists():
        return set()
    try:
        return set(json.loads(STORE_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_suggested(node_ids: Set[str]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(sorted(node_ids)), encoding="utf-8")


def find_recurring_topics(graph) -> List[Dict[str, Any]]:
    """Real scan of memory_manager.graph.nodes for anything mentioned
    MIN_MENTIONS_FOR_SUGGESTION+ times -- these are genuinely recurring
    topics, not a guess. Returns richest-first (most mentions first)."""
    candidates = []
    for node in graph.nodes.values():
        mention_count = (node.metadata or {}).get("mention_count", 1)
        if mention_count >= MIN_MENTIONS_FOR_SUGGESTION:
            candidates.append({
                "node_id": node.id,
                "type": node.type.value,
                "content": node.content,
                "mention_count": mention_count,
                "last_mentioned_at": (node.metadata or {}).get("last_mentioned_at", node.created_at),
            })
    candidates.sort(key=lambda c: c["mention_count"], reverse=True)
    return candidates


def get_new_suggestions(graph, limit: int = 5) -> List[Dict[str, Any]]:
    """Real recurring topics that haven't already been suggested before --
    the one-shot filter that keeps the periodic check from repeating itself
    forever on the same handful of topics."""
    already = _load_suggested()
    recurring = find_recurring_topics(graph)
    fresh = [c for c in recurring if c["node_id"] not in already][:limit]
    if fresh:
        already.update(c["node_id"] for c in fresh)
        _save_suggested(already)
    return fresh


def format_suggestion(candidate: Dict[str, Any]) -> str:
    preview = candidate["content"][:100]
    return (
        f"Sir, you've mentioned this {candidate['mention_count']} times: \"{preview}\" -- "
        f"want me to set up a watch or a macro for it?"
    )
