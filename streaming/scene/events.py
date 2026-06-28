"""
Event log — the DERIVED, append-only record of scene-state transitions.

Per the pivot decision, events are never authored directly by a detector; they
fall out of changes the `SceneTracker` makes to `SceneState`: an entity becomes
confirmed (entered), a confirmed entity goes missing past the grace window
(exited), an entity crosses into/out of a zone, a restricted zone is breached, a
new semantic note lands, or aggregate activity changes band.

The log is a bounded ring buffer (so an always-on stream cannot OOM) plus a
subscription hook. Tier 4 wiring (PowerSync push, dashboard, alerting) just
`subscribe()`s; it does not need to know how events are produced.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Iterable, List, Optional


class EventType(str, Enum):
    ENTITY_ENTERED = "entity_entered"
    ENTITY_EXITED = "entity_exited"
    ZONE_ENTERED = "zone_entered"
    ZONE_EXITED = "zone_exited"
    ZONE_BREACH = "zone_breach"        # entry into a RESTRICTED zone
    SEMANTIC_NOTE = "semantic_note"    # a fresh Tier-2 description
    ACTIVITY_CHANGE = "activity_change"


@dataclass(slots=True)
class Event:
    """One derived occurrence. `ts_monotonic` orders it; `ts_wall` dates it."""

    seq: int
    type: EventType
    ts_monotonic: float
    ts_wall: float
    source_id: str
    message: str                       # human-readable, e.g. "person#3 entered"
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "type": self.type.value,
            "ts_wall": self.ts_wall,
            "source_id": self.source_id,
            "message": self.message,
            "data": self.data,
        }


class EventLog:
    """Bounded, append-only event store with optional subscribers."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._events: Deque[Event] = deque(maxlen=maxlen)
        self._subscribers: List[Callable[[Event], None]] = []
        self._seq = 0

    def emit(
        self,
        type: EventType,
        ts_monotonic: float,
        source_id: str,
        message: str,
        data: Optional[dict] = None,
    ) -> Event:
        self._seq += 1
        ev = Event(
            seq=self._seq,
            type=type,
            ts_monotonic=ts_monotonic,
            ts_wall=time.time(),
            source_id=source_id,
            message=message,
            data=data or {},
        )
        self._events.append(ev)
        # A misbehaving subscriber must never take down the pipeline — isolate it.
        for cb in self._subscribers:
            try:
                cb(ev)
            except Exception:  # noqa: BLE001 — deliberately swallow downstream errors
                pass
        return ev

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """Register a sink (e.g. PowerSync push) called on every new event."""
        self._subscribers.append(callback)

    def recent(
        self,
        n: Optional[int] = None,
        types: Optional[Iterable[EventType]] = None,
    ) -> List[Event]:
        """Most-recent-last list, optionally filtered by type and count."""
        evs = list(self._events)
        if types is not None:
            wanted = set(types)
            evs = [e for e in evs if e.type in wanted]
        if n is not None:
            evs = evs[-n:]
        return evs

    def __len__(self) -> int:
        return len(self._events)
