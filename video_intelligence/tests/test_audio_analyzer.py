"""
Tests for pipeline/audio_analyzer.py and pipeline/_shared.py

All Gemini API calls are mocked — no API key needed.
Integration tests (real API) are marked @pytest.mark.integration.
"""

import json
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from pipeline._shared import AudioSegment, get_frame_audio_context
from pipeline.audio_analyzer import (
    analyze_audio,
    _detect_mime,
    _parse_audio_response,
    VALID_TYPES,
    MAX_FILE_BYTES,
    AUDIO_MODEL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_segment(
    start: float,
    end: float,
    content: str = "test audio",
    seg_type: str = "speech",
) -> AudioSegment:
    return AudioSegment(start=start, end=end, content=content, segment_type=seg_type)


def make_raw_segment(start, end, content="test audio", seg_type="speech") -> dict:
    return {"start": start, "end": end, "content": content, "type": seg_type}


def make_mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.text = response_text
    client.models.generate_content.return_value = response
    return client


def make_audio_file(tmp_path, content: bytes = b"fake audio", name: str = "audio.aac") -> str:
    path = str(tmp_path / name)
    with open(path, "wb") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# _detect_mime
# ---------------------------------------------------------------------------

class TestDetectMime:
    def test_aac(self):
        assert _detect_mime("audio.aac") == "audio/aac"

    def test_mp3(self):
        assert _detect_mime("track.mp3") == "audio/mpeg"

    def test_wav(self):
        assert _detect_mime("sound.wav") == "audio/wav"

    def test_ogg(self):
        assert _detect_mime("audio.ogg") == "audio/ogg"

    def test_opus(self):
        assert _detect_mime("audio.opus") == "audio/ogg"

    def test_flac(self):
        assert _detect_mime("audio.flac") == "audio/flac"

    def test_m4a(self):
        assert _detect_mime("audio.m4a") == "audio/mp4"

    def test_webm(self):
        assert _detect_mime("audio.webm") == "audio/webm"

    def test_unknown_extension_falls_back_to_aac(self):
        assert _detect_mime("audio.xyz") == "audio/aac"

    def test_no_extension_falls_back_to_aac(self):
        assert _detect_mime("audiofile") == "audio/aac"

    def test_uppercase_extension(self):
        assert _detect_mime("audio.AAC") == "audio/aac"
        assert _detect_mime("track.MP3") == "audio/mpeg"

    def test_full_path(self):
        assert _detect_mime("/tmp/output/video_audio.aac") == "audio/aac"


# ---------------------------------------------------------------------------
# _parse_audio_response
# ---------------------------------------------------------------------------

class TestParseAudioResponse:
    def test_valid_single_segment(self):
        raw = json.dumps([make_raw_segment(0.0, 5.0, "Hello world", "speech")])
        result = _parse_audio_response(raw, duration=60.0)
        assert len(result) == 1
        assert result[0].start == 0.0
        assert result[0].end == 5.0
        assert result[0].content == "Hello world"
        assert result[0].segment_type == "speech"

    def test_valid_multiple_segments(self):
        raw = json.dumps([
            make_raw_segment(0.0, 3.0, "Speech here", "speech"),
            make_raw_segment(3.0, 5.0, "Car engine", "event"),
            make_raw_segment(5.0, 10.0, "HVAC hum", "ambient"),
        ])
        result = _parse_audio_response(raw, duration=60.0)
        assert len(result) == 3
        assert result[0].segment_type == "speech"
        assert result[1].segment_type == "event"
        assert result[2].segment_type == "ambient"

    def test_all_valid_types_accepted(self):
        for seg_type in VALID_TYPES:
            raw = json.dumps([make_raw_segment(0.0, 1.0, "content", seg_type)])
            result = _parse_audio_response(raw, duration=60.0)
            assert len(result) == 1
            assert result[0].segment_type == seg_type

    def test_unknown_type_mapped_to_event(self):
        raw = json.dumps([make_raw_segment(0.0, 5.0, "some sound", "noise")])
        result = _parse_audio_response(raw, duration=60.0)
        assert result[0].segment_type == "event"

    def test_empty_type_mapped_to_event(self):
        raw = json.dumps([{"start": 0.0, "end": 5.0, "content": "sound", "type": ""}])
        result = _parse_audio_response(raw, duration=60.0)
        assert result[0].segment_type == "event"

    def test_invalid_json_returns_empty(self):
        assert _parse_audio_response("not json at all", duration=60.0) == []

    def test_non_list_json_returns_empty(self):
        assert _parse_audio_response(json.dumps({"error": "bad"}), duration=60.0) == []

    def test_empty_array_returns_empty(self):
        assert _parse_audio_response("[]", duration=60.0) == []

    def test_markdown_fence_stripped(self):
        raw = f'```json\n{json.dumps([make_raw_segment(0.0, 5.0)])}\n```'
        result = _parse_audio_response(raw, duration=60.0)
        assert len(result) == 1

    def test_inverted_timestamps_discarded(self):
        raw = json.dumps([make_raw_segment(5.0, 2.0)])   # end < start
        assert _parse_audio_response(raw, duration=60.0) == []

    def test_equal_timestamps_discarded(self):
        raw = json.dumps([make_raw_segment(3.0, 3.0)])   # end == start
        assert _parse_audio_response(raw, duration=60.0) == []

    def test_negative_start_clamped_to_zero(self):
        raw = json.dumps([make_raw_segment(-2.0, 5.0)])
        result = _parse_audio_response(raw, duration=60.0)
        assert result[0].start == 0.0
        assert result[0].end == 5.0

    def test_end_beyond_duration_clamped(self):
        raw = json.dumps([make_raw_segment(55.0, 70.0)])
        result = _parse_audio_response(raw, duration=60.0)
        assert result[0].end == 60.0

    def test_end_within_1s_tolerance_not_discarded(self):
        # 60.5 is within +1s of duration=60.0 — clamped to 60.0, still valid
        raw = json.dumps([make_raw_segment(58.0, 60.5)])
        result = _parse_audio_response(raw, duration=60.0)
        assert len(result) == 1

    def test_empty_content_discarded(self):
        raw = json.dumps([{"start": 0.0, "end": 5.0, "content": "", "type": "speech"}])
        assert _parse_audio_response(raw, duration=60.0) == []

    def test_whitespace_only_content_discarded(self):
        raw = json.dumps([{"start": 0.0, "end": 5.0, "content": "   ", "type": "speech"}])
        assert _parse_audio_response(raw, duration=60.0) == []

    def test_non_dict_items_skipped(self):
        raw = json.dumps(["string", 42, None, make_raw_segment(0.0, 5.0)])
        result = _parse_audio_response(raw, duration=60.0)
        assert len(result) == 1

    def test_unparseable_numeric_fields_skipped(self):
        raw = json.dumps([{"start": "not_a_number", "end": 5.0, "content": "x", "type": "speech"}])
        assert _parse_audio_response(raw, duration=60.0) == []

    def test_sorted_by_start_time(self):
        raw = json.dumps([
            make_raw_segment(10.0, 15.0, "late"),
            make_raw_segment(0.0, 5.0, "early"),
            make_raw_segment(5.0, 10.0, "middle"),
        ])
        result = _parse_audio_response(raw, duration=60.0)
        starts = [s.start for s in result]
        assert starts == sorted(starts)

    def test_mixed_valid_and_invalid_keeps_valid(self):
        raw = json.dumps([
            make_raw_segment(0.0, 5.0, "valid"),
            {"start": "bad", "end": 10.0, "content": "invalid", "type": "speech"},
            make_raw_segment(5.0, 10.0, "also valid"),
        ])
        result = _parse_audio_response(raw, duration=60.0)
        assert len(result) == 2

    def test_timestamps_rounded_to_3_decimal_places(self):
        raw = json.dumps([make_raw_segment(1.23456789, 5.98765432)])
        result = _parse_audio_response(raw, duration=60.0)
        assert result[0].start == round(1.23456789, 3)
        assert result[0].end == round(5.98765432, 3)

    def test_infinite_duration_no_clamping(self):
        # When duration is inf, end timestamps should not be clamped
        raw = json.dumps([make_raw_segment(0.0, 9999.0)])
        result = _parse_audio_response(raw, duration=float("inf"))
        assert result[0].end == 9999.0

    def test_missing_fields_use_defaults_then_validate(self):
        # Missing start defaults to 0, missing end defaults to 0 → end(0) <= start(0) → discarded
        raw = json.dumps([{"content": "no timestamps", "type": "speech"}])
        assert _parse_audio_response(raw, duration=60.0) == []


# ---------------------------------------------------------------------------
# get_frame_audio_context
# ---------------------------------------------------------------------------

class TestGetFrameAudioContext:
    def test_no_segments_returns_empty(self):
        assert get_frame_audio_context([], 0.0, 5.0) == ""

    def test_non_overlapping_before_returns_empty(self):
        segments = [make_segment(0.0, 3.0, "before")]
        assert get_frame_audio_context(segments, 5.0, 8.0) == ""

    def test_non_overlapping_after_returns_empty(self):
        segments = [make_segment(10.0, 15.0, "after")]
        assert get_frame_audio_context(segments, 0.0, 5.0) == ""

    def test_exact_boundary_end_equals_start_excluded(self):
        # segment ends exactly when frame starts — no overlap
        segments = [make_segment(0.0, 3.0, "before")]
        assert get_frame_audio_context(segments, 3.0, 6.0) == ""

    def test_exact_boundary_start_equals_end_excluded(self):
        # segment starts exactly when frame ends — no overlap
        segments = [make_segment(6.0, 9.0, "after")]
        assert get_frame_audio_context(segments, 3.0, 6.0) == ""

    def test_fully_contained_overlap(self):
        # segment entirely within frame window
        segments = [make_segment(1.0, 2.0, "Hello world")]
        result = get_frame_audio_context(segments, 0.0, 5.0)
        assert result == "Audio: Hello world"

    def test_segment_spans_frame_window(self):
        # segment starts before and ends after the frame
        segments = [make_segment(0.0, 10.0, "long ambient")]
        result = get_frame_audio_context(segments, 3.0, 6.0)
        assert result == "Audio: long ambient"

    def test_partial_overlap_start(self):
        # segment starts before frame, ends inside
        segments = [make_segment(1.0, 5.0, "overlapping")]
        result = get_frame_audio_context(segments, 3.0, 8.0)
        assert result == "Audio: overlapping"

    def test_partial_overlap_end(self):
        # segment starts inside frame, ends after
        segments = [make_segment(5.0, 10.0, "overlapping")]
        result = get_frame_audio_context(segments, 3.0, 7.0)
        assert result == "Audio: overlapping"

    def test_silence_excluded(self):
        segments = [make_segment(0.0, 5.0, "silence", seg_type="silence")]
        assert get_frame_audio_context(segments, 0.0, 5.0) == ""

    def test_silence_excluded_but_others_included(self):
        segments = [
            make_segment(0.0, 3.0, "silence", seg_type="silence"),
            make_segment(1.0, 4.0, "dog barking", seg_type="event"),
        ]
        result = get_frame_audio_context(segments, 0.0, 5.0)
        assert "dog barking" in result
        assert "silence" not in result

    def test_multiple_overlapping_joined_with_semicolons(self):
        segments = [
            make_segment(0.0, 5.0, "HVAC hum", seg_type="ambient"),
            make_segment(1.0, 3.0, "'relax your arm'", seg_type="speech"),
            make_segment(2.5, 4.0, "glove snap", seg_type="event"),
        ]
        result = get_frame_audio_context(segments, 0.0, 5.0)
        assert result.startswith("Audio: ")
        assert "HVAC hum" in result
        assert "'relax your arm'" in result
        assert "glove snap" in result
        assert "; " in result

    def test_prefix_is_audio_colon(self):
        segments = [make_segment(0.0, 5.0, "content")]
        result = get_frame_audio_context(segments, 0.0, 5.0)
        assert result.startswith("Audio: ")

    def test_all_silence_returns_empty(self):
        segments = [
            make_segment(0.0, 5.0, "silence", seg_type="silence"),
            make_segment(5.0, 10.0, "silence", seg_type="silence"),
        ]
        assert get_frame_audio_context(segments, 0.0, 10.0) == ""

    def test_zero_length_frame_window_no_overlap(self):
        segments = [make_segment(0.0, 5.0, "content")]
        # ts_start == ts_end: no segment can satisfy start < ts_end AND end > ts_start
        # when ts_start == ts_end == 3.0: need start < 3.0 AND end > 3.0 — this DOES overlap
        # (a zero-length point at 3.0 is inside a segment [0, 5])
        result = get_frame_audio_context(segments, 3.0, 3.0)
        # 0.0 < 3.0 AND 5.0 > 3.0 → overlaps
        assert result == "Audio: content"

    def test_music_segment_included(self):
        segments = [make_segment(0.0, 30.0, "upbeat electronic music", seg_type="music")]
        result = get_frame_audio_context(segments, 5.0, 10.0)
        assert "upbeat electronic music" in result


# ---------------------------------------------------------------------------
# analyze_audio — null / early-exit paths (no API call)
# ---------------------------------------------------------------------------

class TestAnalyzeAudioEarlyExits:
    def test_none_audio_path_returns_empty(self):
        assert analyze_audio(None) == []

    def test_empty_string_path_returns_empty(self):
        assert analyze_audio("") == []

    def test_nonexistent_file_returns_empty(self):
        assert analyze_audio("/nonexistent/audio.aac") == []

    def test_empty_file_returns_empty(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"", name="empty.aac")
        assert analyze_audio(path) == []

    def test_file_too_large_returns_empty(self, tmp_path, monkeypatch):
        path = make_audio_file(tmp_path, content=b"x", name="audio.aac")
        monkeypatch.setattr("pipeline.audio_analyzer.MAX_FILE_BYTES", 0)
        assert analyze_audio(path) == []

    def test_no_api_key_returns_empty_not_raises(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio data", name="audio.aac")
        env_backup = os.environ.pop("GEMINI_API_KEY", None)
        try:
            # No key — should return [] rather than propagating ValueError
            result = analyze_audio(path)
            assert result == []
        finally:
            if env_backup:
                os.environ["GEMINI_API_KEY"] = env_backup


# ---------------------------------------------------------------------------
# analyze_audio — with mocked client
# ---------------------------------------------------------------------------

class TestAnalyzeAudioWithMock:
    def _valid_response(self, segments: list[dict]) -> str:
        return json.dumps(segments)

    def test_returns_list_of_audio_segments(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(self._valid_response([
            make_raw_segment(0.0, 5.0, "Hello", "speech"),
        ]))
        result = analyze_audio(path, client=client)
        assert isinstance(result, list)
        assert all(isinstance(s, AudioSegment) for s in result)

    def test_correct_segment_data_returned(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(self._valid_response([
            make_raw_segment(1.0, 4.0, "engine revving", "event"),
        ]))
        result = analyze_audio(path, client=client)
        assert result[0].content == "engine revving"
        assert result[0].segment_type == "event"
        assert result[0].start == 1.0
        assert result[0].end == 4.0

    def test_multiple_segments_returned_sorted(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(self._valid_response([
            make_raw_segment(10.0, 15.0, "late event", "event"),
            make_raw_segment(0.0, 5.0, "early speech", "speech"),
        ]))
        result = analyze_audio(path, client=client)
        assert result[0].start < result[1].start

    def test_api_call_made_once(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(self._valid_response([
            make_raw_segment(0.0, 5.0),
        ]))
        analyze_audio(path, client=client)
        assert client.models.generate_content.call_count == 1

    def test_audio_model_used(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(self._valid_response([
            make_raw_segment(0.0, 5.0),
        ]))
        analyze_audio(path, client=client)
        call_kwargs = client.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == AUDIO_MODEL

    def test_api_failure_returns_empty_not_raises(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = MagicMock()
        client.models.generate_content.side_effect = Exception("network error")
        with patch("pipeline.vision_model.time.sleep"):
            result = analyze_audio(path, client=client)
        assert result == []

    def test_malformed_api_response_returns_empty(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client("this is not json")
        result = analyze_audio(path, client=client)
        assert result == []

    def test_duration_passed_to_parser_for_clamping(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        # Segment end (70.0) exceeds duration (52.0) — should be clamped
        client = make_mock_client(self._valid_response([
            make_raw_segment(40.0, 70.0, "late speech", "speech"),
        ]))
        result = analyze_audio(path, duration=52.0, client=client)
        assert result[0].end == 52.0

    def test_silence_segments_parsed_and_returned(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(self._valid_response([
            make_raw_segment(0.0, 3.0, "silence", "silence"),
            make_raw_segment(3.0, 8.0, "conversation", "speech"),
        ]))
        result = analyze_audio(path, client=client)
        # analyze_audio returns all segments including silence
        # (silence is only filtered out at get_frame_audio_context level)
        types_found = {s.segment_type for s in result}
        assert "silence" in types_found
        assert "speech" in types_found

    def test_empty_described_list_returned_on_empty_api_response(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client("[]")
        result = analyze_audio(path, client=client)
        assert result == []

    def test_config_uses_json_mime_type(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(self._valid_response([make_raw_segment(0.0, 1.0)]))
        analyze_audio(path, client=client)
        call_kwargs = client.models.generate_content.call_args
        config = call_kwargs.kwargs["config"]
        assert config.response_mime_type == "application/json"


# ---------------------------------------------------------------------------
# Integration: analyze_audio → get_frame_audio_context pipeline
# ---------------------------------------------------------------------------

class TestAudioPipeline:
    """End-to-end: mocked API → segments → frame context."""

    def test_speech_injected_into_correct_frame_window(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(json.dumps([
            {"start": 5.0, "end": 10.0, "content": "'relax your arm'", "type": "speech"},
            {"start": 0.0, "end": 5.0, "content": "HVAC hum", "type": "ambient"},
        ]))
        segments = analyze_audio(path, duration=60.0, client=client)

        # Frame [4.0 → 8.0] overlaps both segments
        ctx = get_frame_audio_context(segments, 4.0, 8.0)
        assert "'relax your arm'" in ctx
        assert "HVAC hum" in ctx

    def test_speech_not_injected_outside_frame_window(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(json.dumps([
            {"start": 20.0, "end": 25.0, "content": "'you will feel a pinch'", "type": "speech"},
        ]))
        segments = analyze_audio(path, duration=60.0, client=client)

        # Frame at 0-5s should NOT receive the speech at 20-25s
        ctx = get_frame_audio_context(segments, 0.0, 5.0)
        assert ctx == ""

    def test_no_audio_path_produces_no_context(self):
        segments = analyze_audio(None)
        ctx = get_frame_audio_context(segments, 0.0, 30.0)
        assert ctx == ""

    def test_silence_not_injected_into_frame(self, tmp_path):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(json.dumps([
            {"start": 0.0, "end": 10.0, "content": "silence", "type": "silence"},
        ]))
        segments = analyze_audio(path, duration=60.0, client=client)
        ctx = get_frame_audio_context(segments, 0.0, 10.0)
        assert ctx == ""


# ---------------------------------------------------------------------------
# analyze_audio — dynamic token budget (Fix 5)
# ---------------------------------------------------------------------------

class TestAnalyzeAudioTokenBudget:
    """token_budget scales with duration and is safely bounded."""

    def _run_and_capture_config(self, tmp_path, duration):
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(json.dumps([make_raw_segment(0.0, 1.0)]))
        analyze_audio(path, duration=duration, client=client)
        call_kwargs = client.models.generate_content.call_args
        return call_kwargs.kwargs["config"]

    def test_short_clip_uses_minimum(self, tmp_path):
        # 10s * 150 = 1500 < 4000 → budget = 4000 (MAX_TOKENS floor)
        config = self._run_and_capture_config(tmp_path, 10.0)
        assert config.max_output_tokens == 4_000

    def test_medium_clip_scales_up(self, tmp_path):
        # 40s * 150 = 6000 → between floor(4000) and ceiling(16000) → budget = 6000
        config = self._run_and_capture_config(tmp_path, 40.0)
        assert config.max_output_tokens == 6_000

    def test_long_clip_capped_at_ceiling(self, tmp_path):
        # 2000s * 150 = 300000 > 16000 → capped at 16000
        config = self._run_and_capture_config(tmp_path, 2_000.0)
        assert config.max_output_tokens == 16_000

    def test_inf_duration_uses_ceiling(self, tmp_path):
        # float("inf") → finite_dur = 1200 → 1200*150 = 180000 → capped at 16000
        config = self._run_and_capture_config(tmp_path, float("inf"))
        assert config.max_output_tokens == 16_000

    def test_inf_duration_does_not_crash(self, tmp_path):
        # Regression: int(inf * 15) previously raised OverflowError → return []
        path = make_audio_file(tmp_path, content=b"audio")
        client = make_mock_client(json.dumps([make_raw_segment(0.0, 5.0)]))
        result = analyze_audio(path, client=client)   # duration defaults to inf
        assert len(result) == 1
