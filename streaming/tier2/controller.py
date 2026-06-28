"""
Tier2Controller — runs the expensive VLM *off the critical path*, gated.

The whole point of Tier 2 is to NOT run a VLM on every frame. This controller
decides *when* to spend a ~1fps inference and keeps it from ever slowing Tier 1/3:

  * Gating = triggers OR heartbeat. A trigger-worthy Tier-1 event (a new entity,
    a zone breach, an activity-band change) marks the scene "dirty" and earns a
    semantic refresh; a heartbeat floor guarantees a refresh at least every
    `heartbeat_s` even when nothing happens, so the semantic read never goes
    silently ancient.
  * Rate cap. Never fires more often than `min_interval_s` no matter how many
    triggers arrive — that is the realistic VLM throughput on-device.
  * Off the critical path. A worker thread does the slow inference; the Tier-3
    loop only calls `offer(frame)`, which is a cheap peek-latest store. The
    worker always reasons over the *freshest* offered frame (drop-stale), so a
    slow model means fewer, fresher reads — never a growing backlog.
  * Graceful degradation. A backend failure is counted and backed off; the scene
    state simply keeps its last semantic read, flagged stale. Tier 1/3 are
    unaffected.

Results are written back into the single source of truth via
`tracker.note_semantic()`, which also derives a SEMANTIC_NOTE event.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Set

from streaming.frame import Frame
from streaming.scene.events import EventType
from streaming.scene.tracker import SceneTracker
from streaming.tier2.understanding import SceneUnderstander

logger = logging.getLogger(__name__)

# Tier-1 events that justify spending a VLM call (something semantically new).
_DEFAULT_TRIGGERS: Set[EventType] = {
    EventType.ENTITY_ENTERED,
    EventType.ZONE_ENTERED,
    EventType.ZONE_BREACH,
    EventType.ACTIVITY_CHANGE,
}


class Tier2Controller:
    def __init__(
        self,
        tracker: SceneTracker,
        understander: SceneUnderstander,
        *,
        heartbeat_s: float = 8.0,
        min_interval_s: float = 1.0,
        trigger_types: Optional[Set[EventType]] = None,
        backoff_s: float = 5.0,
    ) -> None:
        self.tracker = tracker
        self.understander = understander
        self.heartbeat_s = heartbeat_s
        self.min_interval_s = min_interval_s
        self.trigger_types = trigger_types or set(_DEFAULT_TRIGGERS)
        self.backoff_s = backoff_s

        # Peek-latest frame store (NOT the consume-based LatestFrameSlot: a
        # heartbeat must be able to re-observe the most recent frame even if no
        # newer one has arrived since the last read).
        self._lock = threading.Lock()
        self._latest: Optional[Frame] = None
        self._offered_since_run = 0

        self._dirty_since: Optional[float] = None   # monotonic ts of oldest pending trigger
        # -inf = "never run, infinitely overdue" → the first tick always produces
        # an initial semantic read instead of waiting a full heartbeat.
        self._last_run = float("-inf")
        self._fail_streak = 0
        self._cooldown_until = 0.0

        # Observability
        self.runs = 0
        self.failures = 0
        self.dropped_frames = 0

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # Triggers come straight off the derived event log.
        self.tracker.events.subscribe(self._on_event)

    # -- inputs ------------------------------------------------------------
    def offer(self, frame: Frame) -> None:
        """Cheap: store the freshest frame for the worker. Called every Tier-3 tick."""
        with self._lock:
            if self._latest is not None:
                self.dropped_frames += 1
            self._latest = frame
            self._offered_since_run += 1

    def _on_event(self, event) -> None:
        if event.type in self.trigger_types and self._dirty_since is None:
            self._dirty_since = event.ts_monotonic

    # -- policy (pure, unit-testable) -------------------------------------
    def _should_run(self, now: float) -> bool:
        if now < self._cooldown_until:
            return False
        if (now - self._last_run) < self.min_interval_s:
            return False
        if self._dirty_since is not None:
            return True                       # a trigger is pending
        return (now - self._last_run) >= self.heartbeat_s   # heartbeat floor

    def _context_text(self) -> str:
        """Compact, token-cheap summary of current scene state for the prompt."""
        st = self.tracker.state
        counts: dict[str, int] = {}
        for e in st.confirmed_entities():
            counts[e.label] = counts.get(e.label, 0) + 1
        objs = ", ".join(f"{n} {lbl}" for lbl, n in sorted(counts.items())) or "nothing tracked"
        occ = {k: len(v) for k, v in st.zone_occupancy.items() if v}
        zones = f"; zones: {occ}" if occ else ""
        return f"{objs}; activity: {st.activity_label}{zones}"

    # -- execution ---------------------------------------------------------
    def _run_once(self, now: float) -> bool:
        with self._lock:
            frame = self._latest
            offered = self._offered_since_run
        if frame is None:
            return False                      # nothing to look at yet
        # Claim this run window now so triggers arriving mid-inference re-arm
        # for the *next* run rather than being lost or double-counted.
        self._last_run = now
        self._dirty_since = None
        with self._lock:
            self._offered_since_run = 0

        context = self._context_text()
        obs = self.understander.observe(frame, context)
        self.runs += 1
        if obs.ok:
            self._fail_streak = 0
            self.tracker.note_semantic(obs.text, ts_monotonic=frame.ts_monotonic, source=obs.source)
        else:
            self.failures += 1
            self._fail_streak += 1
            # Exponential-ish backoff so a wedged backend doesn't busy-loop.
            self._cooldown_until = now + self.backoff_s * min(self._fail_streak, 6)
            logger.warning("Tier 2 backend failed (streak=%d): %s", self._fail_streak, obs.text)
        return True

    def tick(self, now: Optional[float] = None) -> bool:
        """One scheduling step: run the VLM iff policy allows. Returns whether it ran."""
        now = time.monotonic() if now is None else now
        if not self._should_run(now):
            return False
        return self._run_once(now)

    # -- worker thread -----------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="tier2", daemon=True)
        self._thread.start()
        logger.info("Tier 2 started (%s, heartbeat=%.1fs, min_interval=%.1fs)",
                    self.understander.name, self.heartbeat_s, self.min_interval_s)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 — worker must never die
                logger.exception("Tier 2 tick crashed (continuing): %s", exc)
            # Poll cadence: fine-grained enough to honour min_interval/heartbeat
            # without busy-spinning. The inference itself dominates wall time.
            self._stop.wait(0.1)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
