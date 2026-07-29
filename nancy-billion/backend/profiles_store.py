"""Household member profiles -- real scope, chosen explicitly over full
multi-tenant SaaS: a handful of known people (family/housemates) each get
their own memory context and voice identification, but there's still one
deployment, one set of API keys/credentials, and no login/auth system. A
profile is a personalization boundary, not a security/tenancy boundary --
see household_voice_id.py's own docstring for why its identification
threshold is intentionally separate from voice_id.py's actual security gate.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "profiles.json"


@dataclass
class Profile:
    id: str
    name: str
    created_at: float = field(default_factory=time.time)
    preferences: Dict[str, Any] = field(default_factory=dict)
    voice_enrolled: bool = False

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProfileStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._profiles: Dict[str, Profile] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for p in raw:
                profile = Profile(**p)
                self._profiles[profile.id] = profile
        except Exception:
            logger.exception("Failed to load profiles.json -- starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(p) for p in self._profiles.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[Profile]:
        return sorted(self._profiles.values(), key=lambda p: p.name.lower())

    def get(self, profile_id: str) -> Optional[Profile]:
        return self._profiles.get(profile_id)

    def get_by_name(self, name: str) -> Optional[Profile]:
        lowered = name.strip().lower()
        return next((p for p in self._profiles.values() if p.name.lower() == lowered), None)

    def create(self, name: str, preferences: Optional[Dict[str, Any]] = None) -> Profile:
        if not name.strip():
            raise ValueError("name must not be empty.")
        if self.get_by_name(name):
            raise ValueError(f"A profile named '{name}' already exists.")
        profile = Profile(id=uuid.uuid4().hex[:12], name=name.strip(), preferences=preferences or {})
        self._profiles[profile.id] = profile
        self._save()
        return profile

    def delete(self, profile_id: str) -> bool:
        if profile_id not in self._profiles:
            return False
        del self._profiles[profile_id]
        self._save()
        return True

    def mark_voice_enrolled(self, profile_id: str) -> None:
        profile = self._profiles.get(profile_id)
        if profile is None:
            return
        profile.voice_enrolled = True
        self._save()

    def update_preferences(self, profile_id: str, preferences: Dict[str, Any]) -> Optional[Profile]:
        profile = self._profiles.get(profile_id)
        if profile is None:
            return None
        profile.preferences.update(preferences)
        self._save()
        return profile


profile_store = ProfileStore()
