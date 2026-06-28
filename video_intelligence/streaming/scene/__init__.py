"""
Tier 3 — scene state.

The source-of-truth layer of the live pipeline. Consumes Tier-1 DetectionResults
and maintains a continuously-updated SceneState (entities, zones, activity,
semantic), while deriving an append-only EventLog from state transitions.

    from streaming.scene import SceneTracker, Zone, ZoneKind, EventType
"""

from streaming.scene.events import Event, EventLog, EventType
from streaming.scene.state import (
    Entity,
    EntityStatus,
    SceneState,
    SemanticState,
)
from streaming.scene.tracker import SceneTracker
from streaming.scene.zones import Zone, ZoneKind, zones_containing

__all__ = [
    "SceneTracker",
    "SceneState",
    "Entity",
    "EntityStatus",
    "SemanticState",
    "Zone",
    "ZoneKind",
    "zones_containing",
    "Event",
    "EventLog",
    "EventType",
]
