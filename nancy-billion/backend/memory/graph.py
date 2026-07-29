"""
Memory Graph System for Nancy/Billion

This module provides:
- Knowledge graph for storing memories
- Vector embeddings for semantic similarity
- Memory retrieval and inference
- Long-term context building
"""

import json
import logging
import hashlib
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Types of memories Nancy can store"""
    CONVERSATION = "conversation"
    PROJECT = "project"
    DECISION = "decision"
    FACT = "fact"
    TRADE = "trade"
    INSIGHT = "insight"
    PERSON = "person"
    EVENT = "event"


@dataclass
class MemoryNode:
    """A single memory node in the knowledge graph"""
    id: str
    type: MemoryType
    content: str
    embedding: List[float]
    metadata: Dict
    links: List[str] = None  # IDs of related memories
    importance: float = 0.5  # 0.0 - 1.0
    created_at: str = None

    def __post_init__(self):
        if self.links is None:
            self.links = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['type'] = self.type.value
        return data


class SimpleEmbedding:
    """
    Hashed-bag-of-words fallback -- only used if sentence-transformers isn't
    importable or its model fails to load (e.g. no internet on first run to
    fetch weights). Real semantic similarity lives in SentenceTransformerEmbedding
    below; this exists purely so memory search degrades to "still works, just
    keyword-ish" instead of crashing, same tradeoff already made everywhere
    else in this codebase (NeuTTS -> Pyttsx3, Claude -> fallback chain, etc.).
    """

    def __init__(self, vocab_size: int = 1000):
        self.vocab_size = vocab_size
        self.vocabulary = {}
        self.idf = {}

    def embed(self, text: str) -> List[float]:
        """
        Create embedding for text.
        Returns vector of fixed size.
        """
        words = self._tokenize(text)
        embedding = [0.0] * self.vocab_size

        for word in words:
            word_idx = hash(word) % self.vocab_size
            embedding[word_idx] += 1.0

        # Normalize
        total = sum(embedding)
        if total > 0:
            embedding = [x / total for x in embedding]

        return embedding

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization"""
        return text.lower().split()

    def similarity(self, emb1: List[float], emb2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings"""
        if len(emb1) != len(emb2):
            # A memory saved under a different embedding engine (e.g. before
            # this machine had sentence-transformers available) has a
            # different vector length -- zip() would silently truncate to
            # the shorter one and produce a meaningless score instead of
            # erroring, so treat it as simply unrelated rather than trusting
            # a comparison that was never valid.
            return 0.0
        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = sum(a * a for a in emb1) ** 0.5
        norm2 = sum(b * b for b in emb2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


class SentenceTransformerEmbedding:
    """Real semantic embeddings via sentence-transformers (all-MiniLM-L6-v2:
    22M params, 384-dim, fast enough on CPU for single short texts -- this
    replaces SimpleEmbedding's hashed-bag-of-words, which could only ever
    match on literal shared words, never actual meaning ("what's my trading
    performance" would never match a memory saying "I closed the EUR/USD
    position for a profit" -- no words in common, same meaning).

    Same embed()/similarity() interface as SimpleEmbedding, so MemoryGraph
    doesn't need to know which one it's using. Lazy-loaded (the model isn't
    fetched/loaded until the first real .embed() call) -- see
    main_new.py's _prewarm_memory_embeddings for why that first call is
    pre-warmed at startup instead of stalling a user's first real message.
    """

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self):
        self._model = None

    def _ensure_loaded(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading memory embedding model (%s)...", self.MODEL_NAME)
            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("Memory embedding model loaded.")
        return self._model

    def embed(self, text: str) -> List[float]:
        model = self._ensure_loaded()
        # normalize_embeddings=True means the vectors are already unit-length,
        # so cosine similarity below is just a dot product -- no need to
        # recompute norms on every comparison.
        vector = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vector.tolist()

    def similarity(self, emb1: List[float], emb2: List[float]) -> float:
        if len(emb1) != len(emb2):
            return 0.0  # see SimpleEmbedding.similarity's comment on why
        return sum(a * b for a, b in zip(emb1, emb2))


def _create_embedding_engine():
    """sentence-transformers by default; falls back to the hashed-bag-of-words
    engine if the package or its model genuinely can't load (e.g. no network
    on a first run with no cached weights) -- degrades gracefully rather than
    taking memory search down entirely."""
    backend = os.getenv("MEMORY_EMBEDDING_BACKEND", "sentence-transformers").lower()
    if backend == "simple":
        return SimpleEmbedding()
    try:
        import sentence_transformers  # noqa: F401 -- just checking importability here

        return SentenceTransformerEmbedding()
    except Exception as e:
        logger.warning(
            "sentence-transformers unavailable (%s) -- memory search falling back "
            "to keyword-based similarity instead of real semantic matching.", e,
        )
        return SimpleEmbedding()


class MemoryGraph:
    """
    Knowledge graph storing Nancy's memories.

    Supports:
    - Storing memories as nodes
    - Linking related memories
    - Querying by similarity
    - Inferring connections
    """

    def __init__(self, storage_path: str = "data/memory_graph.json"):
        self.storage_path = storage_path
        self.nodes: Dict[str, MemoryNode] = {}
        self.embedding_engine = _create_embedding_engine()
        self._load_from_disk()
        logger.info(f"MemoryGraph initialized with {len(self.nodes)} existing memories")

    def add_memory(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Dict = None,
        importance: float = 0.5
    ) -> MemoryNode:
        """
        Add a new memory to the graph.

        Automatically:
        - Creates embedding
        - Finds related memories
        - Links them together
        """
        if metadata is None:
            metadata = {}

        # Generate ID
        node_id = self._generate_id(content)

        # Check if already exists
        if node_id in self.nodes:
            logger.debug(f"Memory already exists: {node_id}")
            return self.nodes[node_id]

        # Create embedding
        embedding = self.embedding_engine.embed(content)

        # Create node
        node = MemoryNode(
            id=node_id,
            type=memory_type,
            content=content,
            embedding=embedding,
            metadata=metadata,
            importance=importance
        )

        # Find and link related memories
        related_ids = self._find_related_memories(embedding, top_k=5)
        node.links = related_ids

        # Store
        self.nodes[node_id] = node

        logger.info(f"Added memory: {node_id} ({memory_type.value})")
        node.metadata.setdefault("mentions", [{"content": content, "at": node.created_at}])
        node.metadata.setdefault("last_mentioned_at", node.created_at)
        self._save_to_disk()

        return node

    # Real content-similarity threshold for merging into an existing node
    # rather than creating a new one. Calibrated live against the actual
    # SentenceTransformerEmbedding: same topic reworded scored ~0.82,
    # near-identical wording ~0.88, genuinely unrelated content ~0.01 --
    # a huge real margin, so 0.65 comfortably catches "the same topic
    # mentioned again in different words" without risking two distinct
    # topics of the same type ever colliding (0.82's own paraphrase case
    # would have missed the merge entirely at that threshold).
    MERGE_SIMILARITY_THRESHOLD = 0.65

    def add_or_merge_memory(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Dict = None,
        importance: float = 0.5,
    ) -> MemoryNode:
        """Like add_memory, but first checks for an existing node of the
        SAME type whose content is similar enough to be "the same topic
        mentioned again" -- merges into that node instead of creating a
        near-duplicate. Every individual mention's own text and timestamp
        is preserved in metadata["mentions"] (created_at stays the FIRST
        time the topic came up; metadata["last_mentioned_at"] tracks the
        most recent one), so nothing is lost, it's just consolidated --
        exactly what a real memory should do with "we talked about X
        again," rather than growing one node per raw message forever."""
        if metadata is None:
            metadata = {}
        embedding = self.embedding_engine.embed(content)

        best_match: Optional[MemoryNode] = None
        best_score = 0.0
        for node in self.nodes.values():
            if node.type != memory_type:
                continue
            score = self.embedding_engine.similarity(embedding, node.embedding)
            if score > best_score:
                best_score = score
                best_match = node

        if best_match is not None and best_score >= self.MERGE_SIMILARITY_THRESHOLD:
            now = datetime.now().isoformat()
            best_match.metadata.setdefault("mentions", [])
            best_match.metadata["mentions"].append({"content": content, "at": now})
            best_match.metadata["last_mentioned_at"] = now
            best_match.metadata["mention_count"] = len(best_match.metadata["mentions"])
            # A topic that keeps coming up is real signal it matters more.
            best_match.importance = min(1.0, best_match.importance + 0.03)
            logger.info(
                "Merged memory into existing node %s (%s, similarity %.2f, %d mentions)",
                best_match.id, memory_type.value, best_score, best_match.metadata["mention_count"],
            )
            self._save_to_disk()
            return best_match

        return self.add_memory(content, memory_type, metadata, importance)

    def query_with_scores(self, query_text: str, top_k: int = 10, threshold: float = 0.3) -> List[Tuple[MemoryNode, float]]:
        """Same real semantic search as query(), but also returns each
        result's similarity score -- used by memory/extensions.py's
        _SemanticRetriever (the /memory/search REST path), which used to
        run a completely separate token-overlap scorer instead of this
        same real embedding-based search."""
        query_embedding = self.embedding_engine.embed(query_text)

        similarities = []
        for node_id, node in self.nodes.items():
            similarity = self.embedding_engine.similarity(query_embedding, node.embedding)
            if similarity >= threshold:
                similarities.append((node_id, similarity, node))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return [(node, score) for _, score, node in similarities[:top_k]]

    def query(self, query_text: str, top_k: int = 10, threshold: float = 0.3) -> List[MemoryNode]:
        """
        Find memories similar to query.

        Returns top_k most similar memories above threshold.
        """
        results = [node for node, _score in self.query_with_scores(query_text, top_k=top_k, threshold=threshold)]

        logger.debug(f"Query returned {len(results)} memories")
        return results

    def get_conversation_context(self, num_memories: int = 5) -> List[MemoryNode]:
        """Get recent conversation memories for context"""
        conv_memories = [
            node for node in self.nodes.values()
            if node.type == MemoryType.CONVERSATION
        ]

        # Sort by recency
        conv_memories.sort(key=lambda x: x.created_at, reverse=True)

        return conv_memories[:num_memories]

    def get_project_memories(self) -> List[MemoryNode]:
        """Get all project memories"""
        return [
            node for node in self.nodes.values()
            if node.type == MemoryType.PROJECT
        ]

    def get_trade_history(self) -> List[MemoryNode]:
        """Get all trade memories for analysis"""
        return [
            node for node in self.nodes.values()
            if node.type == MemoryType.TRADE
        ]

    def infer_connections(self, node_id: str) -> List[Tuple[str, float]]:
        """
        Find all connections for a memory.

        Returns list of (related_id, connection_strength)
        """
        if node_id not in self.nodes:
            return []

        node = self.nodes[node_id]
        connections = []

        # Find similar memories
        for other_id, other_node in self.nodes.items():
            if other_id == node_id:
                continue

            similarity = self.embedding_engine.similarity(node.embedding, other_node.embedding)
            if similarity > 0.3:  # Threshold
                connections.append((other_id, similarity))

        # Sort by strength
        connections.sort(key=lambda x: x[1], reverse=True)
        return connections

    def summarize_memory(self, node_id: str) -> Dict:
        """Get summary of a memory with context"""
        if node_id not in self.nodes:
            return {}

        node = self.nodes[node_id]
        connections = self.infer_connections(node_id)

        return {
            "id": node.id,
            "type": node.type.value,
            "content": node.content,
            "importance": node.importance,
            "created": node.created_at,
            "connections": [
                {
                    "id": conn_id,
                    "content": self.nodes[conn_id].content,
                    "strength": strength
                }
                for conn_id, strength in connections[:3]
            ]
        }

    def _find_related_memories(self, embedding: List[float], top_k: int = 5) -> List[str]:
        """Find memories similar to given embedding"""
        similarities = []

        for node_id, node in self.nodes.items():
            similarity = self.embedding_engine.similarity(embedding, node.embedding)
            if similarity > 0.2:  # Threshold
                similarities.append((node_id, similarity))

        # Sort and return top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [node_id for node_id, _ in similarities[:top_k]]

    def _generate_id(self, content: str) -> str:
        """Generate unique ID for memory"""
        hash_obj = hashlib.md5(content.encode())
        return f"mem_{hash_obj.hexdigest()[:8]}"

    def _save_to_disk(self):
        """Persist memory graph to disk.

        Writes to a per-call-unique temp file, verifies it round-trips as
        valid JSON, and only then os.replace()s it into place -- writing
        self.storage_path directly, and even a naive write-tmp-then-replace,
        both left a truncated, unparseable file in practice (reproduced
        several times: the write is cut off mid-value with no exception
        raised and nothing logged, so it isn't a crash this code can catch
        -- storage_path lives inside a live-synced OneDrive folder, which is
        the leading suspect for something outside this process's control
        interrupting the write). Rather than depend on root-causing that,
        this makes it structurally impossible for a bad write to ever reach
        the live file: a tmp file that doesn't parse back is discarded and
        the previous, still-valid storage_path is left untouched, so
        _load_from_disk can never again silently see "0 memories" because a
        write got cut short."""
        tmp_path = f"{self.storage_path}.{uuid.uuid4().hex}.tmp"
        try:
            data = {
                "nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self.nodes.items()
                }
            }

            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2)

            with open(tmp_path, 'r') as f:
                json.load(f)  # verify before replacing -- see docstring

            os.replace(tmp_path, self.storage_path)
            logger.debug(f"Saved {len(self.nodes)} memories to disk")
        except Exception as e:
            logger.error(f"Failed to save memory graph, previous file left untouched: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _load_from_disk(self):
        """Load memory graph from disk"""
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            for node_id, node_data in data.get("nodes", {}).items():
                node_type = MemoryType(node_data['type'])
                node = MemoryNode(
                    id=node_data['id'],
                    type=node_type,
                    content=node_data['content'],
                    embedding=node_data['embedding'],
                    metadata=node_data['metadata'],
                    links=node_data.get('links', []),
                    importance=node_data.get('importance', 0.5),
                    created_at=node_data.get('created_at')
                )
                self.nodes[node_id] = node

            logger.info(f"Loaded {len(self.nodes)} memories from disk")
        except FileNotFoundError:
            logger.info("No existing memory graph found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load memory graph: {e}")


# Example usage
if __name__ == "__main__":
    graph = MemoryGraph()

    # Add some memories
    graph.add_memory(
        "Working on Roxan ERP system backend",
        MemoryType.PROJECT,
        {"status": "in_progress", "team": ["dev1", "dev2"]},
        importance=0.8
    )

    graph.add_memory(
        "EUR/USD showing bullish momentum",
        MemoryType.TRADE,
        {"pair": "EUR/USD", "direction": "bullish"},
        importance=0.7
    )

    # Query memories
    results = graph.query("What projects am I working on?")
    print(f"Found {len(results)} related memories")

    for result in results:
        print(f"- {result.type.value}: {result.content[:50]}...")

