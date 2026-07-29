"""Real LanceDB-backed alternative to MemoryGraph's brute-force in-memory
cosine scan -- ported from OpenClaw's memory-lancedb extension. Implements
the exact same public interface as memory/graph.py's MemoryGraph (add_memory,
query, query_with_scores, get_conversation_context, get_project_memories,
get_trade_history, infer_connections, summarize_memory, .nodes) so it's a
genuine drop-in: memory/manager.py picks whichever backend based on
MEMORY_BACKEND, and every downstream caller (which only ever touches these
methods/attributes) works unmodified either way.

Reuses the SAME embedding engine graph.py already loads (sentence-transformers
all-MiniLM-L6-v2) rather than loading a second copy of the model -- LanceDB's
job here is purely the storage/query engine (a real embedded ANN index via
Lance's columnar format), not a second embedding source.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from memory.graph import MemoryNode, MemoryType, _create_embedding_engine

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "lancedb_memory"
TABLE_NAME = "memories"


class LanceDBMemoryGraph:
    """Drop-in alternative to MemoryGraph. `.nodes` is a real dict kept in
    sync with the LanceDB table (LanceDB is the source of truth on disk;
    `.nodes` is an in-memory mirror rebuilt from it at startup) so existing
    code doing `memory_manager.graph.nodes` keeps working unmodified."""

    def __init__(self, storage_path: str = str(DB_PATH)) -> None:
        import lancedb
        import pyarrow as pa

        self.storage_path = storage_path
        self.embedding_engine = _create_embedding_engine()
        self._db = lancedb.connect(storage_path)
        self.nodes: Dict[str, MemoryNode] = {}

        if TABLE_NAME in self._db.table_names():
            self._table = self._db.open_table(TABLE_NAME)
            self._load_nodes_from_table()
        else:
            # Schema inferred from a throwaway probe embedding so the vector
            # column's dimensionality always matches whatever embedding
            # engine is actually active (384 for sentence-transformers, 1000
            # for the SimpleEmbedding fallback).
            dim = len(self.embedding_engine.embed("_probe_"))
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("type", pa.string()),
                pa.field("content", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
                pa.field("importance", pa.float64()),
                pa.field("created_at", pa.string()),
                pa.field("links", pa.string()),  # JSON-encoded list[str]
                pa.field("metadata", pa.string()),  # JSON-encoded dict
            ])
            self._table = self._db.create_table(TABLE_NAME, schema=schema)

        logger.info("LanceDBMemoryGraph initialized with %d existing memories", len(self.nodes))

    def _load_nodes_from_table(self) -> None:
        import json
        for row in self._table.to_pandas().itertuples():
            try:
                node = MemoryNode(
                    id=row.id, type=MemoryType(row.type), content=row.content,
                    embedding=list(row.vector), metadata=json.loads(row.metadata),
                    links=json.loads(row.links), importance=row.importance, created_at=row.created_at,
                )
                self.nodes[node.id] = node
            except Exception as e:
                logger.warning("LanceDBMemoryGraph: failed to load row %s: %s", getattr(row, "id", "?"), e)

    def _generate_id(self, content: str) -> str:
        import hashlib
        return f"mem_{hashlib.md5(content.encode()).hexdigest()[:8]}"

    def add_memory(self, content: str, memory_type: MemoryType, metadata: Optional[Dict] = None, importance: float = 0.5) -> MemoryNode:
        import json
        if metadata is None:
            metadata = {}
        node_id = self._generate_id(content)
        if node_id in self.nodes:
            return self.nodes[node_id]

        embedding = self.embedding_engine.embed(content)
        related_ids = self._find_related(embedding, top_k=5, exclude_id=node_id)
        node = MemoryNode(id=node_id, type=memory_type, content=content, embedding=embedding, metadata=metadata, links=related_ids, importance=importance)

        self._table.add([{
            "id": node.id, "type": node.type.value, "content": node.content, "vector": node.embedding,
            "importance": node.importance, "created_at": node.created_at,
            "links": json.dumps(node.links), "metadata": json.dumps(node.metadata),
        }])
        self.nodes[node_id] = node
        return node

    def _find_related(self, embedding: List[float], top_k: int, exclude_id: str = "") -> List[str]:
        if len(self.nodes) == 0:
            return []
        try:
            results = self._table.search(embedding).limit(top_k + 1).to_list()
            return [r["id"] for r in results if r["id"] != exclude_id][:top_k]
        except Exception as e:
            logger.warning("LanceDBMemoryGraph: related-memory search failed: %s", e)
            return []

    def query_with_scores(self, query_text: str, top_k: int = 10, threshold: float = 0.3) -> List[Tuple[MemoryNode, float]]:
        if len(self.nodes) == 0:
            return []
        query_embedding = self.embedding_engine.embed(query_text)
        try:
            results = self._table.search(query_embedding).limit(top_k).to_list()
        except Exception as e:
            logger.warning("LanceDBMemoryGraph: query failed: %s", e)
            return []

        out: List[Tuple[MemoryNode, float]] = []
        for r in results:
            node = self.nodes.get(r["id"])
            if node is None:
                continue
            # LanceDB's default metric is L2 distance on this schema; convert
            # to a cosine-similarity-like score in [0, 1] via the same
            # normalized-vector dot-product MemoryGraph's own similarity()
            # would produce, so `threshold` means the same thing either way.
            score = self.embedding_engine.similarity(query_embedding, node.embedding)
            if score >= threshold:
                out.append((node, score))
        out.sort(key=lambda x: x[1], reverse=True)
        return out[:top_k]

    def query(self, query_text: str, top_k: int = 10, threshold: float = 0.3) -> List[MemoryNode]:
        return [node for node, _ in self.query_with_scores(query_text, top_k=top_k, threshold=threshold)]

    def get_conversation_context(self, num_memories: int = 5) -> List[MemoryNode]:
        conv = [n for n in self.nodes.values() if n.type == MemoryType.CONVERSATION]
        conv.sort(key=lambda x: x.created_at, reverse=True)
        return conv[:num_memories]

    def get_project_memories(self) -> List[MemoryNode]:
        return [n for n in self.nodes.values() if n.type == MemoryType.PROJECT]

    def get_trade_history(self) -> List[MemoryNode]:
        return [n for n in self.nodes.values() if n.type == MemoryType.TRADE]

    def infer_connections(self, node_id: str) -> List[Tuple[str, float]]:
        if node_id not in self.nodes:
            return []
        node = self.nodes[node_id]
        connections = []
        for other_id, other in self.nodes.items():
            if other_id == node_id:
                continue
            sim = self.embedding_engine.similarity(node.embedding, other.embedding)
            if sim > 0.3:
                connections.append((other_id, sim))
        connections.sort(key=lambda x: x[1], reverse=True)
        return connections

    def summarize_memory(self, node_id: str) -> Dict:
        if node_id not in self.nodes:
            return {}
        node = self.nodes[node_id]
        connections = self.infer_connections(node_id)
        return {
            "id": node.id, "type": node.type.value, "content": node.content,
            "importance": node.importance, "created": node.created_at,
            "connections": [
                {"id": cid, "content": self.nodes[cid].content, "strength": strength}
                for cid, strength in connections[:3]
            ],
        }


def create_memory_backend(storage_path: str = "data/memory_graph.json"):
    """Real backend switch -- returns LanceDBMemoryGraph if MEMORY_BACKEND=lancedb
    AND lancedb actually imports cleanly; otherwise returns today's
    MemoryGraph unchanged. This is the one place that decision is made, so
    memory/manager.py's __init__ stays a one-line call regardless of outcome."""
    import os
    if os.getenv("MEMORY_BACKEND", "graph").lower() == "lancedb":
        try:
            # A non-default storage_path (see memory/manager.py's household
            # profile support) maps to its own LanceDB directory too, so a
            # profile's memory is actually isolated under either backend --
            # not just the default MemoryGraph/JSON path.
            if storage_path == "data/memory_graph.json":
                lancedb_path = str(DB_PATH)
            else:
                lancedb_path = str(DB_PATH.parent / f"lancedb_{Path(storage_path).stem}")
            return LanceDBMemoryGraph(lancedb_path)
        except Exception as e:
            logger.warning("MEMORY_BACKEND=lancedb requested but unavailable (%s) -- falling back to MemoryGraph", e)
    from memory.graph import MemoryGraph
    return MemoryGraph(storage_path)
