"""
Tests for pipeline/vision_model.py

All Gemini API calls are mocked — no API key needed.
Integration tests (real API) are marked @pytest.mark.integration.
"""

import json
import numpy as np
import pytest
from unittest.mock import MagicMock, patch, call
from PIL import Image

from pipeline.keyframe_extractor import Keyframe
from pipeline.yolo_analyzer import ScoredKeyframe, YOLOResult
from pipeline.vision_model import (
    describe_keyframes,
    _parse_batch_response,
    _build_batch_parts,
    _call_with_retry,
    _strip_markdown_json,
    _safe_camera_movement,
    _fmt_ts,
    DescribedKeyframe,
    FrameDescription,
    BATCH_SIZE,
    TAIL_SIZE,
    CAMERA_MOVEMENTS,
    MAX_RETRIES,
)
from pipeline._shared import AudioSegment, get_frame_audio_context


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def make_scored(kid: int, scene_id: int = 1, force_sampled: bool = False,
                scene_change: bool = False, objects: list | None = None) -> ScoredKeyframe:
    kf = Keyframe(
        keyframe_id=kid,
        frame_number=kid * 15,
        timestamp_start=float(kid * 3),
        timestamp_end=float(kid * 3 + 3),
        scene_id=scene_id,
        scene_change=scene_change,
        force_sampled=force_sampled,
        image=np.zeros((480, 854, 3), dtype=np.uint8),
    )
    yr = YOLOResult(
        detected_objects=objects or [],
        frame_confidence=0.85 if objects else 0.0,
        yolo_context=f"YOLO detected: {', '.join(objects)}" if objects else "YOLO detected: no objects identified",
    )
    return ScoredKeyframe(keyframe=kf, yolo=yr)


def valid_description(kid: int) -> dict:
    return {
        "keyframe_id": kid,
        "description": f"Frame {kid} description.",
        "camera_movement": "static",
        "actions": "no movement",
        "changes_from_previous": "slight change",
    }


def make_mock_client(response_json: list[dict] | None = None, text: str | None = None):
    """Build a mock genai.Client where .models.generate_content returns given JSON."""
    client = MagicMock()
    response = MagicMock()
    response.text = text if text is not None else json.dumps(response_json or [])
    client.models.generate_content.return_value = response
    return client

# backward-compat alias used throughout tests
make_mock_model = make_mock_client


# ---------------------------------------------------------------------------
# _strip_markdown_json
# ---------------------------------------------------------------------------

class TestStripMarkdownJson:
    def test_plain_json_unchanged(self):
        assert _strip_markdown_json('[{"a": 1}]') == '[{"a": 1}]'

    def test_strips_json_code_fence(self):
        text = '```json\n[{"a": 1}]\n```'
        assert _strip_markdown_json(text) == '[{"a": 1}]'

    def test_strips_plain_code_fence(self):
        text = '```\n[{"a": 1}]\n```'
        assert _strip_markdown_json(text) == '[{"a": 1}]'

    def test_strips_surrounding_whitespace(self):
        assert _strip_markdown_json('  [1]  ') == '[1]'

    def test_multiline_json_preserved(self):
        text = '```json\n[\n  {"a": 1},\n  {"b": 2}\n]\n```'
        result = _strip_markdown_json(text)
        parsed = json.loads(result)
        assert len(parsed) == 2


# ---------------------------------------------------------------------------
# _safe_camera_movement
# ---------------------------------------------------------------------------

class TestSafeCameraMovement:
    def test_valid_values_pass_through(self):
        for v in CAMERA_MOVEMENTS:
            assert _safe_camera_movement(v) == v

    def test_invalid_returns_unknown(self):
        assert _safe_camera_movement("flying") == "unknown"

    def test_case_insensitive(self):
        assert _safe_camera_movement("STATIC") == "static"
        assert _safe_camera_movement("Pan_Left") == "pan_left"

    def test_empty_string_returns_unknown(self):
        assert _safe_camera_movement("") == "unknown"


# ---------------------------------------------------------------------------
# _fmt_ts
# ---------------------------------------------------------------------------

class TestFmtTs:
    def test_zero(self):
        assert _fmt_ts(0.0) == "0:00.00"

    def test_under_one_minute(self):
        assert _fmt_ts(45.5) == "0:45.50"

    def test_over_one_minute(self):
        assert _fmt_ts(90.0) == "1:30.00"

    def test_exact_minute(self):
        assert _fmt_ts(60.0) == "1:00.00"


