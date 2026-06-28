"""
The sync layer — fan out live scene state + events to any number of clients.

This is the "Tier 4" seam the lower tiers were built toward. A `StateSink` is any
destination for live updates (a browser dashboard, a Postgres table PowerSync
syncs, a robot planner, a logger). `SinkHub` fans out to several at once with
per-sink error isolation. `StatePublisher` is the single driver that wires the
scene graph to the hub.

Threading model (deliberate): the publisher snapshots and forwards events **on
the pipeline thread** — `on_event` fires from the tracker during update(), and
`tick()` is called from the run loop. That means we never read `SceneState` from
a second thread while Tier 1 is mutating it (no torn reads / "dict changed size"
races). Sinks that need their own threads (a web server, a DB writer) own only
their *own* buffers, which `on_event`/`on_snapshot` must fill cheaply and without
blocking.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

from streaming.scene.events import Event
from streaming.scene.tracker import SceneTracker

logger = logging.getLogger(__name__)


class StateSink(ABC):
    """A destination for live scene updates. Methods must be cheap & non-blocking."""

    @abstractmethod
    def on_event(self, event: Event) -> None:
        """A new derived event. Buffer it; do not block the pipeline."""

    @abstractmethod
    def on_snapshot(self, snapshot: dict) -> None:
        """A fresh full scene snapshot (JSON-ready dict). Buffer it."""

    def close(self) -> None:  # optional
        """Release resources (stop servers, flush writers)."""


class SinkHub(StateSink):
    """Fans out to several sinks; one misbehaving sink never affects the others."""

    def __init__(self, sinks: Optional[Sequence[StateSink]] = None) -> None:
        self._sinks: List[StateSink] = list(sinks or [])

    def add(self, sink: StateSink) -> "SinkHub":
        self._sinks.append(sink)
        return self

    def on_event(self, event: Event) -> None:
        for s in self._sinks:
            try:
                s.on_event(event)
            except Exception:  # noqa: BLE001 — a bad sink must not break the pipeline
                logger.exception("sink %s on_event failed", type(s).__name__)

    def on_snapshot(self, snapshot: dict) -> None:
        for s in self._sinks:
            try:
                s.on_snapshot(snapshot)
            except Exception:  # noqa: BLE001
                logger.exception("sink %s on_snapshot failed", type(s).__name__)

    def close(self) -> None:
        for s in self._sinks:
            try:
                s.close()
            except Exception:  # noqa: BLE001
                logger.exception("sink %s close failed", type(s).__name__)


class StatePublisher:
    """Wires a SceneTracker to a sink (or hub): forwards events live and emits
    full snapshots on a cadence. Driven by the pipeline thread — call `tick()`
    each loop iteration; events forward themselves via the tracker subscription."""

    def __init__(
        self,
        tracker: SceneTracker,
        sink: StateSink,
        *,
        snapshot_interval_s: float = 0.5,
    ) -> None:
        self.tracker = tracker
        self.sink = sink
        self.snapshot_interval_s = snapshot_interval_s
        self._last_snapshot = float("-inf")
        self.snapshots_sent = 0
        tracker.events.subscribe(self.sink.on_event)

    def tick(self, now: float) -> bool:
        """Emit a snapshot if the interval has elapsed. Returns whether it did."""
        if (now - self._last_snapshot) < self.snapshot_interval_s:
            return False
        self._last_snapshot = now
        snap = self.tracker.state.snapshot(self.tracker.semantic_ttl_seconds)
        self.sink.on_snapshot(snap)
        self.snapshots_sent += 1
        return True

    def close(self) -> None:
        self.sink.close()
