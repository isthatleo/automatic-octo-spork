"""Knowledge Engine -- Book II Phase IV, Book IV Ch.7 (Knowledge Agent),
Book V Ch.7/10/13 (Knowledge Graph / Digital Brain / Knowledge Evolution).

Composes two subsystems that were already real (memory/graph.py's embeddings
and doc_extraction.py's PDF/DOCX text extraction) into a third: entities and
relationships resolved out of that text into a persisted graph. See
graph.py's module docstring for why this stayed a deliberately scoped,
evidence-grounded pass rather than open-ended generative clustering --
memory/wiki_store.py made the same call for the same reason.
"""

from knowledge.graph import EntityType, KnowledgeEdge, KnowledgeGraph, KnowledgeNode, RelationType

__all__ = ["KnowledgeGraph", "KnowledgeNode", "KnowledgeEdge", "EntityType", "RelationType"]
