"""Multi-profile speaker identification for household members -- lets
Billion tell WHICH household member is currently speaking, so a turn's
memory context/extraction can go to that person's own profile instead of
one shared graph. Reuses voice_id.py's exact real MFCC-embedding approach
(same lightweight, non-forensic-grade method, same honesty about its
limits) via its private _embed() helper -- deliberately not a new
embedding pipeline, just keyed by profile id instead of a single enrolled
user.

Fully additive and separate from voice_id.py's own single-profile
enroll/verify, which remains untouched and is what actually gates sensitive
tool approvals (see main_new.py's _request_approval/_voice_mismatch) --
that stays a security signal. This module is a personalization signal: a
false positive here means a turn's memory gets attributed to the wrong
household member, never a bypassed approval, so its identification
threshold is intentionally looser than voice_id's.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from voice_id import TARGET_SAMPLE_RATE, _embed

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent / "data" / "household_voice_profiles"
DEFAULT_IDENTIFY_THRESHOLD = 0.75


def enroll_member(profile_id: str, pcm_float32: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> Dict[str, Any]:
    embedding = _embed(pcm_float32, sample_rate)
    if embedding is None:
        return {"success": False, "error": "Audio sample too short or silent to enroll -- need at least ~1-2 real seconds of clear speech."}
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    (PROFILES_DIR / f"{profile_id}.json").write_text(json.dumps({"embedding": embedding.tolist()}), encoding="utf-8")
    return {"success": True}


def remove_member(profile_id: str) -> None:
    path = PROFILES_DIR / f"{profile_id}.json"
    if path.exists():
        path.unlink()


def identify_speaker(
    pcm_float32: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE, threshold: float = DEFAULT_IDENTIFY_THRESHOLD,
) -> Optional[Tuple[str, float]]:
    """Returns (profile_id, similarity) for the best-matching enrolled
    household member above `threshold`, or None if nobody's enrolled, the
    clip's too short/silent to embed, or no enrolled profile matches well
    enough to be worth attributing this turn to them."""
    if not PROFILES_DIR.exists():
        return None
    embedding = _embed(pcm_float32, sample_rate)
    if embedding is None:
        return None
    best_id: Optional[str] = None
    best_similarity = -1.0
    for path in PROFILES_DIR.glob("*.json"):
        try:
            stored = np.array(json.loads(path.read_text(encoding="utf-8"))["embedding"], dtype=np.float32)
        except Exception:
            continue
        similarity = float(np.dot(embedding, stored))
        if similarity > best_similarity:
            best_id, best_similarity = path.stem, similarity
    if best_id is not None and best_similarity >= threshold:
        return best_id, round(best_similarity, 3)
    return None