# ---------------------------------------------------------------------------
# _parse_batch_response
# ---------------------------------------------------------------------------

class TestParseBatchResponse:
    def test_valid_response_all_ids(self):
        raw = json.dumps([valid_description(i) for i in [1, 2, 3]])
        result = _parse_batch_response(raw, [1, 2, 3])
        assert len(result) == 3
        assert [r.keyframe_id for r in result] == [1, 2, 3]

    def test_description_text_preserved(self):
        raw = json.dumps([valid_description(1)])
        result = _parse_batch_response(raw, [1])
        assert result[0].description == "Frame 1 description."

    def test_camera_movement_validated(self):
        item = valid_description(1)
        item["camera_movement"] = "pan_left"
        raw = json.dumps([item])
        result = _parse_batch_response(raw, [1])
        assert result[0].camera_movement == "pan_left"

    def test_invalid_camera_movement_becomes_unknown(self):
        item = valid_description(1)
        item["camera_movement"] = "teleport"
        raw = json.dumps([item])
        result = _parse_batch_response(raw, [1])
        assert result[0].camera_movement == "unknown"

    def test_missing_keyframe_filled_with_defaults(self):
        # Response has frame 1 but not frame 2
        raw = json.dumps([valid_description(1)])
        result = _parse_batch_response(raw, [1, 2])
        assert result[1].keyframe_id == 2
        assert result[1].description == "No description available."

    def test_extra_keyframe_in_response_ignored(self):
        raw = json.dumps([valid_description(1), valid_description(99)])
        result = _parse_batch_response(raw, [1])
        assert len(result) == 1
        assert result[0].keyframe_id == 1

    def test_completely_invalid_json_returns_defaults(self):
        result = _parse_batch_response("this is not json at all", [1, 2])
        assert len(result) == 2
        assert all(r.description == "No description available." for r in result)

    def test_empty_json_array_returns_defaults(self):
        result = _parse_batch_response("[]", [1, 2, 3])
        assert len(result) == 3
        assert all(r.description == "No description available." for r in result)

    def test_json_wrapped_in_markdown_parsed(self):
        raw = f'```json\n{json.dumps([valid_description(1)])}\n```'
        result = _parse_batch_response(raw, [1])
        assert result[0].description == "Frame 1 description."

    def test_non_list_response_returns_defaults(self):
        raw = json.dumps({"error": "oops"})
        result = _parse_batch_response(raw, [1])
        assert result[0].description == "No description available."

    def test_output_order_matches_expected_ids(self):
        # Response in reverse order — output should follow expected_ids order
        raw = json.dumps([valid_description(3), valid_description(2), valid_description(1)])
        result = _parse_batch_response(raw, [1, 2, 3])
        assert [r.keyframe_id for r in result] == [1, 2, 3]


# ---------------------------------------------------------------------------
# _build_batch_parts
# ---------------------------------------------------------------------------

class TestBuildBatchParts:
    def test_returns_list(self):
        batch = [make_scored(1, scene_change=True)]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0)
        assert isinstance(parts, list)
        assert len(parts) > 0

    def test_contains_pil_image_for_each_frame(self):
        batch = [make_scored(i) for i in range(1, 4)]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0)
        pil_count = sum(1 for p in parts if isinstance(p, Image.Image))
        assert pil_count == 3

    def test_no_previous_context_when_first_batch(self):
        batch = [make_scored(1)]
        parts = _build_batch_parts(batch, [], 1, 2, 60.0)
        text_parts = [p for p in parts if isinstance(p, str)]
        combined = "\n".join(text_parts)
        assert "previous batch" not in combined.lower()

    def test_previous_context_included_when_provided(self):
        tail = [FrameDescription(1, "A person walks.", "static", "", "")]
        batch = [make_scored(2)]
        parts = _build_batch_parts(batch, tail, 2, 2, 60.0)
        text_parts = [p for p in parts if isinstance(p, str)]
        combined = "\n".join(text_parts)
        assert "previous" in combined.lower()
        assert "A person walks." in combined

    def test_scene_change_flagged_in_parts(self):
        batch = [make_scored(1, scene_change=True)]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0)
        text_parts = " ".join(p for p in parts if isinstance(p, str))
        assert "scene_change" in text_parts

    def test_force_sampled_flagged_in_parts(self):
        batch = [make_scored(1, force_sampled=True)]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0)
        text_parts = " ".join(p for p in parts if isinstance(p, str))
        assert "force_sampled" in text_parts

    def test_yolo_context_included(self):
        batch = [make_scored(1, objects=["person", "car"])]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0)
        text_parts = " ".join(p for p in parts if isinstance(p, str))
        assert "person" in text_parts
        assert "car" in text_parts

    def test_output_format_instructions_included(self):
        batch = [make_scored(1)]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0)
        text_parts = " ".join(p for p in parts if isinstance(p, str))
        assert "keyframe_id" in text_parts
        assert "camera_movement" in text_parts


