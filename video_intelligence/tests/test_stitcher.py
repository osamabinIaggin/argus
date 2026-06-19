"""
Tests for pipeline/stitcher.py

All Gemini summary calls are mocked — no API key needed.
"""

import json
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from pipeline.keyframe_extractor import Keyframe
from pipeline.yolo_analyzer import ScoredKeyframe, YOLOResult
from pipeline.vision_model import DescribedKeyframe, FrameDescription
from pipeline.preprocessor import PreprocessResult, VideoMetadata
from pipeline.stitcher import (
    stitch,
    build_timeline_entry,
    _build_timeline_text,
    _build_summary_prompt,
    _parse_summary,
    _fmt_ts,
    _generate_video_id,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def make_described(
    kid: int,
    ts_start: float = None,
    ts_end: float = None,
    description: str = None,
    camera: str = "static",
    objects: list = None,
    confidence: float = 0.85,
    scene_change: bool = False,
) -> DescribedKeyframe:
    ts_start = ts_start if ts_start is not None else float(kid * 3)
    ts_end   = ts_end   if ts_end   is not None else float(kid * 3 + 3)

    kf = Keyframe(
        keyframe_id=kid, frame_number=kid * 15,
        timestamp_start=ts_start, timestamp_end=ts_end,
        scene_id=1, scene_change=scene_change, force_sampled=False,
        image=np.zeros((480, 854, 3), dtype=np.uint8),
    )
    yr = YOLOResult(
        detected_objects=objects or [],
        frame_confidence=confidence,
        yolo_context="",
    )
    sk = ScoredKeyframe(keyframe=kf, yolo=yr)
    fd = FrameDescription(
        keyframe_id=kid,
        description=description or f"Description for frame {kid}.",
        camera_movement=camera,
        actions="some action",
        changes_from_previous="slight change",
    )
    return DescribedKeyframe(scored=sk, frame_desc=fd)


def make_preprocess_result(
    width=1280, height=720, fps=30.0, duration=30.0,
    proc_w=854, proc_h=480, proc_fps=5,
) -> PreprocessResult:
    meta = VideoMetadata(
        duration_seconds=duration,
        original_fps=fps,
        original_width=width,
        original_height=height,
        is_portrait=height > width,
    )
    return PreprocessResult(
        processed_video_path="/tmp/test_processed.mp4",
        audio_path="/tmp/test_audio.aac",
        metadata=meta,
        processed_width=proc_w,
        processed_height=proc_h,
        processed_fps=proc_fps,
    )


def make_summary_model(summary_text: str = "A test video summary.") -> MagicMock:
    model = MagicMock()
    response = MagicMock()
    response.text = json.dumps({"summary": summary_text})
    model.models.generate_content.return_value = response
    return model


# ---------------------------------------------------------------------------
# _parse_summary
# ---------------------------------------------------------------------------

class TestParseSummary:
    def test_valid_json_summary(self):
        text = json.dumps({"summary": "A person assembles a robot."})
        assert _parse_summary(text) == "A person assembles a robot."

    def test_markdown_wrapped_json(self):
        text = '```json\n{"summary": "A drone flies over a city."}\n```'
        assert _parse_summary(text) == "A drone flies over a city."

    def test_invalid_json_returns_fallback(self):
        result = _parse_summary("not json at all")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_missing_summary_key_returns_fallback(self):
        text = json.dumps({"result": "something else"})
        result = _parse_summary(text)
        assert result == "Summary unavailable."

    def test_empty_summary_returns_fallback(self):
        text = json.dumps({"summary": ""})
        result = _parse_summary(text)
        assert result == "Summary unavailable."

    def test_strips_leading_trailing_whitespace(self):
        text = json.dumps({"summary": "  Clean summary.  "})
        assert _parse_summary(text) == "Clean summary."


# ---------------------------------------------------------------------------
# _build_timeline_text
# ---------------------------------------------------------------------------

class TestBuildTimelineText:
    def test_contains_timestamps(self):
        frames = [make_described(1, ts_start=0.0, ts_end=3.0)]
        text = _build_timeline_text(frames)
        assert "0:00.00" in text
        assert "0:03.00" in text

    def test_contains_descriptions(self):
        frames = [make_described(1, description="Person walks into frame.")]
        text = _build_timeline_text(frames)
        assert "Person walks into frame." in text

    def test_camera_movement_included_when_not_static(self):
        frames = [make_described(1, camera="pan_left")]
        text = _build_timeline_text(frames)
        assert "pan_left" in text

    def test_static_camera_movement_not_included(self):
        frames = [make_described(1, camera="static")]
        text = _build_timeline_text(frames)
        assert "camera" not in text.lower()

    def test_multiple_frames_all_present(self):
        frames = [make_described(i) for i in range(1, 5)]
        text = _build_timeline_text(frames)
        for i in range(1, 5):
            assert f"Description for frame {i}." in text

    def test_empty_list_returns_empty_string(self):
        assert _build_timeline_text([]) == ""


# ---------------------------------------------------------------------------
# build_timeline_entry
# ---------------------------------------------------------------------------

class TestBuildTimelineEntry:
    def test_required_schema_fields_present(self):
        dk = make_described(1, ts_start=0.0, ts_end=4.0, objects=["person"])
        entry = build_timeline_entry(dk)
        required = [
            "keyframe_id", "timestamp_start", "timestamp_end",
            "description", "detected_objects", "scene_change", "confidence",
            "camera_movement", "actions", "changes_from_previous",
        ]
        for field in required:
            assert field in entry, f"Missing field: {field}"

    def test_keyframe_id_correct(self):
        assert build_timeline_entry(make_described(7))["keyframe_id"] == 7

    def test_timestamps_formatted_as_strings(self):
        dk = make_described(1, ts_start=65.0, ts_end=68.0)
        entry = build_timeline_entry(dk)
        assert isinstance(entry["timestamp_start"], str)
        assert "1:05" in entry["timestamp_start"]

    def test_detected_objects_carried_from_yolo(self):
        dk = make_described(1, objects=["car", "person"])
        entry = build_timeline_entry(dk)
        assert "car" in entry["detected_objects"]
        assert "person" in entry["detected_objects"]

    def test_scene_change_is_native_bool(self):
        dk = make_described(1, scene_change=True)
        entry = build_timeline_entry(dk)
        assert entry["scene_change"] is True
        assert type(entry["scene_change"]) is bool

    def test_confidence_from_yolo(self):
        dk = make_described(1, confidence=0.73)
        entry = build_timeline_entry(dk)
        assert entry["confidence"] == pytest.approx(0.73)

    def test_description_from_vision_model(self):
        dk = make_described(1, description="A bright sunrise over mountains.")
        entry = build_timeline_entry(dk)
        assert entry["description"] == "A bright sunrise over mountains."


# ---------------------------------------------------------------------------
# stitch — full output schema
# ---------------------------------------------------------------------------

class TestStitch:
    def _run(self, n_frames=3, duration=30.0, total_frames=451, proc_time=2.4,
             summary="A test video.", video_id="vid_test001"):
        frames = [make_described(i) for i in range(1, n_frames + 1)]
        pr = make_preprocess_result(duration=duration)
        model = make_summary_model(summary)
        return stitch(
            described=frames,
            preprocess_result=pr,
            total_frames=total_frames,
            processing_time_s=proc_time,
            video_id=video_id,
            summary_model=model,
        )

    def test_returns_dict(self):
        assert isinstance(self._run(), dict)

    def test_video_id_set(self):
        result = self._run(video_id="vid_abc123")
        assert result["video_id"] == "vid_abc123"

    def test_status_complete(self):
        assert self._run()["status"] == "complete"

    def test_summary_present(self):
        result = self._run(summary="Earth rotates slowly in space.")
        assert result["summary"] == "Earth rotates slowly in space."

    def test_timeline_length_matches_frames(self):
        result = self._run(n_frames=5)
        assert len(result["timeline"]) == 5

    def test_timeline_ordered_by_keyframe_id(self):
        result = self._run(n_frames=5)
        ids = [e["keyframe_id"] for e in result["timeline"]]
        assert ids == sorted(ids)

    def test_metadata_original_resolution(self):
        result = self._run()
        assert result["metadata"]["original_resolution"] == "1280x720"

    def test_metadata_processed_resolution(self):
        result = self._run()
        assert result["metadata"]["processed_resolution"] == "854x480"

    def test_metadata_original_fps(self):
        result = self._run()
        assert result["metadata"]["original_fps"] == 30.0

    def test_metadata_processed_fps(self):
        result = self._run()
        assert result["metadata"]["processed_fps"] == 5  # default proc_fps in make_preprocess_result

    def test_metadata_duration_seconds(self):
        result = self._run(duration=30.5)
        assert result["metadata"]["duration_seconds"] == pytest.approx(30.5)

    def test_metadata_total_frames(self):
        result = self._run(total_frames=451)
        assert result["metadata"]["total_frames_extracted"] == 451

    def test_metadata_keyframes_analyzed(self):
        result = self._run(n_frames=12, total_frames=451)
        assert result["metadata"]["keyframes_analyzed"] == 12

    def test_metadata_duplicates_removed(self):
        result = self._run(n_frames=12, total_frames=451)
        assert result["metadata"]["duplicates_removed"] == 451 - 12

    def test_metadata_processing_time(self):
        result = self._run(proc_time=2.4)
        assert result["metadata"]["processing_time_seconds"] == pytest.approx(2.4)

    def test_video_id_auto_generated_when_not_provided(self):
        frames = [make_described(1)]
        pr = make_preprocess_result()
        model = make_summary_model()
        result = stitch(
            described=frames, preprocess_result=pr,
            total_frames=100, processing_time_s=1.0,
            summary_model=model,
        )
        assert result["video_id"].startswith("vid_")
        assert len(result["video_id"]) > 4

    def test_summary_model_called_once(self):
        frames = [make_described(i) for i in range(1, 4)]
        pr = make_preprocess_result()
        model = make_summary_model()
        stitch(described=frames, preprocess_result=pr,
               total_frames=100, processing_time_s=1.0,
               summary_model=model)
        assert model.models.generate_content.call_count == 1

    def test_output_is_json_serializable(self):
        result = self._run()
        # Must not raise
        serialized = json.dumps(result)
        assert len(serialized) > 0

    def test_empty_described_list(self):
        frames = []
        pr = make_preprocess_result()
        model = make_summary_model("Empty video.")
        result = stitch(
            described=frames, preprocess_result=pr,
            total_frames=100, processing_time_s=0.5,
            summary_model=model,
        )
        assert result["timeline"] == []
        assert result["metadata"]["keyframes_analyzed"] == 0
        assert result["metadata"]["duplicates_removed"] == 100

    def test_no_api_key_raises(self):
        import os
        env_backup = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="API key"):
                stitch(
                    described=[make_described(1)],
                    preprocess_result=make_preprocess_result(),
                    total_frames=100,
                    processing_time_s=1.0,
                )
        finally:
            if env_backup:
                os.environ["GEMINI_API_KEY"] = env_backup


# ---------------------------------------------------------------------------
# _generate_video_id
# ---------------------------------------------------------------------------

class TestGenerateVideoId:
    def test_starts_with_vid(self):
        assert _generate_video_id().startswith("vid_")

    def test_unique_each_call(self):
        ids = {_generate_video_id() for _ in range(100)}
        assert len(ids) == 100
