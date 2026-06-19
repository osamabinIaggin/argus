"""
Tests for pipeline/keyframe_extractor.py

Uses synthetically generated videos:
- Static: single colour, no motion → minimal keyframes
- Multi-scene: colour changes → hard cut detection
- Slow pan: subtle gradient shift per frame → density fallback triggered
"""

import subprocess
import numpy as np
import pytest
from pipeline.keyframe_extractor import (
    extract_keyframes,
    detect_scenes,
    DENSITY_WINDOW_SECONDS,
    DENSITY_MIN_SCENE_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_static_video(path: str, width=854, height=480, duration=5, fps=15, color="blue"):
    """Single colour, no motion — should produce very few keyframes."""
    cmd = [
        "ffmpeg", "-f", "lavfi",
        "-i", f"color=c={color}:size={width}x{height}:rate={fps}",
        "-t", str(duration), "-c:v", "libx264", "-an", "-y", path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    assert r.returncode == 0, r.stderr.decode()


def make_multiscene_video(path: str, fps=15):
    """
    Two hard-cut scenes: 3s blue, 3s red.
    PySceneDetect should detect a cut at ~3s.
    """
    # Create two colour clips and concat
    cmd = [
        "ffmpeg",
        "-f", "lavfi", "-i", "color=c=blue:size=854x480:rate=15:duration=3",
        "-f", "lavfi", "-i", "color=c=red:size=854x480:rate=15:duration=3",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[out]",
        "-map", "[out]",
        "-c:v", "libx264", "-an", "-y", path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    assert r.returncode == 0, r.stderr.decode()


def make_slow_pan_video(path: str, duration=12, fps=15, width=854, height=480):
    """
    Simulate a slow camera pan: gradual horizontal scroll of a gradient.
    Each frame is slightly different but consecutive diffs are tiny.
    Uses FFmpeg's scroll filter.
    """
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"gradients=size={width*4}x{height}:rate={fps},scroll=h=0.002",
        "-t", str(duration),
        "-vf", f"scale={width}:{height}",
        "-c:v", "libx264", "-an", "-y", path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    assert r.returncode == 0, r.stderr.decode()


# ---------------------------------------------------------------------------
# detect_scenes
# ---------------------------------------------------------------------------

class TestDetectScenes:
    def test_single_scene_static_video(self, tmp_path):
        v = str(tmp_path / "static.mp4")
        make_static_video(v, duration=5)
        scenes = detect_scenes(v)
        assert len(scenes) >= 1
        # Entire video covered
        assert scenes[0][0] == pytest.approx(0.0, abs=0.1)
        assert scenes[-1][1] == pytest.approx(5.0, abs=0.5)

    def test_multiscene_detects_cut(self, tmp_path):
        v = str(tmp_path / "multi.mp4")
        make_multiscene_video(v)
        scenes = detect_scenes(v)
        # Should detect at least 2 scenes (the blue→red hard cut)
        assert len(scenes) >= 2

    def test_scenes_are_contiguous(self, tmp_path):
        v = str(tmp_path / "multi.mp4")
        make_multiscene_video(v)
        scenes = detect_scenes(v)
        for i in range(len(scenes) - 1):
            assert scenes[i][1] == pytest.approx(scenes[i + 1][0], abs=0.1)

    def test_scenes_start_at_zero(self, tmp_path):
        v = str(tmp_path / "static.mp4")
        make_static_video(v, duration=3)
        scenes = detect_scenes(v)
        assert scenes[0][0] == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------------
# extract_keyframes — core behaviour
# ---------------------------------------------------------------------------

class TestExtractKeyframes:
    def test_returns_at_least_one_keyframe(self, tmp_path):
        v = str(tmp_path / "static.mp4")
        make_static_video(v, duration=3)
        kfs = extract_keyframes(v)
        assert len(kfs) >= 1

    def test_keyframe_ids_are_sequential(self, tmp_path):
        v = str(tmp_path / "multi.mp4")
        make_multiscene_video(v)
        kfs = extract_keyframes(v)
        ids = [k.keyframe_id for k in kfs]
        assert ids == list(range(1, len(kfs) + 1))

    def test_timestamps_are_ordered(self, tmp_path):
        v = str(tmp_path / "multi.mp4")
        make_multiscene_video(v)
        kfs = extract_keyframes(v)
        starts = [k.timestamp_start for k in kfs]
        assert starts == sorted(starts)

    def test_timestamp_end_equals_next_start(self, tmp_path):
        v = str(tmp_path / "multi.mp4")
        make_multiscene_video(v)
        kfs = extract_keyframes(v)
        for i in range(len(kfs) - 1):
            assert kfs[i].timestamp_end == pytest.approx(kfs[i + 1].timestamp_start, abs=0.1)

    def test_first_keyframe_starts_near_zero(self, tmp_path):
        v = str(tmp_path / "static.mp4")
        make_static_video(v, duration=3)
        kfs = extract_keyframes(v)
        assert kfs[0].timestamp_start == pytest.approx(0.0, abs=0.2)

    def test_scene_change_flagged_on_cut(self, tmp_path):
        v = str(tmp_path / "multi.mp4")
        make_multiscene_video(v)
        kfs = extract_keyframes(v)
        # First keyframe of each scene should have scene_change=True
        scene_starts = [k for k in kfs if k.scene_change]
        assert len(scene_starts) >= 2

    def test_static_video_low_keyframe_count(self, tmp_path):
        """Static video: pHash dedup should eliminate nearly all frames."""
        v = str(tmp_path / "static.mp4")
        make_static_video(v, duration=5)
        kfs = extract_keyframes(v)
        # 5s static = 75 frames at 15fps, should collapse to very few
        assert len(kfs) <= 5

    def test_each_keyframe_has_image_data(self, tmp_path):
        v = str(tmp_path / "static.mp4")
        make_static_video(v, duration=2)
        kfs = extract_keyframes(v)
        for kf in kfs:
            assert kf.image is not None
            assert isinstance(kf.image, np.ndarray)
            assert kf.image.size > 0

    def test_multiscene_each_scene_has_keyframe(self, tmp_path):
        """Minimum-per-scene guarantee: every scene must contribute at least one keyframe."""
        v = str(tmp_path / "multi.mp4")
        make_multiscene_video(v)
        kfs = extract_keyframes(v)
        scenes_represented = set(k.scene_id for k in kfs)
        # Both scenes (1 and 2) must be in the output
        assert 1 in scenes_represented
        assert 2 in scenes_represented


# ---------------------------------------------------------------------------
# Temporal density fallback
# ---------------------------------------------------------------------------

class TestTemporalDensityFallback:
    def test_slow_pan_gets_adequate_coverage(self, tmp_path):
        """
        Slow pan video: consecutive pHash diffs are tiny.
        Without density fallback most frames would be dropped.
        With it, we expect coverage roughly every DENSITY_WINDOW_SECONDS.
        """
        v = str(tmp_path / "slow_pan.mp4")
        make_slow_pan_video(v, duration=12)
        kfs = extract_keyframes(v)

        # 12s video / 3s window = at least 4 keyframes expected
        expected_min = int(12 / DENSITY_WINDOW_SECONDS)
        assert len(kfs) >= expected_min

    def test_force_sampled_flag_set(self, tmp_path):
        """
        Force-sample triggers on a long static scene where pHash diffs are zero
        and the density fallback must inject keyframes to maintain coverage.
        A scrolling pan generates genuine pHash changes so doesn't need force-sampling —
        this test uses a truly static scene which does.
        """
        v = str(tmp_path / "long_static.mp4")
        make_static_video(v, duration=10)  # well above DENSITY_MIN_SCENE_SECONDS (4s)
        kfs = extract_keyframes(v)
        force_sampled = [k for k in kfs if k.force_sampled]
        assert len(force_sampled) >= 1

    def test_short_static_scene_no_force_sample(self, tmp_path):
        """
        A static scene shorter than DENSITY_MIN_SCENE_SECONDS should not
        trigger force-sampling — it's too short to need it.
        """
        v = str(tmp_path / "short_static.mp4")
        make_static_video(v, duration=3)  # < 4s threshold
        kfs = extract_keyframes(v)
        force_sampled = [k for k in kfs if k.force_sampled]
        assert len(force_sampled) == 0

    def test_timestamps_never_exceed_video_duration(self, tmp_path):
        v = str(tmp_path / "slow_pan.mp4")
        make_slow_pan_video(v, duration=12)
        kfs = extract_keyframes(v)
        for kf in kfs:
            assert kf.timestamp_start >= 0.0
            assert kf.timestamp_end <= 12.5  # small tolerance for encoding
            assert kf.timestamp_start <= kf.timestamp_end
