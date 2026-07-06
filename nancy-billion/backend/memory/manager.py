"""
Memory Manager - Integration layer between Context and Memory Graph

Handles:
- Converting conversation context to memories
- Retrieving memories for augmented responses
- Learning from conversation patterns
- Cross-session memory access
"""

import logging
from typing import Dict, List, Optional
from memory.graph import MemoryGraph, MemoryType, MemoryNode
from context_manager import ContextManager

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Manages Nancy's memory system.

    Bridges context manager with memory graph for:
    - Automatic memory extraction from conversations
    - Context-augmented responses
    - Learning and pattern detection
    - Long-term knowledge building
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.graph = MemoryGraph()
        self.context: Optional[ContextManager] = None
        self.last_extracted_ids = []

    def set_context_manager(self, context: ContextManager):
        """Link with context manager"""
        self.context = context

    def extract_memories_from_conversation(self) -> List[MemoryNode]:
        """
        Extract important facts as memories from conversation.

        Identifies:
        - Projects mentioned
        - Decisions made
        - Important facts
        - Trading activities
        """
        if not self.context:
            return []

        memories = []
        history = self.context.get_recent_context(max_messages=10)

        for msg in history:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Extract memories from user messages
            if role == "user":
                # Check for project mentions
                if any(x in content.lower() for x in ["working on", "project", "building", "developing"]):
                    node = self.graph.add_memory(
                        content,
                        MemoryType.PROJECT,
                        {"source": "conversation", "role": role},
                        importance=0.7
                    )
                    memories.append(node)

                # Check for trading activity
                if any(x in content.lower() for x in ["trade", "buy", "sell", "forex", "eur/usd"]):
                    node = self.graph.add_memory(
                        content,
                        MemoryType.TRADE,
                        {"source": "conversation"},
                        importance=0.8
                    )
                    memories.append(node)

                # Check for decisions
                if any(x in content.lower() for x in ["decided", "decided to", "will", "planning to"]):
                    node = self.graph.add_memory(
                        content,
                        MemoryType.DECISION,
                        {"source": "conversation"},
                        importance=0.6
                    )
                    memories.append(node)

            # Store conversation snippets
            if content.strip():
                node = self.graph.add_memory(
                    content,
                    MemoryType.CONVERSATION,
                    {"source": role, "timestamp": msg.get("timestamp")},
                    importance=0.3
                )
                memories.append(node)

        self.last_extracted_ids = [m.id for m in memories]
        logger.info(f"Extracted {len(memories)} memories from conversation")
        return memories

    def get_relevant_memories(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Get memories relevant to query.

        Returns formatted memories for LLM context.
        """
        memories = self.graph.query(query, top_k=top_k)

        formatted = [
            {
                "type": mem.type.value,
                "content": mem.content,
                "importance": mem.importance,
                "related": len(mem.links)
            }
            for mem in memories
        ]

        logger.debug(f"Retrieved {len(formatted)} relevant memories")
        return formatted

    def get_memory_context_string(self, query: str, max_memories: int = 5) -> str:
        """
        Get formatted string of relevant memories for LLM prompt.

        Example:
        "Previous memories about your projects:
        - Working on Roxan ERP backend
        - Completed Docker integration"
        """
        memories = self.graph.query(query, top_k=max_memories)

        if not memories:
            return ""

        lines = ["# Previous memories relevant to your question:\n"]

        for mem in memories:
            lines.append(f"- ({mem.type.value}) {mem.content[:80]}")

        return "\n".join(lines)

    def get_project_context(self) -> List[Dict]:
        """Get all active projects for context"""
        projects = self.graph.get_project_memories()

        return [
            {
                "content": p.content,
                "importance": p.importance,
                "created": p.created_at,
                "connections": len(p.links)
            }
            for p in projects
        ]

    def get_trade_history(self, limit: int = 20) -> List[Dict]:
        """Get trade history for analysis"""
        trades = self.graph.get_trade_history()[-limit:]

        return [
            {
                "content": t.content,
                "created": t.created_at,
                "importance": t.importance
            }
            for t in trades
        ]

    def augment_prompt_with_memory(self, prompt: str) -> str:
        """
        Add memory context to LLM prompt.

        Transforms:
        "user: How's the project?"

        Into:
        "# Previous memories:
        - Working on Roxan ERP

        user: How's the project?"
        """
        memory_context = self.get_memory_context_string(prompt, max_memories=5)

        if memory_context:
            return f"{memory_context}\n\n{prompt}"

        return prompt

    def learn_from_response(self, user_query: str, assistant_response: str):
        """
        Learn from exchange to improve future responses.

        Stores:
        - Important facts from response
        - Follow-ups or related ideas
        """
        # Extract facts from assistant response
        if any(x in assistant_response.lower() for x in ["remember", "noted", "learned"]):
            self.graph.add_memory(
                f"Nancy learned: {assistant_response[:100]}",
                MemoryType.INSIGHT,
                {"source": "learning", "from_query": user_query[:50]},
                importance=0.5
            )

    def get_memory_summary(self) -> Dict:
        """Get summary of Nancy's memory state"""
        all_memories = self.graph.nodes

        by_type = {}
        for node in all_memories.values():
            type_name = node.type.value
            if type_name not in by_type:
                by_type[type_name] = 0
            by_type[type_name] += 1

        return {
            "total_memories": len(all_memories),
            "by_type": by_type,
            "recent_conversations": len([n for n in all_memories.values() if n.type == MemoryType.CONVERSATION]),
            "projects": len([n for n in all_memories.values() if n.type == MemoryType.PROJECT]),
            "trades": len([n for n in all_memories.values() if n.type == MemoryType.TRADE]),
        }


# Example usage
if __name__ == "__main__":
    manager = MemoryManager()

    # Simulate memory extraction
    context = ContextManager()
    context.add_message("user", "I'm working on Roxan ERP system")
    context.add_message("assistant", "Great! I'll remember that.")
    context.add_message("user", "EUR/USD is looking bullish today")

    manager.set_context_manager(context)

    # Extract and display
    memories = manager.extract_memories_from_conversation()
    print(f"Extracted {len(memories)} memories")

    # Get summary
    summary = manager.get_memory_summary()
    print(f"Memory summary: {summary}")

    # Augment prompt
    prompt = "How's my project going?"
    augmented = manager.augment_prompt_with_memory(prompt)
    print(f"Augmented prompt:\n{augmented}")

