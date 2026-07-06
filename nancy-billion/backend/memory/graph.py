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
    Simple embedding system using TF-IDF-like approach.

    In production, would use:
    - OpenAI embeddings API
    - Sentence transformers
    - Other ML models

    For now: keyword-based embedding for fast iteration
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
        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = sum(a * a for a in emb1) ** 0.5
        norm2 = sum(b * b for b in emb2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


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
        self.embedding_engine = SimpleEmbedding()
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
        self._save_to_disk()

        return node

    def query(self, query_text: str, top_k: int = 10, threshold: float = 0.3) -> List[MemoryNode]:
        """
        Find memories similar to query.

        Returns top_k most similar memories above threshold.
        """
        query_embedding = self.embedding_engine.embed(query_text)

        # Calculate similarities
        similarities = []
        for node_id, node in self.nodes.items():
            similarity = self.embedding_engine.similarity(query_embedding, node.embedding)
            if similarity >= threshold:
                similarities.append((node_id, similarity, node))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top_k nodes
        results = [node for _, _, node in similarities[:top_k]]

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
        """Persist memory graph to disk"""
        try:
            data = {
                "nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self.nodes.items()
                }
            }

            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self.nodes)} memories to disk")
        except Exception as e:
            logger.error(f"Failed to save memory graph: {e}")

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

