"""
SceneTracker — turns a stream of Tier-1 DetectionResults into living scene
state, and derives an event log from the transitions.

One tracker owns one stream's `SceneState` (per-stream isolation: one crashing
stream must not corrupt another's world). Each `update(result)`:

  1. matches detections to existing entities by track id;
  2. debounces lifecycle — a new id is TENTATIVE until it has persisted for
     `confirm_seconds`, and a vanished entity is only declared gone after
     `exit_grace_seconds`. This absorbs ByteTrack id flicker so the event log
     stays clean (robustness-first: no spurious enter/exit storms);
  3. updates per-entity motion and zone membership, emitting zone events;
  4. recomputes a smoothed scene-wide activity level.

Semantic ('what is happening') text is injected separately by Tier 2 via
`note_semantic`; the tracker stores it and tracks staleness but never blocks on
it — if Tier 2 is down, geometric state stays fully live.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from streaming.detection import DetectionResult
from streaming.scene.events import EventLog, EventType
from streaming.scene.state import Entity, EntityStatus, SceneState
from streaming.scene.zones import Zone, ZoneKind

# Activity bands, in frame-fractions/sec of the mean confirmed-entity center
# speed (1.0 == an object crossing the whole frame in one second). Tuned for
# people/vehicles; exposed as constants so they are easy to retune per source.
_ACTIVITY_BANDS = (
    (0.02, "idle"),
    (0.08, "low"),
    (0.20, "medium"),
)
_ACTIVITY_HIGH = "high"


def _anchor_point(bbox, anchor: str) -> tuple[float, float]:
    """Pixel anchor used for zone membership. Default 'bottom_center' is the
    ground-contact point — the right notion of 'standing in a zone' for people
    and vehicles, far better than the box center which floats mid-body."""
    x1, y1, x2, y2 = bbox
    if anchor == "center":
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    # bottom_center
    return ((x1 + x2) / 2.0, y2)


class SceneTracker:
    def __init__(
        self,
        source_id: str,
        zones: Optional[Sequence[Zone]] = None,
        *,
        confirm_seconds: float = 0.3,
        exit_grace_seconds: float = 1.5,
        anchor: str = "bottom_center",
        semantic_ttl_seconds: float = 10.0,
        activity_smoothing: float = 0.3,   # EMA alpha for scene activity
        event_log: Optional[EventLog] = None,
    ) -> None:
        self.source_id = source_id
        self.zones: List[Zone] = list(zones or [])
        self.confirm_seconds = confirm_seconds
        self.exit_grace_seconds = exit_grace_seconds
        self.anchor = anchor
        self.semantic_ttl_seconds = semantic_ttl_seconds
        self.activity_smoothing = activity_smoothing

        self.events = event_log or EventLog()
        self.state = SceneState(source_id=source_id)
        for z in self.zones:
            self.state.zone_occupancy.setdefault(z.name, set())

    # ------------------------------------------------------------------ update
    def update(self, result: DetectionResult) -> SceneState:
        now = result.ts_monotonic
        st = self.state
        st.frame_seq = result.frame_seq
        st.last_update_monotonic = now
        if result.frame_width and result.frame_height:
            st.frame_width = result.frame_width
            st.frame_height = result.frame_height

        seen_ids: set[int] = set()
        for det in result.detections:
            if det.track_id is None:
                # Untracked detection — cannot maintain identity/lifecycle for it.
                continue
            seen_ids.add(det.track_id)
            entity = st.entities.get(det.track_id)
            if entity is None:
                entity = self._spawn(det, now)
                st.entities[det.track_id] = entity
            else:
                self._touch(entity, det, now)

            self._maybe_confirm(entity, now)
            self._update_zones(entity)

        self._reap_missing(seen_ids, now)
        self._update_activity(now)
        return st

    # --------------------------------------------------------------- lifecycle
    def _spawn(self, det, now: float) -> Entity:
        import time as _time

        e = Entity(
            track_id=det.track_id,
            label=det.label,
            class_id=det.class_id,
            confidence=det.confidence,
            bbox=det.bbox,
            status=EntityStatus.TENTATIVE,
            first_seen_monotonic=now,
            last_seen_monotonic=now,
            first_seen_wall=_time.time(),
        )
        self._push_center(e, det, now)
        return e

    def _touch(self, e: Entity, det, now: float) -> None:
        e.bbox = det.bbox
        e.confidence = det.confidence
        e.last_seen_monotonic = now
        e.hits += 1
        # A track id can be reassigned by the detector to a different class as
        # the box settles; trust the latest label.
        e.label = det.label
        e.class_id = det.class_id
        self._push_center(e, det, now)

    def _maybe_confirm(self, e: Entity, now: float) -> None:
        if e.status is EntityStatus.TENTATIVE and (now - e.first_seen_monotonic) >= self.confirm_seconds:
            e.status = EntityStatus.CONFIRMED
            self.events.emit(
                EventType.ENTITY_ENTERED,
                now,
                self.source_id,
                f"{e.label}#{e.track_id} entered",
                {"track_id": e.track_id, "label": e.label},
            )

    def _reap_missing(self, seen_ids: set[int], now: float) -> None:
        for tid in list(self.state.entities.keys()):
            if tid in seen_ids:
                continue
            e = self.state.entities[tid]
            if (now - e.last_seen_monotonic) <= self.exit_grace_seconds:
                continue  # still within grace — assume transient miss, keep it
            # Past grace: it is really gone.
            if e.status is EntityStatus.CONFIRMED:
                # Clean zone occupancy silently (entity_exited subsumes it), then
                # announce departure.
                for zname in e.zones:
                    self.state.zone_occupancy.get(zname, set()).discard(tid)
                self.events.emit(
                    EventType.ENTITY_EXITED,
                    now,
                    self.source_id,
                    f"{e.label}#{e.track_id} left",
                    {"track_id": e.track_id, "label": e.label,
                     "dwell_seconds": round(now - e.first_seen_monotonic, 2)},
                )
            del self.state.entities[tid]

    # -------------------------------------------------------------------- zones
    def _update_zones(self, e: Entity) -> None:
        if not self.zones or not self.state.frame_width or not self.state.frame_height:
            return
        ax, ay = _anchor_point(e.bbox, self.anchor)
        nx = ax / self.state.frame_width
        ny = ay / self.state.frame_height
        current = {z.name for z in self.zones if z.contains(nx, ny)}

        entered = current - e.zones
        exited = e.zones - current
        confirmed = e.status is EntityStatus.CONFIRMED

        for zname in entered:
            self.state.zone_occupancy.setdefault(zname, set())
            if confirmed:
                self.state.zone_occupancy[zname].add(e.track_id)
            zone = self._zone(zname)
            if confirmed:
                if zone and zone.kind is ZoneKind.RESTRICTED:
                    self.events.emit(
                        EventType.ZONE_BREACH, e.last_seen_monotonic, self.source_id,
                        f"{e.label}#{e.track_id} breached restricted zone {zname!r}",
                        {"track_id": e.track_id, "label": e.label, "zone": zname},
                    )
                else:
                    self.events.emit(
                        EventType.ZONE_ENTERED, e.last_seen_monotonic, self.source_id,
                        f"{e.label}#{e.track_id} entered zone {zname!r}",
                        {"track_id": e.track_id, "label": e.label, "zone": zname},
                    )
        for zname in exited:
            self.state.zone_occupancy.get(zname, set()).discard(e.track_id)
            if confirmed:
                self.events.emit(
                    EventType.ZONE_EXITED, e.last_seen_monotonic, self.source_id,
                    f"{e.label}#{e.track_id} left zone {zname!r}",
                    {"track_id": e.track_id, "label": e.label, "zone": zname},
                )
        e.zones = current

    def _zone(self, name: str) -> Optional[Zone]:
        for z in self.zones:
            if z.name == name:
                return z
        return None

    # ------------------------------------------------------------------ motion
    def _push_center(self, e: Entity, det, now: float) -> None:
        if not self.state.frame_width or not self.state.frame_height:
            return
        cx, cy = det.center
        e._centers.append((now, cx / self.state.frame_width, cy / self.state.frame_height))
        if len(e._centers) >= 2:
            t0, x0, y0 = e._centers[0]
            t1, x1, y1 = e._centers[-1]
            dt = t1 - t0
            if dt > 1e-3:
                inst = math.hypot(x1 - x0, y1 - y0) / dt
                # Per-entity EMA so a single jumpy frame does not spike speed.
                e.speed = 0.5 * e.speed + 0.5 * inst

    def _update_activity(self, now: float) -> None:
        confirmed = self.state.confirmed_entities()
        raw = (sum(e.speed for e in confirmed) / len(confirmed)) if confirmed else 0.0
        a = self.activity_smoothing
        self.state.activity_level = (1 - a) * self.state.activity_level + a * raw

        label = _ACTIVITY_HIGH
        for threshold, name in _ACTIVITY_BANDS:
            if self.state.activity_level < threshold:
                label = name
                break
        if label != self.state.activity_label:
            prev = self.state.activity_label
            self.state.activity_label = label
            self.events.emit(
                EventType.ACTIVITY_CHANGE, now, self.source_id,
                f"activity {prev} → {label}",
                {"from": prev, "to": label, "level": round(self.state.activity_level, 4)},
            )

    # ---------------------------------------------------------------- semantic
    def note_semantic(
        self,
        text: str,
        ts_monotonic: Optional[float] = None,
        source: str = "tier2",
    ) -> None:
        """Record a fresh semantic read from Tier 2 and derive a SEMANTIC_NOTE."""
        import time as _time

        ts = ts_monotonic if ts_monotonic is not None else self.state.last_update_monotonic
        sem = self.state.semantic
        sem.text = text
        sem.ts_monotonic = ts
        sem.ts_wall = _time.time()
        sem.source = source
        self.events.emit(
            EventType.SEMANTIC_NOTE, ts, self.source_id, text,
            {"source": source},
        )
