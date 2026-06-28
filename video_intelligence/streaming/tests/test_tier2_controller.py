"""
Tier 2 gating tests — drive Tier2Controller.tick() with an explicit clock and a
stub backend, so the scheduling policy is verified deterministically with no
threads, no MLX, no model download.

What we prove:
  * heartbeat floor fires a refresh even with zero events;
  * a trigger event fires a refresh sooner than the heartbeat would;
  * the rate cap (min_interval) blocks back-to-back runs under trigger spam;
  * the worker reasons over the freshest offered frame (drop-stale);
  * results land in the scene state's semantic slot (+ SEMANTIC_NOTE event);
  * a failing backend degrades gracefully (backoff, no crash, semantic stays put);
  * start()/stop() of the real thread is clean.
"""

from __future__ import annotations

import time

import numpy as np

from streaming.detection import Detection, DetectionResult
from streaming.frame import Frame
from streaming.scene import EventType, SceneTracker, Zone, ZoneKind
from streaming.tier2 import StubSceneUnderstander, Tier2Controller

W, H = 64, 48


def _frame(seq: int, ts: float) -> Frame:
    return Frame(data=np.zeros((H, W, 3), dtype=np.uint8), seq=seq, ts_monotonic=ts, source_id="t")


def _result(seq, ts, dets):
    return DetectionResult("t", seq, ts, list(dets), frame_width=W, frame_height=H)


def _person(tid, cx, cy):
    return Detection("person", 0.9, (cx - 5, cy - 5, cx + 5, cy + 5), 0, tid)


def _confirm_entity(tr, tid=1, x=10, y=20, t0=0.0):
    for i, ts in enumerate([t0, t0 + 0.2, t0 + 0.4]):
        tr.update(_result(i, ts, [_person(tid, x, y)]))


def test_heartbeat_fires_without_events():
    tr = SceneTracker("t")
    stub = StubSceneUnderstander()
    c = Tier2Controller(tr, stub, heartbeat_s=8.0, min_interval_s=1.0)
    c.offer(_frame(0, 0.0))

    assert c.tick(now=0.0) is True          # first run is always allowed
    assert c.tick(now=3.0) is False         # within heartbeat, no trigger
    c.offer(_frame(1, 9.0))
    assert c.tick(now=9.0) is True          # heartbeat elapsed → refresh
    assert stub.calls == 2
    assert tr.state.semantic.text is not None


def test_trigger_fires_sooner_than_heartbeat():
    tr = SceneTracker("t", confirm_seconds=0.0)
    stub = StubSceneUnderstander()
    c = Tier2Controller(tr, stub, heartbeat_s=30.0, min_interval_s=1.0)
    c.offer(_frame(0, 0.0))
    c.tick(now=0.0)                          # initial run
    assert c.tick(now=2.0) is False          # no trigger, heartbeat far away

    # A confirmed entity emits ENTITY_ENTERED → a trigger.
    _confirm_entity(tr, t0=2.0)
    c.offer(_frame(5, 3.0))
    assert c.tick(now=3.0) is True           # trigger fired the refresh early


def test_rate_cap_blocks_back_to_back_runs():
    tr = SceneTracker("t", confirm_seconds=0.0)
    stub = StubSceneUnderstander()
    c = Tier2Controller(tr, stub, heartbeat_s=30.0, min_interval_s=1.0)
    c.offer(_frame(0, 0.0))
    c.tick(now=0.0)
    # Spam triggers within min_interval — must NOT run again.
    for t in (0.1, 0.2, 0.3):
        _confirm_entity(tr, tid=int(t * 10) + 2, x=10, t0=t)
        c.offer(_frame(10, t))
        assert c.tick(now=t) is False
    # Past min_interval, the still-pending trigger runs exactly once.
    c.offer(_frame(11, 1.5))
    assert c.tick(now=1.5) is True
    assert stub.calls == 2


def test_drop_stale_uses_freshest_frame():
    tr = SceneTracker("t")
    stub = StubSceneUnderstander()
    c = Tier2Controller(tr, stub, min_interval_s=0.0, heartbeat_s=0.0)
    c.offer(_frame(100, 0.0))
    c.offer(_frame(200, 0.1))
    c.offer(_frame(300, 0.2))               # only the newest should be seen
    assert c.tick(now=1.0) is True
    assert stub.last_frame_seq == 300
    assert c.dropped_frames == 2


def test_result_lands_in_semantic_slot_with_event():
    tr = SceneTracker("t")
    stub = StubSceneUnderstander()
    c = Tier2Controller(tr, stub)
    c.offer(_frame(7, 5.0))
    c.tick(now=5.0)
    assert tr.state.semantic.text == "stub view of frame 7 (nothing tracked; activity: idle)"
    assert tr.state.semantic.source == "stub"
    types = [e.type for e in tr.events.recent()]
    assert EventType.SEMANTIC_NOTE in types


def test_failing_backend_degrades_gracefully():
    tr = SceneTracker("t")
    bad = StubSceneUnderstander(fail=True)
    c = Tier2Controller(tr, bad, min_interval_s=0.0, heartbeat_s=0.0, backoff_s=5.0)
    c.offer(_frame(1, 0.0))
    assert c.tick(now=0.0) is True           # it ran…
    assert c.failures == 1
    assert tr.state.semantic.text is None    # …but semantic was NOT poisoned
    # Backoff is in effect — no busy-loop retry.
    c.offer(_frame(2, 0.5))
    assert c.tick(now=0.5) is False


def test_thread_start_stop_is_clean():
    tr = SceneTracker("t")
    stub = StubSceneUnderstander()
    c = Tier2Controller(tr, stub, min_interval_s=0.0, heartbeat_s=0.0)
    c.offer(_frame(1, 0.0))
    c.start()
    deadline = time.monotonic() + 2.0
    while stub.calls == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    c.stop()
    assert stub.calls >= 1
    assert tr.state.semantic.text is not None
