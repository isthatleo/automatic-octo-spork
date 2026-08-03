"""Live per-subsystem activity levels -- the real signal Book VI Ch.7 needs.

Book VI Ch.7 assigns each Orb ring a specific subsystem (health, memory,
knowledge, agent, reasoning, network) and Ch.3's Purpose principle forbids
decorative elements outright: "every pixel communicates information." The
Orb had rings, but nothing to bind them to, so they animated on fixed
timers -- decoration by the book's own definition, and Ch.24 says remove
anything that doesn't communicate state.

This module is that missing signal. Every level here is derived from
something that actually happened: a real agent task, a real memory write, a
real LLM call. Nothing is simulated, because a ring driven by a fake number
would satisfy the letter of Ch.7 while violating its point.

Levels decay toward zero over ACTIVITY_HALFLIFE_S, so the Orb shows genuine
recent activity rather than a cumulative counter that only ever climbs.
"""

from __future__ import annotations

import math
import time
from typing import Dict

#: Book VI Ch.7's six rings, in ring order.
SUBSYSTEMS = ("health", "memory", "knowledge", "agent", "reasoning", "network")

#: How quickly an activity level falls back to rest. Short enough that the
#: Orb reads as "what is happening now" rather than "what happened today".
ACTIVITY_HALFLIFE_S = 8.0


class SubsystemActivity:
    """Rolling, decaying activity level per subsystem.

    Deliberately dependency-free and synchronous -- it is poked from hot
    paths (every agent task, every memory write) and must never add latency
    or import weight to them.
    """

    def __init__(self) -> None:
        self._level: Dict[str, float] = {name: 0.0 for name in SUBSYSTEMS}
        self._touched: Dict[str, float] = {name: 0.0 for name in SUBSYSTEMS}

    def poke(self, subsystem: str, amount: float = 1.0) -> None:
        """Record a DISCRETE event (an agent task, a memory write, an LLM
        call). Accumulates and saturates, so a burst pins the ring at full
        rather than overflowing, then decays back.

        Use set_level() for continuous conditions -- accumulating those
        produces a ring that climbs simply because time passed. Confirmed
        live: health was poked at 0.04 twice a second while perfectly
        healthy and reached 0.65, so the health ring glowed brightest when
        nothing was wrong, inverting its meaning (a Book VI Ch.24 failure --
        a visual that misreports state is worse than none)."""
        if subsystem not in self._level:
            return
        now = time.time()
        self._level[subsystem] = min(1.0, self._decayed(subsystem, now) + amount)
        self._touched[subsystem] = now

    def set_level(self, subsystem: str, value: float) -> None:
        """Report a CONTINUOUS condition (system health, connected clients).
        Replaces rather than accumulates, so the ring reflects the condition
        as it currently is."""
        if subsystem not in self._level:
            return
        self._level[subsystem] = max(0.0, min(1.0, float(value)))
        self._touched[subsystem] = time.time()

    def _decayed(self, subsystem: str, now: float) -> float:
        last = self._touched.get(subsystem, 0.0)
        if not last:
            return 0.0
        elapsed = now - last
        return self._level[subsystem] * math.pow(0.5, elapsed / ACTIVITY_HALFLIFE_S)

    def snapshot(self) -> Dict[str, float]:
        """Current decayed levels, 0.0-1.0, for broadcast to the Orb."""
        now = time.time()
        return {name: round(self._decayed(name, now), 3) for name in SUBSYSTEMS}

    def is_quiet(self) -> bool:
        """True when nothing is meaningfully active -- lets the Orb settle
        into Book VI Ch.10's Idle/Sleep states honestly."""
        return all(v < 0.02 for v in self.snapshot().values())


subsystem_activity = SubsystemActivity()
