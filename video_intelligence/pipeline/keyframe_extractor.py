from __future__ import annotations
"""
Stage 3: Keyframe extraction.

Steps:
  a) PySceneDetect — hard cut detection, streams scene boundaries as found
  b) OpenCV pHash dedup within each scene segment
  c) Temporal density fallback — force-sample if a scene segment exceeds
     DENSITY_WINDOW_SECONDS without sufficient keyframe coverage

Output: ordered list of Keyframe objects with timestamps and scene metadata.
"""

import cv2
import numpy as np
from PIL import Image
import imagehash
from dataclasses import dataclass, field
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PHASH_THRESHOLD = 8           # Hamming distance — lower = keeps more frames (less aggressive dedup)
DENSITY_WINDOW_SECONDS = 2.0  # Max seconds between keyframes before force-sampling
DENSITY_MIN_SCENE_SECONDS = 3.0  # Scene must be longer than this to trigger density check
SCENE_THRESHOLD = 22.0        # ContentDetector sensitivity (lower = more sensitive, detects subtler cuts)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Keyframe:
    keyframe_id: int
    frame_number: int
    timestamp_start: float      # seconds
    timestamp_end: float        # seconds (updated after list is complete)
    scene_id: int
    scene_change: bool          # True if first frame of a new scene
    force_sampled: bool         # True if added by temporal density fallback
    image: np.ndarray = field(repr=False)  # BGR frame data


# ---------------------------------------------------------------------------
# Scene detection
# ---------------------------------------------------------------------------

def detect_scenes(video_path: str) -> list[tuple[float, float]]:
    """
    Run PySceneDetect and return scene boundaries as (start_sec, end_sec) tuples.
    Always returns at least one scene covering the full video.
    """
    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=SCENE_THRESHOLD))
    manager.detect_scenes(video, show_progress=False)

    scene_list = manager.get_scene_list()

    if not scene_list:
        # No cuts detected — entire video is one scene
        cap = cv2.VideoCapture(video_path)
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        duration = total_frames / fps if fps > 0 else 0
        return [(0.0, duration)]

    return [
        (scene[0].get_seconds(), scene[1].get_seconds())
        for scene in scene_list
    ]


# ---------------------------------------------------------------------------
# pHash dedup within a scene
# ---------------------------------------------------------------------------

def _phash(frame_bgr: np.ndarray) -> imagehash.ImageHash:
    """Compute perceptual hash of a BGR frame."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    return imagehash.phash(pil)


def extract_keyframes_from_scene(
    cap: cv2.VideoCapture,
    scene_start_sec: float,
    scene_end_sec: float,
    scene_id: int,
    fps: float,
    next_keyframe_id: int,
) -> list[Keyframe]:
    """
    Extract keyframes from a single scene segment using pHash dedup
    with a temporal density fallback.

    Returns a list of Keyframe objects. Guaranteed to contain at least one.
    """
    start_frame = int(scene_start_sec * fps)
    end_frame = int(scene_end_sec * fps)

    keyframes: list[Keyframe] = []
    last_hash: imagehash.ImageHash | None = None
    last_keyframe_time: float = scene_start_sec
    is_first_in_scene = True
    kid = next_keyframe_id

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    for frame_num in range(start_frame, end_frame):
        ret, frame = cap.read()
        if not ret:
            break

        current_time = frame_num / fps
        h = _phash(frame)

        is_duplicate = (
            last_hash is not None
            and (h - last_hash) < PHASH_THRESHOLD
        )

        time_since_last = current_time - last_keyframe_time
        needs_density_sample = (
            time_since_last >= DENSITY_WINDOW_SECONDS
            and (scene_end_sec - scene_start_sec) > DENSITY_MIN_SCENE_SECONDS
        )

        if is_first_in_scene or not is_duplicate or needs_density_sample:
            force_sampled = needs_density_sample and is_duplicate
            keyframes.append(Keyframe(
                keyframe_id=kid,
                frame_number=frame_num,
                timestamp_start=current_time,
                timestamp_end=scene_end_sec,  # placeholder, fixed in caller
                scene_id=scene_id,
                scene_change=is_first_in_scene,
                force_sampled=force_sampled,
                image=frame.copy(),
            ))
            last_hash = h
            last_keyframe_time = current_time
            is_first_in_scene = False
            kid += 1

    # Minimum-per-scene guarantee: if nothing was extracted, force the first frame
    if not keyframes:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        ret, frame = cap.read()
        if ret:
            keyframes.append(Keyframe(
                keyframe_id=kid,
                frame_number=start_frame,
                timestamp_start=scene_start_sec,
                timestamp_end=scene_end_sec,
                scene_id=scene_id,
                scene_change=True,
                force_sampled=True,
                image=frame.copy(),
            ))

    return keyframes


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_keyframes(video_path: str) -> list[Keyframe]:
    """
    Full keyframe extraction pipeline for a preprocessed video.

    1. Detect scene boundaries
    2. Per scene: pHash dedup + temporal density fallback
    3. Fix timestamp_end values to point to the next keyframe's start
    4. Return ordered list of Keyframe objects

    Args:
        video_path: Path to the FFmpeg-preprocessed video (15fps, resized).

    Returns:
        List of Keyframe objects, ordered by timestamp.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        raise RuntimeError(f"Invalid FPS in video: {video_path}")

    scenes = detect_scenes(video_path)

    all_keyframes: list[Keyframe] = []
    next_id = 1

    for scene_id, (start_sec, end_sec) in enumerate(scenes, start=1):
        scene_frames = extract_keyframes_from_scene(
            cap=cap,
            scene_start_sec=start_sec,
            scene_end_sec=end_sec,
            scene_id=scene_id,
            fps=fps,
            next_keyframe_id=next_id,
        )
        all_keyframes.extend(scene_frames)
        next_id += len(scene_frames)

    cap.release()

    # Fix timestamp_end: each keyframe ends where the next one starts
    for i in range(len(all_keyframes) - 1):
        all_keyframes[i].timestamp_end = all_keyframes[i + 1].timestamp_start

    # Last keyframe ends at the last scene's end
    if all_keyframes and scenes:
        all_keyframes[-1].timestamp_end = scenes[-1][1]

    return all_keyframes
