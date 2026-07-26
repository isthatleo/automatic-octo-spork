"""Extensions for MemoryManager."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class _MemorySearchResult:
    def __init__(self, content: str, score: float, meta: Optional[Dict[str, Any]] = None) -> None:
        self.content = content
        self.score = float(score)
        self.meta = meta or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "relevance_score": self.score,
            "memory_type": self.meta.get("memory_type"),
            "source": self.meta.get("source"),
        }


class _SemanticRetriever:
    """Was _KeywordRetriever -- ran its own separate token-overlap scorer
    completely independent of MemoryGraph's own (now real, embedding-based)
    query() method, so /memory/search and a direct graph.query() call could
    disagree about what's relevant for the exact same question. Now a thin
    wrapper over graph.query_with_scores(), the same real semantic search
    used everywhere else -- one search behavior, not two."""

    def __init__(self, graph) -> None:
        self.graph = graph

    def search(self, query: str, top_k: int = 10) -> List[_MemorySearchResult]:
        q = str(query or "").strip()
        if not q:
            return []
        query_with_scores = getattr(self.graph, "query_with_scores", None)
        if query_with_scores is None:
            return []
        try:
            hits = query_with_scores(q, top_k=max(top_k, 1), threshold=0.2)
        except Exception:
            return []

        results: List[_MemorySearchResult] = []
        for node, score in hits:
            text = str(getattr(node, "content", "") or "")
            if not text:
                continue
            mem_type = getattr(getattr(node, "type", None), "value", None) or getattr(node, "type", None)
            results.append(
                _MemorySearchResult(
                    content=text,
                    score=float(score),
                    meta={"source": getattr(node, "metadata", None) or {}, "memory_type": mem_type},
                )
            )
        return results


# Old name kept as an alias -- nothing outside this file should construct
# either directly (both are wired up via _extend_memory_manager below), but
# this avoids breaking anything that imported the old name during the
# transition.
_KeywordRetriever = _SemanticRetriever


def _extend_memory_manager(manager_class) -> None:
    if getattr(manager_class, '__nancy_memory_extensions_patched_', False):
        return

    def search_memories(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        graph = getattr(self, "graph", None)
        if graph is None:
            return []
        if not hasattr(self, "_keyword_retriever"):
            try:
                self._keyword_retriever = _KeywordRetriever(graph)  # type: ignore[attr-defined]
            except Exception:
                return []
        try:
            hits = self._keyword_retriever.search(query, top_k=top_k)  # type: ignore[attr-defined]
        except Exception:
            return []
        return [hit.to_dict() for hit in hits]

    def get_search_results(self, query: str, top_k: int = 10) -> List[_MemorySearchResult]:
        graph = getattr(self, "graph", None)
        if graph is None:
            return []
        if not hasattr(self, "_keyword_retriever"):
            try:
                self._keyword_retriever = _KeywordRetriever(graph)  # type: ignore[attr-defined]
            except Exception:
                return []
        try:
            return self._keyword_retriever.search(query, top_k=top_k)  # type: ignore[attr-defined]
        except Exception:
            return []

    def clear_conversation(self) -> bool:
        graph = getattr(self, "graph", None)
        if graph is None:
            return False
        try:
            before = len(getattr(graph, "nodes", {}))
            graph.nodes = {
                node_id: node
                for node_id, node in getattr(graph, "nodes", {}).items()
                if getattr(node, "type", None) != getattr(__import__('memory.graph', fromlist=['MemoryType']).MemoryType, 'CONVERSATION', 'conversation')
            }
            after = len(getattr(graph, "nodes", {}))
            try:
                graph._save_to_disk()  # type: ignore[attr-defined]
            except Exception:
                pass
            return after < before
        except Exception:
            return False

    def build_skills_prompt_injection(self) -> str:
        store = _resolve_skills_store()
        if store is None or not getattr(store, 'list', lambda: [])():
            return ""
        lines = ["Skills:"]
        try:
            for skill in store.list():
                items = ", ".join(skill.agent_keys) if skill.agent_keys else "general"
                lines.append(f"- {skill.name}: {skill.description} [{items}]")
        except Exception:
            return ""
        return "\n".join(lines)

    manager_class.search_memories = search_memories  # type: ignore[attr-defined]
    manager_class.get_search_results = get_search_results  # type: ignore[attr-defined]
    manager_class.clear_conversation = clear_conversation  # type: ignore[attr-defined]
    manager_class.build_skills_prompt_injection = build_skills_prompt_injection  # type: ignore[attr-defined]
    manager_class._nancy_memory_extensions_patched_ = True  # type: ignore[attr-defined]


def _resolve_skills_store():
    try:
        from skills_store import skills_store  # type: ignore[import]
        return skills_store
    except Exception:
        try:
            from nancy_billion.backend.skills_store import skills_store  # type: ignore[import]
            return skills_store
        except Exception:
            return None


def memory_search(manager, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    if manager is None or not query or not hasattr(manager, "search_memories"):
        return []
    try:
        return list(manager.search_memories(query, top_k=top_k) or [])
    except Exception:
        return []

