"""
Tier 3 (scene state) tests — drive the SceneTracker with synthetic
DetectionResults so they run fast and need no torch/YOLO/camera.

What we prove:
  * lifecycle is debounced — a one-frame flicker never emits enter/exit, and a
    persistent object enters once and exits once;
  * a transient miss inside the grace window does NOT drop a present entity;
  * zones produce enter/exit/breach events from the bottom-center anchor, in
    resolution-independent normalized coordinates;
  * activity rises with motion and falls to idle when still;
  * semantic notes are stored, go stale on a TTL, and snapshots are JSON-clean.
"""

from __future__ import annotations

import json

from streaming.detection import Detection, DetectionResult
from streaming.scene import EventType, SceneTracker, Zone, ZoneKind

W, H = 640, 480


def _result(seq: int, ts: float, dets):
    return DetectionResult(
        source_id="t",
        frame_seq=seq,
        ts_monotonic=ts,
        detections=list(dets),
        frame_width=W,
        frame_height=H,
    )


def _person(track_id: int, cx: float, cy: float, *, size: float = 40.0, conf: float = 0.9):
    """A person box centered at (cx, cy) in pixels."""
    return Detection(
        label="person",
        confidence=conf,
        bbox=(cx - size, cy - size, cx + size, cy + size),
        class_id=0,
        track_id=track_id,
    )


def _types(tracker):
    return [e.type for e in tracker.events.recent()]


# --------------------------------------------------------------- lifecycle ---

def test_single_frame_flicker_emits_nothing():
    tr = SceneTracker("t", confirm_seconds=0.3)
    tr.update(_result(0, 0.0, [_person(1, 100, 100)]))
    # Gone immediately after one frame, never confirmed.
    tr.update(_result(1, 2.0, []))  # past grace, but it was only ever tentative
    assert EventType.ENTITY_ENTERED not in _types(tr)
    assert EventType.ENTITY_EXITED not in _types(tr)
    assert tr.state.entities == {}


def test_persistent_entity_enters_once_and_exits_once():
    tr = SceneTracker("t", confirm_seconds=0.3, exit_grace_seconds=1.0)
    # Seen across enough time to confirm.
    for i, ts in enumerate([0.0, 0.2, 0.4, 0.6]):
        tr.update(_result(i, ts, [_person(1, 100, 100)]))
    assert _types(tr).count(EventType.ENTITY_ENTERED) == 1
    assert len(tr.state.confirmed_entities()) == 1

    # Disappear; stays through grace, then exits exactly once.
    tr.update(_result(10, 1.0, []))     # within grace from last_seen=0.6
    assert EventType.ENTITY_EXITED not in _types(tr)
    tr.update(_result(11, 2.0, []))     # past grace
    assert _types(tr).count(EventType.ENTITY_EXITED) == 1
    assert tr.state.entities == {}


def test_transient_miss_within_grace_keeps_entity():
    tr = SceneTracker("t", confirm_seconds=0.2, exit_grace_seconds=1.0)
    tr.update(_result(0, 0.0, [_person(1, 100, 100)]))
    tr.update(_result(1, 0.3, [_person(1, 105, 100)]))  # confirmed
    assert len(tr.state.confirmed_entities()) == 1
    tr.update(_result(2, 0.6, []))                       # missed one frame
    assert len(tr.state.entities) == 1                   # still here
    tr.update(_result(3, 0.9, [_person(1, 110, 100)]))   # reappears
    assert EventType.ENTITY_EXITED not in _types(tr)
    assert tr.state.confirmed_entities()[0].hits >= 3


# -------------------------------------------------------------------- zones ---

def _confirm(tr, track_id, x, y, t0=0.0):
    # Drive an entity to confirmed at a position.
    for i, ts in enumerate([t0, t0 + 0.2, t0 + 0.4]):
        tr.update(_result(i, ts, [_person(track_id, x, y)]))


