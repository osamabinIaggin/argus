"""
Tests for pipeline/preprocessor.py

Requires: ffmpeg and ffprobe installed on PATH.
Uses a synthetically generated test video (no external files needed).
"""

import os
import subprocess
import tempfile
import pytest
from pipeline.preprocessor import (
    probe_video,
    compute_output_resolution,
    preprocess,
    VideoMetadata,
    TARGET_FPS,
    LANDSCAPE_WIDTH,
    LANDSCAPE_HEIGHT,
    PORTRAIT_WIDTH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_test_video(width: int, height: int, duration: int, fps: int, path: str):
    """Generate a synthetic solid-colour test video with FFmpeg."""
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c=blue:size={width}x{height}:rate={fps}",
        "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=44100",
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-y",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, f"Failed to create test video: {result.stderr.decode()}"


# ---------------------------------------------------------------------------
# probe_video
# ---------------------------------------------------------------------------

class TestProbeVideo:
    def test_landscape_1080p(self, tmp_path):
        video = str(tmp_path / "test.mp4")
        make_test_video(1920, 1080, 5, 30, video)
        meta = probe_video(video)

        assert meta.original_width == 1920
        assert meta.original_height == 1080
        assert abs(meta.original_fps - 30.0) < 0.1
        assert meta.duration_seconds == pytest.approx(5.0, abs=0.2)
        assert meta.is_portrait is False

    def test_portrait_9x16(self, tmp_path):
        video = str(tmp_path / "portrait.mp4")
        make_test_video(1080, 1920, 3, 30, video)
        meta = probe_video(video)

        assert meta.original_width == 1080
        assert meta.original_height == 1920
        assert meta.is_portrait is True

    def test_square_video(self, tmp_path):
        video = str(tmp_path / "square.mp4")
        make_test_video(720, 720, 3, 30, video)
        meta = probe_video(video)

        # Square: height == width, not portrait
        assert meta.is_portrait is False

    def test_missing_file_raises(self):
        with pytest.raises(RuntimeError):
            probe_video("/nonexistent/path/video.mp4")


# ---------------------------------------------------------------------------
# compute_output_resolution
# ---------------------------------------------------------------------------

class TestComputeOutputResolution:
    def _meta(self, w, h):
        return VideoMetadata(
            duration_seconds=10,
            original_fps=30,
            original_width=w,
            original_height=h,
            is_portrait=h > w,
        )

    def test_landscape_1080p_fits_within_854x480(self):
        w, h = compute_output_resolution(self._meta(1920, 1080))
        assert w <= LANDSCAPE_WIDTH
        assert h <= LANDSCAPE_HEIGHT
        assert w % 2 == 0
        assert h % 2 == 0
        # Check aspect ratio preserved within 1%
        assert abs((w / h) - (1920 / 1080)) < 0.01

    def test_landscape_720p(self):
        w, h = compute_output_resolution(self._meta(1280, 720))
        assert w <= LANDSCAPE_WIDTH
        assert h <= LANDSCAPE_HEIGHT
        assert w % 2 == 0 and h % 2 == 0

    def test_portrait_1080x1920(self):
        w, h = compute_output_resolution(self._meta(1080, 1920))
        assert w == PORTRAIT_WIDTH
        assert w % 2 == 0 and h % 2 == 0
        # Check aspect ratio preserved
        assert abs((w / h) - (1080 / 1920)) < 0.01

    def test_small_video_not_upscaled(self):
        # A 640x360 video should not be upscaled
        w, h = compute_output_resolution(self._meta(640, 360))
        assert w <= LANDSCAPE_WIDTH
        assert h <= LANDSCAPE_HEIGHT

    def test_output_always_even_dimensions(self):
        # Odd-dimension source — FFmpeg requires even
        w, h = compute_output_resolution(self._meta(1921, 1081))
        assert w % 2 == 0
        assert h % 2 == 0


# ---------------------------------------------------------------------------
# preprocess (integration)
# ---------------------------------------------------------------------------

class TestPreprocess:
    def test_landscape_output_fps_and_resolution(self, tmp_path):
        video = str(tmp_path / "input.mp4")
        make_test_video(1920, 1080, 5, 30, video)

        result = preprocess(video, output_dir=str(tmp_path / "out"))

        assert os.path.exists(result.processed_video_path)

        # Verify output video properties with ffprobe
        meta = probe_video(result.processed_video_path)
        assert abs(meta.original_fps - TARGET_FPS) < 0.5
        assert meta.original_width <= LANDSCAPE_WIDTH
        assert meta.original_height <= LANDSCAPE_HEIGHT

    def test_portrait_output_resolution(self, tmp_path):
        video = str(tmp_path / "portrait.mp4")
        make_test_video(1080, 1920, 3, 30, video)

        result = preprocess(video, output_dir=str(tmp_path / "out"))

        meta = probe_video(result.processed_video_path)
        assert meta.original_width == PORTRAIT_WIDTH

    def test_audio_track_extracted(self, tmp_path):
        video = str(tmp_path / "with_audio.mp4")
        make_test_video(1280, 720, 3, 30, video)

        result = preprocess(video, output_dir=str(tmp_path / "out"))

        assert result.audio_path is not None
        assert os.path.exists(result.audio_path)

    def test_processed_video_has_no_audio_stream(self, tmp_path):
        video = str(tmp_path / "input.mp4")
        make_test_video(1280, 720, 3, 30, video)

        result = preprocess(video, output_dir=str(tmp_path / "out"))

        # Confirm processed video has no audio
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", result.processed_video_path
        ]
        import json, subprocess as sp
        out = sp.run(cmd, capture_output=True, text=True)
        streams = json.loads(out.stdout).get("streams", [])
        audio_streams = [s for s in streams if s["codec_type"] == "audio"]
        assert len(audio_streams) == 0

    def test_metadata_populated_correctly(self, tmp_path):
        video = str(tmp_path / "input.mp4")
        make_test_video(1920, 1080, 5, 30, video)

        result = preprocess(video, output_dir=str(tmp_path / "out"))

        assert result.metadata.original_width == 1920
        assert result.metadata.original_height == 1080
        assert result.processed_width <= LANDSCAPE_WIDTH
        assert result.processed_height <= LANDSCAPE_HEIGHT

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            preprocess("/nonexistent/video.mp4", output_dir=str(tmp_path))

    def test_uses_temp_dir_when_no_output_dir(self, tmp_path):
        video = str(tmp_path / "input.mp4")
        make_test_video(640, 360, 2, 30, video)

        result = preprocess(video)  # no output_dir

        assert os.path.exists(result.processed_video_path)
