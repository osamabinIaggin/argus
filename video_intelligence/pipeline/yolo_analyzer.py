from __future__ import annotations
"""
Stage 4: YOLOv8n per-keyframe analysis.

Role:
  - Object detection → detected_objects list (feeds output schema directly)
  - Confidence scoring → frame_confidence field in output
  - Context string → injected into vision model prompt ("YOLO detected: person, car")
  - NEVER gates frame survival — advisory only, all keyframes pass through

Design decisions:
  - frame_confidence = max single detection confidence (0.0 if nothing detected)
  - Detected objects deduplicated, order preserved by confidence
  - Zero detections is a valid, non-fatal result
  - Model loaded once and reused across all frames
"""

import numpy as np
from dataclasses import dataclass
from ultralytics import YOLO

from pipeline.keyframe_extractor import Keyframe


YOLO_MODEL = "yolov8n.pt"
DETECTION_THRESHOLD = 0.25
YOLO_DEVICE = "cpu"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class YOLOResult:
    detected_objects: list[str]   # unique class names, ordered by confidence desc
    frame_confidence: float        # max detection confidence; 0.0 if nothing found
    yolo_context: str              # formatted string for vision model prompt


@dataclass
class ScoredKeyframe:
    keyframe: Keyframe
    yolo: YOLOResult

    # Convenience pass-throughs so downstream stages don't reach into .keyframe
    @property
    def keyframe_id(self) -> int:
        return self.keyframe.keyframe_id

    @property
    def timestamp_start(self) -> float:
        return self.keyframe.timestamp_start

    @property
    def timestamp_end(self) -> float:
        return self.keyframe.timestamp_end

    @property
    def scene_id(self) -> int:
        return self.keyframe.scene_id

    @property
    def scene_change(self) -> bool:
        return self.keyframe.scene_change

    @property
    def force_sampled(self) -> bool:
        return self.keyframe.force_sampled

    @property
    def image(self) -> np.ndarray:
        return self.keyframe.image

    @property
    def yolo_context(self) -> str:
        return self.yolo.yolo_context

    @property
    def detected_objects(self) -> list[str]:
        return self.yolo.detected_objects

    @property
    def frame_confidence(self) -> float:
        return self.yolo.frame_confidence


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_yolo_result(raw_results) -> YOLOResult:
    """
    Parse ultralytics result object into a YOLOResult.
    Handles zero-detection case cleanly.
    """
    detections: list[tuple[str, float]] = []   # (class_name, confidence)

    if raw_results and raw_results[0].boxes is not None:
        boxes = raw_results[0].boxes
        names = raw_results[0].names

        for box in boxes:
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = names[cls_id]
            if conf >= DETECTION_THRESHOLD:
                detections.append((cls_name, conf))

    # Sort by confidence descending, then deduplicate preserving order
    detections.sort(key=lambda x: x[1], reverse=True)
    seen: set[str] = set()
    unique_objects: list[str] = []
    for name, _ in detections:
        if name not in seen:
            seen.add(name)
            unique_objects.append(name)

    frame_confidence = detections[0][1] if detections else 0.0

    if unique_objects:
        yolo_context = f"YOLO detected: {', '.join(unique_objects)}"
    else:
        yolo_context = "YOLO detected: no objects identified"

    return YOLOResult(
        detected_objects=unique_objects,
        frame_confidence=round(frame_confidence, 4),
        yolo_context=yolo_context,
    )


def _analyze_frame(model: YOLO, frame_bgr: np.ndarray) -> YOLOResult:
    """Run YOLO inference on a single BGR frame."""
    results = model(
        frame_bgr,
        device=YOLO_DEVICE,
        verbose=False,
        conf=DETECTION_THRESHOLD,
    )
    return _build_yolo_result(results)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_model() -> YOLO:
    """Load YOLOv8n. Downloads weights on first call (~6MB)."""
    return YOLO(YOLO_MODEL)


def analyze_keyframes(
    keyframes: list[Keyframe],
    model: YOLO | None = None,
) -> list[ScoredKeyframe]:
    """
    Run YOLOv8n on every keyframe.

    All keyframes survive regardless of detection results.
    YOLO output enriches the output schema and vision model context only.

    Args:
        keyframes: Output from extract_keyframes().
        model: Optional pre-loaded YOLO model. Loaded fresh if not provided.

    Returns:
        List of ScoredKeyframe with YOLO results attached, same order as input.
    """
    if model is None:
        model = load_model()

    return [
        ScoredKeyframe(keyframe=kf, yolo=_analyze_frame(model, kf.image))
        for kf in keyframes
    ]
