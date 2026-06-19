"""
Tests for pipeline/yolo_analyzer.py

Unit tests mock the YOLO model to test enrichment logic in isolation.
Integration test runs real YOLOv8n inference and is marked separately.
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from pipeline.keyframe_extractor import Keyframe
from pipeline.yolo_analyzer import (
    _build_yolo_result,
    _analyze_frame,
    analyze_keyframes,
    ScoredKeyframe,
    YOLOResult,
    DETECTION_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_keyframe(kid: int, scene_id: int = 1, force_sampled: bool = False) -> Keyframe:
    """Create a minimal Keyframe with a blank image."""
    return Keyframe(
        keyframe_id=kid,
        frame_number=kid * 15,
        timestamp_start=float(kid),
        timestamp_end=float(kid + 3),
        scene_id=scene_id,
        scene_change=(kid == 1),
        force_sampled=force_sampled,
        image=np.zeros((480, 854, 3), dtype=np.uint8),
    )


def make_mock_detection(cls_id: int, cls_name: str, conf: float):
    """Build a mock YOLO box detection."""
    box = MagicMock()
    box.conf = [conf]
    box.cls = [cls_id]
    return box


def make_mock_results(detections: list[tuple[int, str, float]]):
    """
    Build a mock ultralytics results list.
    detections: list of (cls_id, cls_name, confidence)
    """
    result = MagicMock()
    names = {d[0]: d[1] for d in detections}
    boxes = [make_mock_detection(d[0], d[1], d[2]) for d in detections]

    result.boxes = boxes if boxes else None
    result.names = names
    return [result]


# ---------------------------------------------------------------------------
# _build_yolo_result
# ---------------------------------------------------------------------------

class TestBuildYoloResult:
    def test_no_detections_returns_zero_confidence(self):
        results = make_mock_results([])
        yr = _build_yolo_result(results)
        assert yr.frame_confidence == 0.0
        assert yr.detected_objects == []

    def test_no_detections_context_string(self):
        results = make_mock_results([])
        yr = _build_yolo_result(results)
        assert yr.yolo_context == "YOLO detected: no objects identified"

    def test_single_detection(self):
        results = make_mock_results([(0, "person", 0.87)])
        yr = _build_yolo_result(results)
        assert "person" in yr.detected_objects
        assert yr.frame_confidence == pytest.approx(0.87, abs=0.001)

    def test_context_string_lists_objects(self):
        results = make_mock_results([(0, "person", 0.87), (2, "car", 0.65)])
        yr = _build_yolo_result(results)
        assert "person" in yr.yolo_context
        assert "car" in yr.yolo_context
        assert yr.yolo_context.startswith("YOLO detected:")

    def test_frame_confidence_is_max_not_average(self):
        results = make_mock_results([
            (0, "person", 0.90),
            (1, "bicycle", 0.30),
        ])
        yr = _build_yolo_result(results)
        assert yr.frame_confidence == pytest.approx(0.90, abs=0.001)

    def test_objects_sorted_by_confidence_descending(self):
        results = make_mock_results([
            (2, "car", 0.45),
            (0, "person", 0.90),
            (5, "bus", 0.60),
        ])
        yr = _build_yolo_result(results)
        assert yr.detected_objects[0] == "person"   # highest confidence first

    def test_duplicate_class_deduplicated(self):
        results = make_mock_results([
            (0, "person", 0.88),
            (0, "person", 0.72),   # same class, second detection
        ])
        yr = _build_yolo_result(results)
        assert yr.detected_objects.count("person") == 1

    def test_below_threshold_detections_excluded(self):
        results = make_mock_results([
            (0, "person", DETECTION_THRESHOLD - 0.01),   # just below threshold
        ])
        yr = _build_yolo_result(results)
        assert yr.detected_objects == []
        assert yr.frame_confidence == 0.0

    def test_exactly_at_threshold_included(self):
        results = make_mock_results([
            (0, "person", DETECTION_THRESHOLD),
        ])
        yr = _build_yolo_result(results)
        assert "person" in yr.detected_objects

    def test_confidence_rounded_to_4dp(self):
        results = make_mock_results([(0, "person", 0.876543)])
        yr = _build_yolo_result(results)
        assert yr.frame_confidence == round(0.876543, 4)

    def test_null_boxes_handled(self):
        result = MagicMock()
        result.boxes = None
        result.names = {}
        yr = _build_yolo_result([result])
        assert yr.detected_objects == []
        assert yr.frame_confidence == 0.0


# ---------------------------------------------------------------------------
# analyze_keyframes — frame survival guarantee
# ---------------------------------------------------------------------------

class TestAnalyzeKeyframes:
    def _make_mock_model(self, detections_per_call):
        """Model that returns given detections list on each call."""
        model = MagicMock()
        model.return_value = make_mock_results(detections_per_call)
        return model

    def test_all_keyframes_survive_with_detections(self):
        keyframes = [make_keyframe(i) for i in range(1, 6)]
        model = self._make_mock_model([(0, "person", 0.85)])
        scored = analyze_keyframes(keyframes, model=model)
        assert len(scored) == len(keyframes)

    def test_all_keyframes_survive_with_zero_detections(self):
        """Core guarantee: zero YOLO detections never drops a frame."""
        keyframes = [make_keyframe(i) for i in range(1, 6)]
        model = self._make_mock_model([])
        scored = analyze_keyframes(keyframes, model=model)
        assert len(scored) == len(keyframes)

    def test_output_order_matches_input_order(self):
        keyframes = [make_keyframe(i) for i in range(1, 6)]
        model = self._make_mock_model([(0, "person", 0.85)])
        scored = analyze_keyframes(keyframes, model=model)
        for original, result in zip(keyframes, scored):
            assert result.keyframe_id == original.keyframe_id

    def test_returns_scored_keyframe_type(self):
        keyframes = [make_keyframe(1)]
        model = self._make_mock_model([])
        scored = analyze_keyframes(keyframes, model=model)
        assert isinstance(scored[0], ScoredKeyframe)
        assert isinstance(scored[0].yolo, YOLOResult)

    def test_empty_keyframe_list(self):
        model = self._make_mock_model([])
        scored = analyze_keyframes([], model=model)
        assert scored == []

    def test_model_called_once_per_frame(self):
        keyframes = [make_keyframe(i) for i in range(1, 4)]
        model = self._make_mock_model([])
        analyze_keyframes(keyframes, model=model)
        assert model.call_count == len(keyframes)


# ---------------------------------------------------------------------------
# ScoredKeyframe pass-throughs
# ---------------------------------------------------------------------------

class TestScoredKeyframePassthroughs:
    def setup_method(self):
        kf = make_keyframe(3, scene_id=2, force_sampled=True)
        yr = YOLOResult(
            detected_objects=["person"],
            frame_confidence=0.87,
            yolo_context="YOLO detected: person",
        )
        self.sk = ScoredKeyframe(keyframe=kf, yolo=yr)

    def test_keyframe_id(self):
        assert self.sk.keyframe_id == 3

    def test_timestamp_start(self):
        assert self.sk.timestamp_start == 3.0

    def test_timestamp_end(self):
        assert self.sk.timestamp_end == 6.0

    def test_scene_id(self):
        assert self.sk.scene_id == 2

    def test_force_sampled(self):
        assert self.sk.force_sampled is True

    def test_image_accessible(self):
        assert self.sk.image is not None
        assert isinstance(self.sk.image, np.ndarray)


# ---------------------------------------------------------------------------
# Integration test — real YOLOv8n model
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestYOLOIntegration:
    def test_real_inference_on_blank_frame(self):
        """
        Runs real YOLOv8n on a blank frame.
        Expects zero detections — validates the pipeline doesn't crash.
        Model weights downloaded automatically on first run.
        """
        from pipeline.yolo_analyzer import load_model
        model = load_model()
        kf = make_keyframe(1)
        scored = analyze_keyframes([kf], model=model)

        assert len(scored) == 1
        assert isinstance(scored[0].yolo.detected_objects, list)
        assert isinstance(scored[0].yolo.frame_confidence, float)
        assert scored[0].yolo.frame_confidence == 0.0  # blank frame, nothing detected

    def test_real_inference_on_person_frame(self):
        """
        Runs real YOLOv8n on a synthetic frame with a bright rectangle
        (won't detect 'person' but validates model runs and returns structured output).
        """
        from pipeline.yolo_analyzer import load_model
        model = load_model()

        frame = np.zeros((480, 854, 3), dtype=np.uint8)
        # Draw a bright rectangle — won't trigger COCO classes but tests pipeline
        frame[100:400, 200:600] = [200, 150, 100]

        kf = make_keyframe(1)
        kf = Keyframe(
            keyframe_id=1, frame_number=0, timestamp_start=0.0,
            timestamp_end=3.0, scene_id=1, scene_change=True,
            force_sampled=False, image=frame,
        )
        scored = analyze_keyframes([kf], model=model)

        assert len(scored) == 1
        assert 0.0 <= scored[0].yolo.frame_confidence <= 1.0
        assert isinstance(scored[0].yolo.yolo_context, str)
        assert scored[0].yolo.yolo_context.startswith("YOLO detected:")
