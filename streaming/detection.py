"""
Tier 1 output types — what the always-on detector emits per frame.

These are deliberately model-agnostic: a Detection is just "a labelled, tracked
box with a confidence", regardless of whether YOLO, a cloud detector, or
something else produced it. Tier 3 (scene state) consumes these, so keeping them
independent of the model keeps the detector swappable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(slots=True)
class Detection:
    """One detected object in one frame."""

    label: str                                   # class name, e.g. "person"
    confidence: float                            # 0..1
    bbox: Tuple[float, float, float, float]      # (x1, y1, x2, y2) in frame pixels
    class_id: int                                # model class index
    track_id: Optional[int] = None               # persistent id across frames (None if untracked)

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


@dataclass(slots=True)
class DetectionResult:
    """All detections for a single frame, plus provenance and timing."""

    source_id: str
    frame_seq: int
    ts_monotonic: float
    detections: List[Detection] = field(default_factory=list)
    infer_ms: float = 0.0          # wall-clock inference time for this frame
    frame_width: int = 0
    frame_height: int = 0

    def counts(self) -> dict[str, int]:
        """Number of detections per label, e.g. {'person': 2, 'chair': 1}."""
        out: dict[str, int] = {}
        for d in self.detections:
            out[d.label] = out.get(d.label, 0) + 1
        return out

    def summary(self) -> str:
        if not self.detections:
            return "—"
        parts = []
        for d in self.detections:
            tid = f"#{d.track_id}" if d.track_id is not None else "?"
            parts.append(f"{d.label}{tid}:{d.confidence:.2f}")
        return ", ".join(parts)
