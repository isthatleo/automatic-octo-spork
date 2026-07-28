"""Real "watch this and tell me when it changes" background monitoring --
Billion's version of a price-watch/change-detector, built on the exact same
JSON-store + due-job pattern as cron_store.py/missions_store.py. Reuses
web_tool.fetch_url for the actual page fetch (SSRF-checked, real redirect
handling) rather than duplicating HTTP logic.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "watches.json"

_PRICE_RE = re.compile(r"[$£€]\s?([\d,]+\.?\d{0,2})")

VALID_KINDS = {"text", "price", "github_release"}


@dataclass
class Watch:
    id: str
    url: str
    description: str
    kind: str = "text"
    target_price: Optional[float] = None
    check_interval_minutes: float = 60.0
    # Most "watch this for me" asks mean "tell me once, then stop" -- not
    # keep alerting on the same event forever. Explicit opt-out for the
    # rarer "keep telling me every time this changes" case.
    one_shot: bool = True
    active: bool = True
    last_value: Optional[str] = None
    last_checked_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WatchStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._watches: Dict[str, Watch] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for w in raw:
                watch = Watch(**w)
                self._watches[watch.id] = watch
        except Exception:
            logger.exception("Failed to load watches.json -- starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(w) for w in self._watches.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[Watch]:
        return sorted(self._watches.values(), key=lambda w: -w.created_at)

    def get(self, watch_id: str) -> Optional[Watch]:
        return self._watches.get(watch_id)

    def create(
        self, url: str, description: str, kind: str = "text",
        target_price: Optional[float] = None, check_interval_minutes: float = 60.0,
        one_shot: bool = True,
    ) -> Watch:
        if kind not in VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
        watch = Watch(
            id=uuid.uuid4().hex[:12], url=url, description=description, kind=kind,
            target_price=target_price, check_interval_minutes=max(check_interval_minutes, 5.0),
            one_shot=one_shot,
        )
        self._watches[watch.id] = watch
        self._save()
        return watch

    def delete(self, watch_id: str) -> bool:
        if watch_id not in self._watches:
            return False
        del self._watches[watch_id]
        self._save()
        return True

    def due(self, now: Optional[float] = None) -> List[Watch]:
        now = now if now is not None else time.time()
        return [
            w for w in self._watches.values()
            if w.active and (w.last_checked_at is None or now - w.last_checked_at >= w.check_interval_minutes * 60)
        ]

    def record_check(self, watch_id: str, new_value: Optional[str], deactivate: bool = False) -> None:
        watch = self._watches.get(watch_id)
        if watch is None:
            return
        watch.last_checked_at = time.time()
        if new_value is not None:
            watch.last_value = new_value
        if deactivate:
            watch.active = False
        self._save()


watch_store = WatchStore()


def _extract_price(text: str) -> Optional[float]:
    match = _PRICE_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


async def check_watch(watch: Watch) -> Dict[str, Any]:
    """Runs one real check for a single watch. Returns whether it changed
    (or crossed target_price for "price" watches) plus a human-readable
    alert message when it did -- the caller (main_new.py's watch loop)
    handles actually sending it and updating the store."""
    if watch.kind == "github_release":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{watch.url}/releases/latest",
                    headers={"User-Agent": "nancy-billion-watch"},
                )
            if resp.status_code != 200:
                return {"success": False, "error": f"GitHub API returned {resp.status_code}"}
            tag = resp.json().get("tag_name")
        except Exception as e:
            return {"success": False, "error": str(e)}
        changed = watch.last_value is not None and tag != watch.last_value
        return {
            "success": True, "new_value": tag, "changed": changed,
            "alert": f"New release for {watch.url}: {tag}, Sir." if changed else None,
        }

    import web_tool  # local import -- avoids a hard circular import with main_new's tool wiring
    result = await web_tool.fetch_url(watch.url)
    if not result.get("success"):
        return {"success": False, "error": result.get("error")}
    text = result.get("text", "")

    if watch.kind == "price":
        price = _extract_price(text)
        if price is None:
            return {"success": False, "error": "Couldn't find a price on that page."}
        first_check_already_under = (
            watch.target_price is not None and watch.last_value is None and price <= watch.target_price
        )
        just_crossed = (
            watch.target_price is not None and watch.last_value is not None
            and float(watch.last_value) > watch.target_price >= price
        )
        crossed = first_check_already_under or just_crossed
        return {
            "success": True, "new_value": str(price), "changed": crossed,
            "alert": (
                f"Price alert, Sir: {watch.description or watch.url} is now ${price:,.2f} "
                f"(target was ${watch.target_price:,.2f})."
            ) if crossed else None,
        }

    # kind == "text": alert on any real content change, via a hash so we
    # never need to store/diff the full page text.
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    changed = watch.last_value is not None and digest != watch.last_value
    return {
        "success": True, "new_value": digest, "changed": changed,
        "alert": f"Change detected, Sir: {watch.description or watch.url} has updated." if changed else None,
    }
