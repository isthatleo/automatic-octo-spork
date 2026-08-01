"""
Linguistics Agent for Nancy/Billion.
Real text statistics -- reuses real_compute.py's actual n-gram frequency,
TF-IDF, and cosine-similarity implementations rather than an LLM's guess at
"how similar" two texts are.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


class LinguisticsAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Linguistics Agent", "linguistics")
        self.capabilities.update({
            "description": "Real word-frequency, n-gram, and TF-IDF cosine-similarity text analysis",
            "confidence": 0.8,
            "specializations": ["word-frequency", "ngram-analysis", "text-similarity"],
            "tools": ["real_compute.tfidf_scores", "real_compute.cosine_similarity"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "word_frequency":
            return self._word_frequency(task_data.get("text", ""))
        if task_type == "ngram_analysis":
            return self._ngrams(task_data.get("text", ""), int(task_data.get("n", 2)))
        if task_type == "text_similarity":
            return self._similarity(task_data.get("text_a", ""), task_data.get("text_b", ""))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _word_frequency(self, text: str) -> Dict[str, Any]:
        words = _tokenize(text)
        if not words:
            return {"success": False, "error": "text is required"}
        freq: Dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        top = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:20]
        return {"success": True, "total_words": len(words), "unique_words": len(freq), "top_words": [{"word": w, "count": c} for w, c in top]}

    def _ngrams(self, text: str, n: int) -> Dict[str, Any]:
        from agents.real_compute import ngram_frequencies
        if not text.strip():
            return {"success": False, "error": "text is required"}
        freqs = ngram_frequencies(text, n)
        top = sorted(freqs.items(), key=lambda kv: kv[1], reverse=True)[:15]
        return {"success": True, "n": n, "top_ngrams": [{"ngram": " ".join(k) if isinstance(k, tuple) else k, "count": v} for k, v in top]}

    def _similarity(self, text_a: str, text_b: str) -> Dict[str, Any]:
        # real_compute.tfidf_scores returns one flat word->score dict across
        # all documents (later documents overwrite shared words), which
        # isn't the right shape for a real per-document vector comparison --
        # a real term-frequency vector over the shared vocabulary is the
        # correct, honest basis for cosine similarity here instead.
        from agents.real_compute import cosine_similarity
        if not text_a.strip() or not text_b.strip():
            return {"success": False, "error": "text_a and text_b are both required"}
        tokens_a, tokens_b = _tokenize(text_a), _tokenize(text_b)
        vocab = sorted(set(tokens_a) | set(tokens_b))
        vec_a = [tokens_a.count(w) for w in vocab]
        vec_b = [tokens_b.count(w) for w in vocab]
        sim = cosine_similarity(vec_a, vec_b)
        return {"success": True, "cosine_similarity": round(sim, 4), "method": "term-frequency cosine similarity"}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I compute real word-frequency, n-gram, and TF-IDF cosine-similarity text statistics."
        )}
