"""
Tier 4 (sync) tests — verify fan-out, error isolation, snapshot cadence, and the
dashboard's buffering, all without starting a server or touching a database.
"""

from __future__ import annotations

from streaming.detection import Detection, DetectionResult
from streaming.scene import SceneTracker
from streaming.sync import LiveDashboard, SinkHub, StatePublisher
from streaming.sync.sink import StateSink

W, H = 64, 48


def _result(seq, ts, dets):
    return DetectionResult("t", seq, ts, list(dets), frame_width=W, frame_height=H)


def _person(tid, cx=20, cy=20):
    return Detection("person", 0.9, (cx - 5, cy - 5, cx + 5, cy + 5), 0, tid)


def _confirm(tr, tid=1, t0=0.0):
    for i, ts in enumerate([t0, t0 + 0.2, t0 + 0.4]):
        tr.update(_result(i, ts, [_person(tid)]))


class _Recording(StateSink):
    def __init__(self):
        self.events = []
        self.snapshots = []

    def on_event(self, event):
        self.events.append(event)

    def on_snapshot(self, snapshot):
        self.snapshots.append(snapshot)


class _Boom(StateSink):
    def on_event(self, event):
        raise RuntimeError("boom")

    def on_snapshot(self, snapshot):
        raise RuntimeError("boom")


def test_hub_fans_out_to_all_sinks():
    a, b = _Recording(), _Recording()
    hub = SinkHub([a]).add(b)
    hub.on_snapshot({"x": 1})
    assert a.snapshots == b.snapshots == [{"x": 1}]


def test_hub_isolates_a_failing_sink():
    good = _Recording()
    hub = SinkHub([_Boom(), good])      # bad sink first
    hub.on_snapshot({"x": 1})            # must not raise
    hub.on_event(object())               # must not raise
    assert good.snapshots == [{"x": 1}]  # good sink still received it


def test_publisher_snapshots_on_interval_and_forwards_events():
    tr = SceneTracker("t", confirm_seconds=0.0)
    rec = _Recording()
    pub = StatePublisher(tr, rec, snapshot_interval_s=1.0)

    # An entity entering emits an event → forwarded immediately.
    _confirm(tr)
    assert any(e.type.value == "entity_entered" for e in rec.events)

    # tick at t=0 emits the first snapshot; t=0.5 is within interval (no snap);
    # t=1.0 emits the next.
    assert pub.tick(now=0.0) is True
    assert pub.tick(now=0.5) is False
    assert pub.tick(now=1.0) is True
    assert len(rec.snapshots) == 2
    assert rec.snapshots[-1]["entity_count"] == 1


def test_dashboard_buffers_events_and_snapshot_without_server():
    tr = SceneTracker("t", confirm_seconds=0.0)
    dash = LiveDashboard(port=0)             # not started; just buffering
    pub = StatePublisher(tr, dash, snapshot_interval_s=0.0)

    _confirm(tr)                              # emits entity_entered → dash.on_event
    pub.tick(now=1.0)                         # pushes a snapshot

    snap, ver = dash._read_snapshot()
    assert ver >= 1 and snap["entity_count"] == 1

    new = dash._events_since(0)
    assert any(e["type"] == "entity_entered" for (_seq, e) in new)
    # _events_since is incremental — nothing new past the latest seq.
    last_seq = new[-1][0]
    assert dash._events_since(last_seq) == []
