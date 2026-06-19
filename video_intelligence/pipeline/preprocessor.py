from __future__ import annotations
"""
Stage 2: FFmpeg preprocessing.
- Reduces to 5fps (configurable via target_fps)
- Resizes: 854x480 landscape / 640px wide portrait (maintains aspect ratio)
- Strips audio to separate track
- Returns paths to processed video and audio track
"""

import subprocess
import tempfile
import json
import os
from pathlib import Path
from dataclasses import dataclass


TARGET_FPS = 10
LANDSCAPE_WIDTH = 1280
LANDSCAPE_HEIGHT = 720
PORTRAIT_WIDTH = 640


@dataclass
class VideoMetadata:
    duration_seconds: float
    original_fps: float
    original_width: int
    original_height: int
    is_portrait: bool


@dataclass
class PreprocessResult:
    processed_video_path: str
    audio_path: str | None
    metadata: VideoMetadata
    processed_width: int
    processed_height: int
    processed_fps: int


def probe_video(input_path: str) -> VideoMetadata:
    """Extract video metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)

    video_stream = next(
        (s for s in data["streams"] if s["codec_type"] == "video"), None
    )
    if not video_stream:
        raise ValueError("No video stream found in file")

    # Parse fps — stored as a fraction string e.g. "30000/1001"
    fps_raw = video_stream.get("r_frame_rate", "30/1")
    num, den = fps_raw.split("/")
    fps = float(num) / float(den)

    width = int(video_stream["width"])
    height = int(video_stream["height"])
    duration = float(data["format"].get("duration", 0))

    return VideoMetadata(
        duration_seconds=duration,
        original_fps=round(fps, 3),
        original_width=width,
        original_height=height,
        is_portrait=height > width,
    )


def compute_output_resolution(metadata: VideoMetadata) -> tuple[int, int]:
    """
    Compute target resolution maintaining aspect ratio.
    Landscape: fit within 854x480
    Portrait: fit width to 640px
    """
    w, h = metadata.original_width, metadata.original_height

    if metadata.is_portrait:
        target_w = PORTRAIT_WIDTH
        target_h = int(h * (target_w / w))
        # Ensure dimensions are divisible by 2 (FFmpeg requirement)
        target_h = target_h if target_h % 2 == 0 else target_h + 1
        return target_w, target_h
    else:
        # Landscape: scale down to fit 854x480
        scale = min(LANDSCAPE_WIDTH / w, LANDSCAPE_HEIGHT / h)
        target_w = int(w * scale)
        target_h = int(h * scale)
        target_w = target_w if target_w % 2 == 0 else target_w + 1
        target_h = target_h if target_h % 2 == 0 else target_h + 1
        return target_w, target_h


def preprocess(
    input_path: str,
    output_dir: str | None = None,
    target_fps: int = TARGET_FPS,
) -> PreprocessResult:
    """
    Run FFmpeg preprocessing on a video file.

    Args:
        input_path: Path to the input video file.
        output_dir: Directory for output files. Uses a temp dir if not provided.
        target_fps: Output frame rate (default TARGET_FPS=15). Use a lower value
                    such as 5 to trade temporal resolution for speed and cost.

    Returns:
        PreprocessResult with paths and metadata.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    metadata = probe_video(input_path)

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="vi_preprocess_")

    output_dir = str(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    target_w, target_h = compute_output_resolution(metadata)

    stem = Path(input_path).stem
    processed_video_path = os.path.join(output_dir, f"{stem}_processed.mp4")
    audio_path = os.path.join(output_dir, f"{stem}_audio.aac")

    # Build FFmpeg command
    # vf: scale to target resolution, then set fps
    # map 0:v — video only for processed output
    # separate audio extraction
    vf_filter = f"scale={target_w}:{target_h},fps={target_fps}"

    cmd_video = [
        "ffmpeg",
        "-i", input_path,
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-crf", "23",          # Good quality/size balance
        "-preset", "fast",
        "-an",                 # No audio in video output
        "-y",                  # Overwrite without asking
        processed_video_path,
    ]

    result = subprocess.run(cmd_video, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg video processing failed:\n{result.stderr}")

    # Strip audio track separately (best-effort — not all videos have audio)
    has_audio = any(
        s["codec_type"] == "audio"
        for s in _get_streams(input_path)
    )

    if has_audio:
        cmd_audio = [
            "ffmpeg",
            "-i", input_path,
            "-vn",              # No video
            "-c:a", "aac",      # Transcode to AAC regardless of source codec.
            "-b:a", "128k",     # "-acodec copy" fails for Vorbis/Opus → .aac.
            "-y",
            audio_path,
        ]
        audio_result = subprocess.run(cmd_audio, capture_output=True, text=True)
        if audio_result.returncode != 0:
            # Non-fatal — audio is for future use
            audio_path = None
    else:
        audio_path = None

    return PreprocessResult(
        processed_video_path=processed_video_path,
        audio_path=audio_path,
        metadata=metadata,
        processed_width=target_w,
        processed_height=target_h,
        processed_fps=target_fps,
    )


def _get_streams(input_path: str) -> list[dict]:
    """Helper to get stream info."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return json.loads(result.stdout).get("streams", [])
