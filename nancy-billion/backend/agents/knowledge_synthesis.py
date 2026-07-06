"""
Knowledge Synthesis Agent for Nancy Billion
Integrates and synthesizes knowledge across specialized agent outputs.
"""
from typing import Dict, Any, Optional, List
import logging
import time

logger = logging.getLogger(__name__)


class KnowledgeSynthesisAgent:
    """Knowledge Synthesis Agent - aggregates and synthesizes multi-source information"""

    def __init__(self, settings):
        self.settings = settings
        self.name = "Knowledge Synthesis Agent"
        self.domain = "knowledge-synthesis"
        self._initialized = False
        self._knowledge_base: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        logger.info("Initializing Knowledge Synthesis Agent")
        self._initialized = True

    async def synthesize(self, inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()
        if not inputs:
            return {"summary": "No inputs to synthesize", "confidence": 0.0}
        topics: Dict[str, list] = {}
        for inp in inputs:
            topic = inp.get("topic", "general")
            if topic not in topics:
                topics[topic] = []
            topics[topic].append(inp)
        synthesis = {}
        for topic, items in topics.items():
            confidences = [i.get("confidence", 0.5) for i in items if "confidence" in i]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
            key_findings = []
            for item in items:
                content = item.get("content") or item.get("result") or item.get("response") or ""
                if isinstance(content, str) and len(content) > 10:
                    key_findings.append(content[:200])
            synthesis[topic] = {
                "key_findings": key_findings[:5],
                "source_count": len(items),
                "avg_confidence": round(avg_confidence, 4),
                "timestamp": time.time()
            }
        return {
            "summary": f"Synthesized {len(inputs)} inputs across {len(topics)} topics",
            "synthesis": synthesis,
            "total_sources": len(inputs),
            "topics_covered": list(topics.keys()),
            "confidence": round(sum(s["avg_confidence"] for s in synthesis.values()) / max(len(synthesis), 1), 4)
        }

    async def integrate_knowledge(self, source: str, data: Dict[str, Any]) -> None:
        key = f"{source}_{int(time.time())}"
        self._knowledge_base[key] = {**data, "source": source, "timestamp": time.time()}
        if len(self._knowledge_base) > 1000:
            oldest = sorted(self._knowledge_base.keys(), key=lambda k: self._knowledge_base[k]["timestamp"])[:200]
            for k in oldest:
                del self._knowledge_base[k]

    async def query_knowledge(self, topic: str) -> Dict[str, Any]:
        relevant = {k: v for k, v in self._knowledge_base.items() if topic.lower() in str(v).lower()}
        return {
            "topic": topic,
            "entries_found": len(relevant),
            "entries": list(relevant.values())[-10:],
            "timestamp": time.time()
        }

    async def shutdown(self):
        logger.info("Shutting down Knowledge Synthesis Agent")
        self._initialized = False