# ---------------------------------------------------------------------------
# _call_with_retry
# ---------------------------------------------------------------------------

class TestCallWithRetry:
    def test_success_on_first_attempt(self):
        model = make_mock_model([valid_description(1)])
        result = _call_with_retry(model, ["prompt"])
        assert model.models.generate_content.call_count == 1
        assert "Frame 1" in result

    def test_retries_on_failure_then_succeeds(self):
        model = MagicMock()
        ok_response = MagicMock()
        ok_response.text = json.dumps([valid_description(1)])
        model.models.generate_content.side_effect = [
            Exception("rate limit"),
            ok_response,
        ]
        with patch("pipeline.vision_model.time.sleep"):
            result = _call_with_retry(model, ["prompt"], max_retries=3)
        assert model.models.generate_content.call_count == 2
        assert "Frame 1" in result

    def test_raises_after_all_retries_exhausted(self):
        model = MagicMock()
        model.models.generate_content.side_effect = Exception("always fails")
        with patch("pipeline.vision_model.time.sleep"):
            with pytest.raises(RuntimeError, match="failed after"):
                _call_with_retry(model, ["prompt"], max_retries=3)
        assert model.models.generate_content.call_count == 3

    def test_exponential_backoff_called(self):
        model = MagicMock()
        model.models.generate_content.side_effect = [
            Exception("fail"),
            Exception("fail"),
            MagicMock(text=json.dumps([valid_description(1)])),
        ]
        with patch("pipeline.vision_model.time.sleep") as mock_sleep:
            _call_with_retry(model, ["prompt"], max_retries=3)
        # First retry: sleep(1), second retry: sleep(2)
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    def test_no_sleep_on_final_failure(self):
        model = MagicMock()
        model.models.generate_content.side_effect = Exception("always fails")
        sleep_calls = []
        with patch("pipeline.vision_model.time.sleep", side_effect=lambda x: sleep_calls.append(x)):
            with pytest.raises(RuntimeError):
                _call_with_retry(model, ["prompt"], max_retries=2)
        # 2 attempts: sleep once (before retry 1), not after final failure
        assert len(sleep_calls) == 1


# ---------------------------------------------------------------------------
# describe_keyframes — batching and context carry-over
# ---------------------------------------------------------------------------

