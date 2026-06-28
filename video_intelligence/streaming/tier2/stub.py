"""
StubSceneUnderstander — a deterministic, dependency-free Tier-2 backend.

Exists so the gating controller (and anything above it) can be developed and
fully tested without downloading a multi-GB model or having MLX installed. It
records what it was asked to observe and returns a canned, context-aware string,
optionally after a simulated latency so tests can exercise the timing logic.
"""

from __future__ import annotations

import time
from typing import Optional

from streaming.frame import Frame
from streaming.tier2.understanding import SceneObservation, SceneUnderstander


class StubSceneUnderstander(SceneUnderstander):
    def __init__(self, latency_s: float = 0.0, fail: bool = False) -> None:
        self.latency_s = latency_s
        self.fail = fail
        self.calls = 0
        self.last_frame_seq: Optional[int] = None
        self.last_context: Optional[str] = None

    def observe(self, frame: Frame, context: Optional[str] = None) -> SceneObservation:
        self.calls += 1
        self.last_frame_seq = frame.seq
        self.last_context = context
        if self.latency_s:
            time.sleep(self.latency_s)
        if self.fail:
            return SceneObservation.failure("stub forced failure", source="stub")
        text = f"stub view of frame {frame.seq}"
        if context:
            text += f" ({context})"
        return SceneObservation(text=text, source="stub", infer_ms=self.latency_s * 1000.0)
