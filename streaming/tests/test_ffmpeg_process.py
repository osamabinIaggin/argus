"""
Tests for FFmpegProcessSource using the lavfi synthetic source — no camera or
network required, so these run anywhere (including CI). They guard:
  * the raw-rgb24 read path (exact byte count → correct ndarray shape)
  * clean startup (no spurious reconnect)
  * clean shutdown (stop() must not log a disconnect or bump the reconnect count)
"""

import time

import pytest

from streaming.sources.ffmpeg_process import FFmpegProcessSource


def _run_briefly(width, height, seconds=1.5):
    src = FFmpegProcessSource.test("t", width=width, height=height, fps=30).start()
    first = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        f = src.read(timeout=1.0)
        if f is not None and first is None:
            first = f
    reconnects_before_stop = src.stats.total_reconnects
    decoded = src.stats.frames_decoded
    src.stop()
    return first, reconnects_before_stop, decoded, src


def test_yields_correct_shape_and_dtype():
    first, _, decoded, _ = _run_briefly(640, 480)
    assert first is not None, "expected at least one frame"
    assert first.data.shape == (480, 640, 3)
    assert first.data.dtype.name == "uint8"
    assert decoded > 10, "expected a steady frame flow"


def test_clean_startup_no_spurious_reconnect():
    _, reconnects_before_stop, _, _ = _run_briefly(320, 240)
    assert reconnects_before_stop == 0, "steady state must not reconnect"


def test_clean_shutdown_does_not_count_as_reconnect():
    _, _, _, src = _run_briefly(320, 240)
    # stop() already called inside _run_briefly; the disconnect-on-shutdown must
    # have been suppressed by the stop-flag-first ordering.
    assert src.stats.total_reconnects == 0
    assert src.stats.state.value == "stopped"
