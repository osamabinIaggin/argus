"""
Scene state — the continuously-updated source of truth for one stream.

This is the heart of Tier 3. Tier 1 (detection) and Tier 2 (semantics) feed it;
everything downstream (the event log, the dashboard, the chat/query layer, a
robot planner) reads from it. The design rule from the pivot is explicit:

    **Scene state is the source of truth. The event log is DERIVED from
    transitions in this state — never the other way round.**

So the dataclasses here hold *current* truth (who is present, where, how active,
what the last semantic read was). The `SceneTracker` mutates them and emits
events when something here changes. A snapshot is JSON-ready so the whole state
can be pushed over PowerSync or answered against by a chat layer.

Time: internal logic reasons in `time.monotonic()` (clock-step immune, same
basis as the rest of the pipeline). We also record wall-clock (`time.time()`)
first-seen so a human-facing log can say "a person arrived at 3:04pm".
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Set, Tuple


class EntityStatus(str, Enum):
    # Seen, but not yet present long enough to trust — a flickered detection or
    # a momentary false positive should die here without ever emitting an event.
    TENTATIVE = "tentative"
    # Confirmed present. Entry/exit/zone events only fire for confirmed entities.
    CONFIRMED = "confirmed"


@dataclass(slots=True)
class Entity:
    """One tracked thing in the scene, keyed by its Tier-1 track id."""

    track_id: int
    label: str
    class_id: int
    confidence: float
    bbox: Tuple[float, float, float, float]   # (x1, y1, x2, y2) in frame pixels
    status: EntityStatus

    first_seen_monotonic: float
    last_seen_monotonic: float
    first_seen_wall: float

    hits: int = 1                              # frames this entity was matched in
    zones: Set[str] = field(default_factory=set)   # zone names currently occupied
    speed: float = 0.0                         # smoothed motion, frame-fractions/sec

    # Recent normalized centers (ts_monotonic, cx, cy) for velocity. Bounded so
    # an entity present for hours does not grow without limit.
    _centers: Deque[Tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=12)
    )

    def age_seconds(self, now_monotonic: float) -> float:
        return now_monotonic - self.first_seen_monotonic

    def to_dict(self) -> dict:
        x1, y1, x2, y2 = self.bbox
        return {
            "track_id": self.track_id,
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "bbox": [round(v, 1) for v in (x1, y1, x2, y2)],
            "zones": sorted(self.zones),
            "speed": round(self.speed, 4),
            "status": self.status.value,
            "first_seen_wall": self.first_seen_wall,
            "age_seconds": None,   # filled by SceneState.snapshot (needs `now`)
        }


@dataclass(slots=True)
class SemanticState:
    """The last semantic ('what is happening') read, owned by Tier 2.

    Tier 3 only stores it and answers staleness. Keeping this here — rather than
    coupling Tier 3 to a VLM — means graceful degradation: if Tier 2 is down the
    geometric state stays live and this just goes stale, flagged honestly.
    """

    text: Optional[str] = None
    ts_monotonic: Optional[float] = None
    ts_wall: Optional[float] = None
    source: Optional[str] = None       # e.g. "tier2", model name

    def is_stale(self, now_monotonic: float, ttl_seconds: float) -> bool:
        if self.ts_monotonic is None:
            return True
        return (now_monotonic - self.ts_monotonic) > ttl_seconds

    def to_dict(self, now_monotonic: float, ttl_seconds: float) -> dict:
        age = None if self.ts_monotonic is None else round(now_monotonic - self.ts_monotonic, 2)
        return {
            "text": self.text,
            "source": self.source,
            "age_seconds": age,
            "stale": self.is_stale(now_monotonic, ttl_seconds),
        }


@dataclass(slots=True)
class SceneState:
    """Everything currently true about one stream."""

    source_id: str
    frame_width: int = 0
    frame_height: int = 0
    frame_seq: int = 0
    last_update_monotonic: float = 0.0

    entities: Dict[int, Entity] = field(default_factory=dict)
    # zone name -> set of confirmed track_ids currently inside it
    zone_occupancy: Dict[str, Set[int]] = field(default_factory=dict)

    activity_level: float = 0.0        # smoothed, ~0..1 (frame-fractions/sec)
    activity_label: str = "idle"       # idle / low / medium / high
    semantic: SemanticState = field(default_factory=SemanticState)

    def confirmed_entities(self) -> List[Entity]:
        return [e for e in self.entities.values() if e.status is EntityStatus.CONFIRMED]

    def snapshot(self, semantic_ttl_seconds: float = 10.0) -> dict:
        """JSON-ready view of the scene — PowerSync push / chat grounding.

        Only *confirmed* entities are exposed; tentative ones are internal
        bookkeeping and would just be noise to a consumer.
        """
        now = self.last_update_monotonic
        ents = []
        for e in self.confirmed_entities():
            d = e.to_dict()
            d["age_seconds"] = round(e.age_seconds(now), 2)
            ents.append(d)
        return {
            "source_id": self.source_id,
            "frame_seq": self.frame_seq,
            "frame_size": [self.frame_width, self.frame_height],
            "entity_count": len(ents),
            "entities": ents,
            "zone_occupancy": {
                name: sorted(tids) for name, tids in self.zone_occupancy.items()
            },
            "activity": {"level": round(self.activity_level, 4), "label": self.activity_label},
            "semantic": self.semantic.to_dict(now, semantic_ttl_seconds),
        }