class TestDescribeKeyframes:
    def _make_model_for(self, keyframes):
        """Model that returns valid descriptions for whatever IDs it receives."""
        model = MagicMock()
        def side_effect(model=None, contents=None, config=None):
            # Extract keyframe IDs from the text parts
            ids = []
            for p in (contents or []):
                if isinstance(p, str) and "Frame " in p:
                    for token in p.split():
                        token = token.rstrip("–").strip()
                        if token.isdigit():
                            ids.append(int(token))
            # Return valid descriptions for all unique ids found
            unique_ids = list(dict.fromkeys(ids))
            resp = MagicMock()
            resp.text = json.dumps([valid_description(i) for i in unique_ids])
            return resp
        model.models.generate_content.side_effect = side_effect
        return model

    def test_empty_input_returns_empty(self):
        result = describe_keyframes([], client=MagicMock())
        assert result == []

    def test_single_frame_one_batch_call(self):
        frames = [make_scored(1)]
        model = make_mock_model([valid_description(1)])
        result = describe_keyframes(frames, client=model)
        assert model.models.generate_content.call_count == 1
        assert len(result) == 1

    def test_output_length_matches_input(self):
        frames = [make_scored(i) for i in range(1, 11)]
        model = make_mock_model([valid_description(i) for i in range(1, 11)])
        result = describe_keyframes(frames, client=model)
        assert len(result) == len(frames)

    def test_exact_batch_size_is_one_call(self):
        frames = [make_scored(i) for i in range(1, BATCH_SIZE + 1)]
        model = make_mock_model([valid_description(i) for i in range(1, BATCH_SIZE + 1)])
        result = describe_keyframes(frames, client=model, batch_size=BATCH_SIZE)
        assert model.models.generate_content.call_count == 1
        assert len(result) == BATCH_SIZE

    def test_batch_size_plus_one_is_two_calls(self):
        n = BATCH_SIZE + 1
        frames = [make_scored(i) for i in range(1, n + 1)]

        responses = [
            MagicMock(text=json.dumps([valid_description(i) for i in range(1, BATCH_SIZE + 1)])),
            MagicMock(text=json.dumps([valid_description(BATCH_SIZE + 1)])),
        ]
        model = MagicMock()
        model.models.generate_content.side_effect = responses

        result = describe_keyframes(frames, client=model, batch_size=BATCH_SIZE)
        assert model.models.generate_content.call_count == 2
        assert len(result) == n

    def test_correct_number_of_batches(self):
        # 60 frames, batch_size=25 → 3 batches (25+25+10)
        frames = [make_scored(i) for i in range(1, 61)]

        def make_response(model=None, contents=None, config=None):
            ids = []
            for p in (contents or []):
                if isinstance(p, str) and "Frame " in p:
                    for token in p.split():
                        t = token.strip("–,").strip()
                        if t.isdigit():
                            ids.append(int(t))
            unique = list(dict.fromkeys(ids))
            return MagicMock(text=json.dumps([valid_description(i) for i in unique]))

        model = MagicMock()
        model.models.generate_content.side_effect = make_response
        describe_keyframes(frames, client=model, batch_size=25)
        assert model.models.generate_content.call_count == 3

    def test_output_order_matches_input_order(self):
        frames = [make_scored(i) for i in range(1, 6)]
        model = make_mock_model([valid_description(i) for i in range(1, 6)])
        result = describe_keyframes(frames, client=model)
        assert [r.keyframe_id for r in result] == [1, 2, 3, 4, 5]

    def test_returns_described_keyframe_type(self):
        frames = [make_scored(1)]
        model = make_mock_model([valid_description(1)])
        result = describe_keyframes(frames, client=model)
        assert isinstance(result[0], DescribedKeyframe)

    def test_context_carry_over_tail_size(self):
        """Previous batch tail (last TAIL_SIZE descriptions) passed to next batch."""
        frames = [make_scored(i) for i in range(1, BATCH_SIZE + 4)]
        call_parts_log = []

        def capture(model=None, contents=None, config=None):
            parts = contents or []
            call_parts_log.append(parts)
            return MagicMock(text=json.dumps([
                valid_description(i)
                for p in parts if isinstance(p, str)
                for token in p.split()
                if token.rstrip("–").isdigit()
                for i in [int(token.rstrip("–"))]
                if 1 <= i <= BATCH_SIZE + 3
            ][:BATCH_SIZE] or [valid_description(1)]))

        model = MagicMock()
        model.models.generate_content.side_effect = capture

        describe_keyframes(frames, client=model, batch_size=BATCH_SIZE)

        # Batch 2's parts should contain "previous batch" context
        batch2_parts = call_parts_log[1]
        text_parts = " ".join(p for p in batch2_parts if isinstance(p, str))
        assert "previous" in text_parts.lower()

    def test_all_frames_have_descriptions_despite_partial_response(self):
        """If API returns fewer descriptions than frames, defaults fill the gaps."""
        frames = [make_scored(i) for i in range(1, 6)]
        # API only returns description for frame 1
        model = make_mock_model([valid_description(1)])
        result = describe_keyframes(frames, client=model)
        assert len(result) == 5
        # Missing frames get default description
        assert result[4].frame_desc.description == "No description available."

    def test_scored_keyframe_data_preserved(self):
        """ScoredKeyframe attributes accessible through DescribedKeyframe."""
        frames = [make_scored(1, scene_change=True, objects=["person"])]
        model = make_mock_model([valid_description(1)])
        result = describe_keyframes(frames, client=model)
        dk = result[0]
        assert dk.scene_change is True
        assert "person" in dk.detected_objects
        assert dk.image is not None

    def test_no_api_key_raises_value_error(self):
        """Calling without API key and no env var raises clearly."""
        import os
        env_backup = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="API key"):
                describe_keyframes([make_scored(1)])
        finally:
            if env_backup:
                os.environ["GEMINI_API_KEY"] = env_backup

    def test_custom_batch_size_respected(self):
        frames = [make_scored(i) for i in range(1, 7)]
        call_count_tracker = []

        def track(model=None, contents=None, config=None):
            parts = contents or []
            call_count_tracker.append(1)
            # Count image parts to determine batch size for this call
            img_count = sum(1 for p in parts if isinstance(p, Image.Image))
            return MagicMock(text=json.dumps([
                valid_description(i) for i in range(1, img_count + 1)
            ]))

        model = MagicMock()
        model.models.generate_content.side_effect = track
        describe_keyframes(frames, client=model, batch_size=3)
        # 6 frames / 3 per batch = 2 calls
        assert model.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# _build_batch_parts — audio injection