def test_zone_enter_and_exit_events():
    # Right-half rectangle zone in normalized coords.
    zone = Zone.rect("right", 0.5, 0.0, 1.0, 1.0)
    tr = SceneTracker("t", zones=[zone], confirm_seconds=0.2)
    # Start in left half (bottom-center anchor x≈100/640 well under 0.5).
    _confirm(tr, 1, 100, 200)
    assert "right" not in [z for e in tr.state.entities.values() for z in e.zones]

    # Move into right half.
    tr.update(_result(5, 1.0, [_person(1, 500, 200)]))
    assert tr.state.entities[1].zones == {"right"}
    assert 1 in tr.state.zone_occupancy["right"]
    assert EventType.ZONE_ENTERED in _types(tr)

    # Move back out.
    tr.update(_result(6, 1.2, [_person(1, 100, 200)]))
    assert tr.state.entities[1].zones == set()
    assert 1 not in tr.state.zone_occupancy["right"]
    assert EventType.ZONE_EXITED in _types(tr)


def test_restricted_zone_emits_breach():
    zone = Zone.rect("vault", 0.0, 0.0, 0.4, 1.0, kind=ZoneKind.RESTRICTED)
    tr = SceneTracker("t", zones=[zone], confirm_seconds=0.2)
    _confirm(tr, 1, 500, 200)  # start outside (right side)
    tr.update(_result(5, 1.0, [_person(1, 50, 200)]))  # cross into vault
    types = _types(tr)
    assert EventType.ZONE_BREACH in types
    assert EventType.ZONE_ENTERED not in types  # restricted -> breach, not enter


def test_zones_are_resolution_independent():
    # Same normalized zone, two different frame sizes: behaviour identical.
    zone = Zone.rect("right", 0.5, 0.0, 1.0, 1.0)

    def occupied(width, height):
        tr = SceneTracker("t", zones=[zone], confirm_seconds=0.2)
        cx = int(width * 0.75)
        det = Detection("person", 0.9, (cx - 10, height // 2 - 10, cx + 10, height // 2 + 10), 0, 1)
        for i, ts in enumerate([0.0, 0.2, 0.4]):
            tr.update(DetectionResult("t", i, ts, [det], frame_width=width, frame_height=height))
        return tr.state.entities[1].zones

    assert occupied(640, 480) == occupied(1920, 1080) == {"right"}


# ----------------------------------------------------------------- activity ---

def test_activity_rises_with_motion_then_settles_idle():
    tr = SceneTracker("t", confirm_seconds=0.0, activity_smoothing=0.6)
    # Sweep an entity across the frame quickly.
    x = 50.0
    for i in range(8):
        tr.update(_result(i, i * 0.1, [_person(1, x, 200)]))
        x += 70.0
    moving_level = tr.state.activity_level
    assert moving_level > 0.0
    assert tr.state.activity_label in {"low", "medium", "high"}

    # Hold still — activity decays back toward idle.
    for i in range(8, 30):
        tr.update(_result(i, i * 0.1, [_person(1, x, 200)]))
    assert tr.state.activity_level < moving_level
    assert tr.state.activity_label == "idle"


# ----------------------------------------------------------------- semantic ---

def test_semantic_note_storage_staleness_and_event():
    tr = SceneTracker("t", semantic_ttl_seconds=5.0)
    tr.update(_result(0, 10.0, [_person(1, 100, 100)]))
    tr.note_semantic("a person stands near the door", ts_monotonic=10.0)
    assert tr.state.semantic.text == "a person stands near the door"
    assert EventType.SEMANTIC_NOTE in _types(tr)
    assert tr.state.semantic.is_stale(now_monotonic=12.0, ttl_seconds=5.0) is False
    assert tr.state.semantic.is_stale(now_monotonic=20.0, ttl_seconds=5.0) is True


def test_snapshot_is_json_serializable_and_hides_tentative():
    tr = SceneTracker("t", confirm_seconds=0.3)
    tr.update(_result(0, 0.0, [_person(1, 100, 100)]))   # tentative only
    snap = tr.state.snapshot()
    assert snap["entity_count"] == 0                      # tentative hidden
    json.dumps(snap)                                      # must not raise

    _confirm(tr, 1, 100, 100)
    snap = tr.state.snapshot()
    assert snap["entity_count"] == 1
    assert snap["entities"][0]["label"] == "person"
    json.dumps(snap)


# ------------------------------------------------------------ event log hook ---

def test_event_subscriber_receives_and_errors_are_isolated():
    tr = SceneTracker("t", confirm_seconds=0.0)
    got = []
    tr.events.subscribe(lambda e: got.append(e.type))
    tr.events.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))  # bad sink
    _confirm(tr, 1, 100, 100)
    assert EventType.ENTITY_ENTERED in got  # delivered despite the throwing sink
