"""
Psychometrics Agent for Nancy/Billion.
Real Flesch Reading Ease scoring (the actual published formula, computed
from real syllable/word/sentence counts) and a basic lexicon-based sentiment
heuristic -- honestly labeled as a simple heuristic, not a trained model.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

_VOWELS = "aeiouy"
_POSITIVE_WORDS = {
    "good", "great", "excellent", "happy", "love", "wonderful", "amazing", "fantastic",
    "positive", "success", "successful", "improve", "improved", "best", "brilliant",
    "helpful", "pleased", "excited", "impressive", "outstanding", "beneficial",
}
_NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "sad", "hate", "horrible", "worst", "fail", "failed",
    "failure", "negative", "problem", "issue", "broken", "wrong", "disappointing",
    "poor", "difficult", "concerning", "worse", "frustrated", "angry",
}


def _count_syllables(word: str) -> int:
    word = word.lower()
    count, prev_was_vowel = 0, False
    for ch in word:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


class PsychometricsAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Psychometrics Agent", "psychometrics")
        self.capabilities.update({
            "description": "Real Flesch Reading Ease scoring from actual text, plus a basic lexicon sentiment heuristic (honestly not a trained model)",
            "confidence": 0.75,
            "specializations": ["readability-scoring", "sentiment-heuristic"],
            "tools": ["flesch-reading-ease"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "readability":
            return self._readability(task_data.get("text", ""))
        if task_type == "sentiment":
            return self._sentiment(task_data.get("text", ""))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _readability(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"success": False, "error": "text is required"}
        sentences = max(1, len(re.findall(r"[.!?]+", text)))
        words = re.findall(r"[A-Za-z']+", text)
        word_count = max(1, len(words))
        syllable_count = sum(_count_syllables(w) for w in words)
        score = 206.835 - 1.015 * (word_count / sentences) - 84.6 * (syllable_count / word_count)
        score = round(score, 1)
        if score >= 90:
            level = "very easy (5th grade)"
        elif score >= 70:
            level = "easy/plain English"
        elif score >= 50:
            level = "fairly difficult"
        elif score >= 30:
            level = "difficult (college level)"
        else:
            level = "very difficult (graduate level)"
        return {"success": True, "flesch_reading_ease": score, "reading_level": level, "word_count": word_count, "sentence_count": sentences}

    def _sentiment(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"success": False, "error": "text is required"}
        words = re.findall(r"[A-Za-z']+", text.lower())
        pos = sum(1 for w in words if w in _POSITIVE_WORDS)
        neg = sum(1 for w in words if w in _NEGATIVE_WORDS)
        total = pos + neg
        polarity = (pos - neg) / total if total else 0.0
        label = "positive" if polarity > 0.2 else "negative" if polarity < -0.2 else "neutral"
        return {
            "success": True, "polarity": round(polarity, 3), "label": label,
            "positive_word_hits": pos, "negative_word_hits": neg,
            "method": "basic lexicon-word-count heuristic -- not a trained sentiment model, treat as a rough signal only",
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I compute a real Flesch Reading Ease score from actual text, and a basic lexicon sentiment heuristic."
        )}