# ---------------------------------------------------------------------------

def make_audio_seg(start, end, content, seg_type="speech") -> AudioSegment:
    return AudioSegment(start=start, end=end, content=content, segment_type=seg_type)


class TestBuildBatchPartsAudio:
    def test_no_audio_segments_produces_same_output(self):
        batch = [make_scored(1)]
        parts_no_audio  = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=None)
        parts_empty_list = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=[])
        # Neither should contain "Audio:"
        for parts in (parts_no_audio, parts_empty_list):
            text = " ".join(p for p in parts if isinstance(p, str))
            assert "Audio:" not in text

    def test_overlapping_audio_injected_into_frame_text(self):
        # Frame 1 covers [3.0 → 6.0]; segment covers [2.0 → 5.0]
        batch = [make_scored(1)]   # ts_start=3.0, ts_end=6.0
        segs = [make_audio_seg(2.0, 5.0, "'relax your arm'")]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=segs)
        text = " ".join(p for p in parts if isinstance(p, str))
        assert "Audio:" in text
        assert "'relax your arm'" in text

    def test_non_overlapping_audio_not_injected(self):
        # Frame 1 covers [3.0 → 6.0]; segment is at [10.0 → 15.0]
        batch = [make_scored(1)]
        segs = [make_audio_seg(10.0, 15.0, "distant speech")]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=segs)
        text = " ".join(p for p in parts if isinstance(p, str))
        assert "distant speech" not in text

    def test_silence_audio_not_injected(self):
        batch = [make_scored(1)]
        segs = [make_audio_seg(3.0, 6.0, "silence", seg_type="silence")]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=segs)
        text = " ".join(p for p in parts if isinstance(p, str))
        assert "silence" not in text.lower() or "Audio:" not in text

    def test_multiple_overlapping_segments_all_injected(self):
        batch = [make_scored(1)]   # ts_start=3.0, ts_end=6.0
        segs = [
            make_audio_seg(2.0, 5.0, "HVAC hum", seg_type="ambient"),
            make_audio_seg(3.5, 4.5, "'hold still'", seg_type="speech"),
        ]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=segs)
        text = " ".join(p for p in parts if isinstance(p, str))
        assert "HVAC hum" in text
        assert "'hold still'" in text

    def test_audio_injected_per_frame_independently(self):
        # Frame 1 [3→6] overlaps seg A; Frame 2 [6→9] overlaps seg B
        batch = [make_scored(1), make_scored(2)]
        segs = [
            make_audio_seg(3.0, 6.0, "snap", seg_type="event"),
            make_audio_seg(6.0, 9.0, "heartbeat", seg_type="event"),
        ]
        parts = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=segs)
        text_parts = [p for p in parts if isinstance(p, str)]
        # Both audio contents must appear
        combined = " ".join(text_parts)
        assert "snap" in combined
        assert "heartbeat" in combined

    def test_image_count_unchanged_with_audio(self):
        # Audio injection must not add or remove image parts
        batch = [make_scored(i) for i in range(1, 4)]
        segs = [make_audio_seg(0.0, 30.0, "background music", seg_type="music")]
        parts_with    = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=segs)
        parts_without = _build_batch_parts(batch, [], 1, 1, 30.0, audio_segments=None)
        imgs_with    = sum(1 for p in parts_with    if isinstance(p, Image.Image))
        imgs_without = sum(1 for p in parts_without if isinstance(p, Image.Image))
        assert imgs_with == imgs_without == 3


# ---------------------------------------------------------------------------
# describe_keyframes — audio_segments parameter
# ---------------------------------------------------------------------------

