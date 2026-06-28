"""
Tests for the drop-stale primitive — the heart of the ingest layer's
"never lag" guarantee. These run without any camera or network.
"""

import threading
import time

import numpy as np

from streaming.frame import Frame
from streaming.sources.base import LatestFrameSlot


def _frame(seq: int) -> Frame:
    return Frame(
        data=np.zeros((2, 2, 3), dtype=np.uint8),
        seq=seq,
        ts_monotonic=time.monotonic(),
        source_id="test",
    )


def test_get_returns_latest_not_oldest():
    slot = LatestFrameSlot()
    slot.put(_frame(1))
    slot.put(_frame(2))
    slot.put(_frame(3))
    got = slot.get(timeout=0.1)
    assert got is not None and got.seq == 3, "consumer must get the freshest frame"


def test_overwritten_frames_count_as_drops():
    slot = LatestFrameSlot()
    slot.put(_frame(1))   # unconsumed
    slot.put(_frame(2))   # overwrites #1 -> 1 drop
    slot.put(_frame(3))   # overwrites #2 -> 2 drops
    assert slot.dropped == 2
    slot.get(timeout=0.1)
    slot.put(_frame(4))   # previous consumed -> no drop
    assert slot.dropped == 2


def test_get_blocks_until_frame_then_delivers():
    slot = LatestFrameSlot()

    def producer():
        time.sleep(0.05)
        slot.put(_frame(7))

    threading.Thread(target=producer, daemon=True).start()
    got = slot.get(timeout=1.0)
    assert got is not None and got.seq == 7
    assert slot.delivered == 1


def test_get_times_out_when_empty():
    slot = LatestFrameSlot()
    assert slot.get(timeout=0.05) is None


def test_close_unblocks_waiting_consumer():
    slot = LatestFrameSlot()

    def closer():
        time.sleep(0.05)
        slot.close()

    threading.Thread(target=closer, daemon=True).start()
    t0 = time.monotonic()
    assert slot.get(timeout=2.0) is None
    assert time.monotonic() - t0 < 1.0, "close() must wake the consumer promptly"
