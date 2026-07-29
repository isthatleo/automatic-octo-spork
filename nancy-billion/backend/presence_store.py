"""Real LAN-based presence detection -- no new hardware, no companion app.
A household member registers their own device once (phone, laptop -- by
hostname or IP, e.g. their phone's LAN address or mDNS hostname); a real
periodic ICMP ping (network_tools.ping_host, confirmed live that this
container genuinely reaches real LAN IPs, not just Docker's internal
network) determines whether that device is currently reachable, as a real
(if imperfect -- a phone can sleep its WiFi radio, a laptop can be
suspended) proxy for "is this person home/at their desk right now." Same
class of technique real home-automation presence trackers use (e.g. Home
Assistant's ping-based device_tracker) -- honest about being a network
reachability signal, not a biometric or GPS-precise location.
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

STORE_PATH = Path(__file__).parent / "data" / "presence_devices.json"


@dataclass
class KnownDevice:
    id: str
    person_name: str
    host: str  # hostname or IP to ping
    present: bool = False
    last_seen_at: Optional[float] = None
    last_checked_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    # Real presence-triggered scene macros -- the actual "if I'm home, dim
    # the lights" conditional fusion, finally buildable now that presence
    # is a real signal instead of a manual declaration. Both optional; a
    # saved macro's own name (see macro_store.py), run via main_new.py's
    # existing _run_macro on a real arrive/leave transition.
    on_arrive_macro: Optional[str] = None
    on_leave_macro: Optional[str] = None

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PresenceStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._devices: Dict[str, KnownDevice] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for d in raw:
                dev = KnownDevice(**d)
                self._devices[dev.id] = dev
        except Exception:
            logger.exception("Failed to load presence_devices.json -- starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(d) for d in self._devices.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[KnownDevice]:
        return sorted(self._devices.values(), key=lambda d: d.person_name.lower())

    def get(self, device_id: str) -> Optional[KnownDevice]:
        return self._devices.get(device_id)

    def create(
        self, person_name: str, host: str,
        on_arrive_macro: Optional[str] = None, on_leave_macro: Optional[str] = None,
    ) -> KnownDevice:
        if not person_name.strip() or not host.strip():
            raise ValueError("person_name and host must not be empty.")
        device = KnownDevice(
            id=uuid.uuid4().hex[:12], person_name=person_name.strip(), host=host.strip(),
            on_arrive_macro=on_arrive_macro, on_leave_macro=on_leave_macro,
        )
        self._devices[device.id] = device
        self._save()
        return device

    def delete(self, device_id: str) -> bool:
        if device_id not in self._devices:
            return False
        del self._devices[device_id]
        self._save()
        return True

    def record_check(self, device_id: str, present: bool) -> None:
        device = self._devices.get(device_id)
        if device is None:
            return
        device.last_checked_at = time.time()
        if present:
            device.last_seen_at = device.last_checked_at
        device.present = present
        self._save()

    def who_is_present(self) -> List[str]:
        """Real distinct list of person_names with at least one currently-
        reachable registered device -- the actual answer to "who's home"."""
        names = {d.person_name for d in self._devices.values() if d.present}
        return sorted(names)


presence_store = PresenceStore()