class TestDescribeKeyframesAudio:
    def test_audio_segments_none_backward_compatible(self):
        frames = [make_scored(1)]
        model = make_mock_model([valid_description(1)])
        result = describe_keyframes(frames, client=model)   # no audio_segments kwarg
        assert len(result) == 1

    def test_audio_segments_empty_list_backward_compatible(self):
        frames = [make_scored(1)]
        model = make_mock_model([valid_description(1)])
        result = describe_keyframes(frames, client=model, audio_segments=[])
        assert len(result) == 1

    def test_audio_segments_injected_into_prompt(self):
        frames = [make_scored(1)]   # ts_start=3.0, ts_end=6.0
        segs = [make_audio_seg(2.0, 7.0, "needle click", seg_type="event")]
        captured_parts = []

        def capture(model=None, contents=None, config=None):
            captured_parts.extend(contents or [])
            return MagicMock(text=json.dumps([valid_description(1)]))

        client = MagicMock()
        client.models.generate_content.side_effect = capture
        describe_keyframes(frames, client=client, audio_segments=segs)

        text = " ".join(p for p in captured_parts if isinstance(p, str))
        assert "needle click" in text

    def test_audio_from_different_window_not_injected(self):
        frames = [make_scored(1)]   # ts_start=3.0, ts_end=6.0
        segs = [make_audio_seg(20.0, 25.0, "distant speech", seg_type="speech")]
        captured_parts = []

        def capture(model=None, contents=None, config=None):
            captured_parts.extend(contents or [])
            return MagicMock(text=json.dumps([valid_description(1)]))

        client = MagicMock()
        client.models.generate_content.side_effect = capture
        describe_keyframes(frames, client=client, audio_segments=segs)

        text = " ".join(p for p in captured_parts if isinstance(p, str))
        assert "distant speech" not in text


# ---------------------------------------------------------------------------
# _safe_camera_movement — compound values (Fix 2)
# ---------------------------------------------------------------------------

class TestSafeCameraMovementCompound:
    def test_compound_comma_returns_first_valid(self):
        assert _safe_camera_movement("pan_right, tilt_down") == "pan_right"

    def test_compound_slash_returns_first_valid(self):
        assert _safe_camera_movement("zoom_in/pan_left") == "zoom_in"

    def test_all_invalid_tokens_returns_unknown(self):
        assert _safe_camera_movement("sideways, diagonal") == "unknown"

    def test_leading_invalid_token_skipped(self):
        assert _safe_camera_movement("sideways, static") == "static"

    def test_whitespace_only_delimiter_handled(self):
        assert _safe_camera_movement("pan_left tilt_up") == "pan_left"


# ---------------------------------------------------------------------------
# describe_keyframes — batch parse-failure retry (Fix 1)
# ---------------------------------------------------------------------------

class TestDescribeKeyframesBatchRetry:
    """Batch-level retry fires on total JSON parse failure, not on ID mismatch."""

    def _make_empty_response(self):
        """Simulate a truncated/unparseable response."""
        return MagicMock(text="not valid json [[[")

    def _make_valid_response(self, ids):
        return MagicMock(text=json.dumps([valid_description(i) for i in ids]))

    def test_retries_once_on_empty_json(self):
        """Empty JSON response triggers exactly one retry (2 total calls)."""
        frames = [make_scored(i) for i in range(1, 4)]
        responses = [self._make_empty_response(), self._make_valid_response([1, 2, 3])]
        client = MagicMock()
        client.models.generate_content.side_effect = responses

        with patch("pipeline.vision_model.time.sleep"):
            result = describe_keyframes(frames, client=client)

        assert client.models.generate_content.call_count == 2
        assert all(dk.frame_desc.description != "No description available." for dk in result)

    def test_no_retry_on_valid_json_with_wrong_ids(self):
        """Valid JSON list (wrong IDs) is accepted without retry — retrying won't help."""
        frames = [make_scored(i) for i in range(1, 4)]
        # Response has IDs 99/98/97 — completely wrong, but valid JSON
        wrong_ids_resp = MagicMock(text=json.dumps([valid_description(i) for i in [99, 98, 97]]))
        client = MagicMock()
        client.models.generate_content.return_value = wrong_ids_resp

        result = describe_keyframes(frames, client=client)

        # Exactly 1 call — no retry triggered
        assert client.models.generate_content.call_count == 1
        # Frames fall back to defaults (IDs not found) but that's expected behaviour
        assert all(dk.frame_desc.description == "No description available." for dk in result)

    def test_degraded_result_accepted_after_retry_also_fails(self):
        """If both attempts return empty JSON, pipeline still completes with defaults."""
        frames = [make_scored(i) for i in range(1, 3)]
        client = MagicMock()
        client.models.generate_content.return_value = self._make_empty_response()

        with patch("pipeline.vision_model.time.sleep"):
            result = describe_keyframes(frames, client=client)

        # 2 calls (original + 1 retry), then gives up
        assert client.models.generate_content.call_count == 2
        assert all(dk.frame_desc.description == "No description available." for dk in result)
