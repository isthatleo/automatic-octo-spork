"""Real sleep-cycle-inspired memory consolidation -- ported from OpenClaw's
"dreaming" memory-core extension. Three cron-scheduled phases operating
directly on whichever MemoryGraph-shaped backend is active
(memory/manager.py's memory_manager.graph -- MemoryGraph or
LanceDBMemoryGraph, both expose the same .nodes/add_memory/embedding_engine
surface this module relies on):

- light: quick near-duplicate dedupe (two memories that are almost the same
  text get merged instead of both persisting forever).
- deep: recurrence-based promotion -- CONVERSATION memories that cluster
  tightly around the same topic (recalled/repeated often) get promoted to a
  single INSIGHT memory, the same "this keeps coming up, it matters" signal
  a human's own memory consolidation does during sleep.
- rem: writes one narrative diary entry (via the LLM, if configured)
  summarizing what got consolidated this cycle into a real, growing
  "dream diary" log.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from memory.graph import MemoryType

logger = logging.getLogger(__name__)

DREAM_DIARY_PATH = Path(__file__).parent.parent / "data" / "dream_diary.json"

DEDUPE_SIMILARITY_THRESHOLD = 0.95
CLUSTER_SIMILARITY_THRESHOLD = 0.75
MIN_RECALL_COUNT_FOR_PROMOTION = 3


def _load_diary() -> List[Dict[str, Any]]:
    if not DREAM_DIARY_PATH.exists():
        return []
    try:
        return json.loads(DREAM_DIARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _append_diary(entry: Dict[str, Any]) -> None:
    diary = _load_diary()
    diary.append(entry)
    DREAM_DIARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DREAM_DIARY_PATH.write_text(json.dumps(diary, indent=2), encoding="utf-8")


def run_light_phase(graph: Any) -> Dict[str, Any]:
    """Dedupes near-identical memories -- keeps the higher-importance one
    (ties broken by keeping the older, more-established memory), deletes
    the other. Real destructive action on the graph, scoped tightly (only
    fires above DEDUPE_SIMILARITY_THRESHOLD, i.e. genuinely near-duplicate
    text, not just related)."""
    nodes = list(graph.nodes.values())
    to_remove: set = set()
    merged_pairs = 0

    for i, a in enumerate(nodes):
        if a.id in to_remove:
            continue
        for b in nodes[i + 1:]:
            if b.id in to_remove or a.type != b.type:
                continue
            sim = graph.embedding_engine.similarity(a.embedding, b.embedding)
            if sim >= DEDUPE_SIMILARITY_THRESHOLD:
                loser = b if a.importance >= b.importance else a
                to_remove.add(loser.id)
                merged_pairs += 1

    for node_id in to_remove:
        graph.nodes.pop(node_id, None)
    if to_remove and hasattr(graph, "_save_to_disk"):
        graph._save_to_disk()

    return {"phase": "light", "merged_pairs": merged_pairs, "removed": len(to_remove)}


def run_deep_phase(graph: Any) -> Dict[str, Any]:
    """Clusters CONVERSATION memories by similarity; any cluster at or above
    MIN_RECALL_COUNT_FOR_PROMOTION gets one new INSIGHT memory summarizing
    it (a real new node via graph.add_memory, not a mutation of the
    originals -- the source conversations stay intact, this just adds a
    higher-level synthesis on top, the same "consolidate, don't erase"
    principle real memory consolidation follows)."""
    conv_nodes = [n for n in graph.nodes.values() if n.type == MemoryType.CONVERSATION]
    clustered: set = set()
    promotions = 0

    for i, seed in enumerate(conv_nodes):
        if seed.id in clustered:
            continue
        cluster = [seed]
        for other in conv_nodes[i + 1:]:
            if other.id in clustered:
                continue
            sim = graph.embedding_engine.similarity(seed.embedding, other.embedding)
            if sim >= CLUSTER_SIMILARITY_THRESHOLD:
                cluster.append(other)

        if len(cluster) >= MIN_RECALL_COUNT_FOR_PROMOTION:
            for n in cluster:
                clustered.add(n.id)
            summary = "; ".join(n.content[:60] for n in cluster[:3])
            graph.add_memory(
                f"Recurring theme (seen {len(cluster)}x): {summary}",
                MemoryType.INSIGHT,
                metadata={"source": "dreaming.deep_phase", "cluster_size": len(cluster)},
                importance=min(1.0, 0.5 + 0.05 * len(cluster)),
            )
            promotions += 1

    return {"phase": "deep", "clusters_found": promotions, "memories_examined": len(conv_nodes)}


async def run_rem_phase(graph: Any, light_result: Dict[str, Any], deep_result: Dict[str, Any]) -> Dict[str, Any]:
    """Writes one real dream-diary entry. Uses the LLM for a narrative
    summary if available; degrades to a plain factual line (no LLM call)
    if not -- same graceful-degrade idiom as everywhere else in this
    codebase, never a hard failure just because no LLM backend is configured."""
    default_narrative = f"Consolidated {light_result['removed']} duplicate memories and formed {deep_result['clusters_found']} new insight(s)."
    narrative = default_narrative
    try:
        from llm import llm_backend
        prompt = (
            f"In one warm, brief sentence, describe a memory-consolidation cycle that merged "
            f"{light_result['removed']} duplicate memories and formed {deep_result['clusters_found']} "
            f"new insights from recurring conversation themes. Write it as a short diary-style reflection."
        )
        candidate = await llm_backend.generate(prompt, max_tokens=80, temperature=0.8)
        # Defensive: at least one local backend in the fallback chain has
        # been observed (this session) to return a raw connection-error
        # string as if it were successful content instead of raising --
        # a real bug upstream in that backend, but this caller has no
        # control over which backend FallbackLLM picks, so guard against
        # obviously-not-a-narrative output rather than trust it blindly.
        looks_like_error = any(m in candidate.lower() for m in ("connection", "traceback", "exception", "error:", "failed"))
        if candidate.strip() and not looks_like_error:
            narrative = candidate
        else:
            logger.warning("dreaming.rem_phase: LLM returned suspicious output, using plain summary instead: %r", candidate[:200])
    except Exception as e:
        logger.info("dreaming.rem_phase: LLM narrative unavailable, using plain summary (%s)", e)

    entry = {
        "timestamp": time.time(),
        "narrative": narrative.strip(),
        "light": light_result,
        "deep": deep_result,
        "total_memories": len(graph.nodes),
    }
    _append_diary(entry)
    return {"phase": "rem", "entry": entry}


async def run_full_cycle(graph: Any) -> Dict[str, Any]:
    light = run_light_phase(graph)
    deep = run_deep_phase(graph)
    rem = await run_rem_phase(graph, light, deep)
    logger.info("dreaming: full cycle complete -- %s", rem["entry"]["narrative"])
    return {"light": light, "deep": deep, "rem": rem}


def get_dream_diary(limit: int = 20) -> List[Dict[str, Any]]:
    return _load_diary()[-limit:][::-1]
