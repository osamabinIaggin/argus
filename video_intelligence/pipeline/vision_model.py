from __future__ import annotations
"""
Stage 5: Vision model per-keyframe description.

Batches ScoredKeyframes into groups of BATCH_SIZE (default 25), sends each
batch to Gemini Flash with full temporal context, and returns structured
per-frame descriptions.

Design decisions:
  - Batches run sequentially to preserve temporal context hand-off
  - Last 3 descriptions from each batch are carried to the next as context
  - response_mime_type="application/json" forces clean JSON output
  - Retry up to MAX_RETRIES times with exponential backoff
  - Malformed/missing frame responses filled with safe defaults (never crash)
  - API key loaded from arg > env var; module imports cleanly without it
"""

import os
import json
import time
import cv2
import numpy as np
from dataclasses import dataclass
from PIL import Image

from google import genai
from google.genai import types

from pipeline.yolo_analyzer import ScoredKeyframe
from pipeline._shared import AudioSegment, get_frame_audio_context


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_NAME   = "gemini-2.5-flash"
BATCH_SIZE   = 25
MAX_RETRIES  = 3
TAIL_SIZE    = 3      # descriptions carried from previous batch as context
TEMPERATURE  = 0.3
MAX_TOKENS   = 16000
MAX_IMG_SIDE = 1024   # Higher resolution for richer detail in vision analysis.
                      # Trades ~2x image token cost for significantly better descriptions.
THINKING_BUDGET = 2048  # Enable extended thinking for deeper visual reasoning

CAMERA_MOVEMENTS = {
    "static", "pan_left", "pan_right",
    "tilt_up", "tilt_down",
    "zoom_in", "zoom_out",
    "cut", "unknown",
}

SYSTEM_PROMPT = """You are an expert video analysis assistant with deep knowledge \
of visual storytelling, animal behavior, human activity, cinematography, and \
environmental context. You receive keyframes extracted from a video in \
chronological order, along with their timestamps.

Rules you must follow:
1. Frames are NOT equally spaced — use timestamp_start/end to understand timing.
   A 3-second gap between frames means that interval looked nearly identical.
2. force_sampled=true means the frame was inserted for temporal coverage, not
   because content changed — treat it as the same scene continuing.
3. YOLO detections are hints only — they can misclassify non-standard objects.
   Use your own visual analysis as the primary source of truth.
4. Describe what is HAPPENING and CHANGING, not just what is statically visible.
   Focus on actions, behaviors, interactions, spatial relationships, body language,
   and the narrative flow between frames.
5. Infer camera movement by comparing frames across the batch holistically.
6. Provide rich, detailed descriptions (2-5 sentences each). Include specific
   visual details: colors, textures, lighting, spatial composition, foreground vs
   background elements, and any emotional or narrative context.
7. For living subjects, describe behavior, posture, gaze direction, and any
   apparent intent or interaction with environment or other subjects.
8. Return ONLY a valid JSON array — no markdown, no explanation."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class FrameDescription:
    keyframe_id:           int
    description:           str
    camera_movement:       str   # static|pan_left|pan_right|tilt_up|tilt_down|zoom_in|zoom_out|cut|unknown
    actions:               str
    changes_from_previous: str


@dataclass
class DescribedKeyframe:
    scored:     ScoredKeyframe
    frame_desc: FrameDescription

    @property
    def keyframe_id(self)           -> int:   return self.scored.keyframe_id
    @property
    def timestamp_start(self)       -> float: return self.scored.timestamp_start
    @property
    def timestamp_end(self)         -> float: return self.scored.timestamp_end
    @property
    def scene_id(self)              -> int:   return self.scored.scene_id
    @property
    def scene_change(self)          -> bool:  return self.scored.scene_change
    @property
    def force_sampled(self)         -> bool:  return self.scored.force_sampled
    @property
    def image(self)                 -> np.ndarray: return self.scored.image
    @property
    def detected_objects(self)      -> list:  return self.scored.yolo.detected_objects
    @property
    def frame_confidence(self)      -> float: return self.scored.yolo.frame_confidence
    @property
    def yolo_context(self)          -> str:   return self.scored.yolo.yolo_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:05.2f}"


def _frame_to_pil(bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _resize_for_gemini(img: Image.Image) -> Image.Image:
    """Resize image so its longest side is at most MAX_IMG_SIDE (768px).

    Keeps each frame within a single Gemini tile (258 tokens) instead of
    spanning 2+ tiles (516+ tokens).  Portrait videos like 640×1390 shrink
    to ~354×768; landscape 854×480 already fits and is returned unchanged.
    Has no effect if both dimensions are already ≤ MAX_IMG_SIDE.
    """
    w, h = img.size
    if w <= MAX_IMG_SIDE and h <= MAX_IMG_SIDE:
        return img
    scale = MAX_IMG_SIDE / max(w, h)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _strip_markdown_json(text: str | None) -> str:
    """Remove markdown code fences if Gemini wraps JSON in them.
    Returns empty string for None/empty input (blocked or empty API response).
    """
    if not text:
        return ""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return text.strip()


def _safe_camera_movement(value: str) -> str:
    """Return the first recognised camera movement token in value.

    Handles compound values the model sometimes returns (e.g. 'pan_right, tilt_down')
    by splitting on common delimiters and returning the first valid token found.
    Falls back to 'unknown' if none of the tokens match.
    """
    import re
    for token in re.split(r"[,/\s]+", str(value).lower().strip()):
        token = token.strip()
        if token in CAMERA_MOVEMENTS:
            return token
    return "unknown"


def _parse_batch_response(
    text: str,
    expected_ids: list[int],
) -> list[FrameDescription]:
    """
    Parse Gemini's JSON response for a batch.
    Fills missing / malformed entries with safe defaults — never raises.
    """
    try:
        raw = json.loads(_strip_markdown_json(text))
        if not isinstance(raw, list):
            raw = []
    except json.JSONDecodeError:
        raw = []

    id_to_raw: dict[int, dict] = {}
    for item in raw:
        if isinstance(item, dict) and "keyframe_id" in item:
            id_to_raw[int(item["keyframe_id"])] = item

    result = []
    for kid in expected_ids:
        item = id_to_raw.get(kid, {})
        result.append(FrameDescription(
            keyframe_id=kid,
            description=str(item.get("description", "No description available.")),
            camera_movement=_safe_camera_movement(item.get("camera_movement", "unknown")),
            actions=str(item.get("actions", "")),
            changes_from_previous=str(item.get("changes_from_previous", "")),
        ))
    return result


def _build_batch_parts(
    batch:          list[ScoredKeyframe],
    prev_tail:      list[FrameDescription],
    batch_num:      int,
    total_batches:  int,
    video_duration: float,
    audio_segments: list[AudioSegment] | None = None,
) -> list:
    """Build content parts list for a single Gemini batch call.

    audio_segments, when provided, are aligned to each frame's timestamp window
    and injected as an 'Audio:' line immediately after the YOLO context.
    This gives the vision model multi-modal grounding without a separate API call.
    """
    parts: list = []

    parts.append(
        f"Video duration: {_fmt_ts(video_duration)} | "
        f"Batch {batch_num}/{total_batches}: "
        f"frames {batch[0].keyframe_id}–{batch[-1].keyframe_id} "
        f"({_fmt_ts(batch[0].timestamp_start)} → {_fmt_ts(batch[-1].timestamp_end)})"
    )

    if prev_tail:
        tail_lines = "\n".join(
            f"  [{d.keyframe_id}] {d.description} "
            f"[camera: {d.camera_movement}]"
            for d in prev_tail
        )
        parts.append(f"Context from previous batch (last {len(prev_tail)} frames):\n{tail_lines}")

    parts.append("Frames to analyze:")

    for sk in batch:
        flags = []
        if sk.scene_change:   flags.append("scene_change")
        if sk.force_sampled:  flags.append("force_sampled — coverage frame, likely similar to neighbors")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        audio_ctx = (
            get_frame_audio_context(audio_segments, sk.timestamp_start, sk.timestamp_end)
            if audio_segments
            else ""
        )

        frame_text = (
            f"\nFrame {sk.keyframe_id} "
            f"[{_fmt_ts(sk.timestamp_start)} → {_fmt_ts(sk.timestamp_end)}]{flag_str}\n"
            f"{sk.yolo_context}"
        )
        if audio_ctx:
            frame_text += f"\n{audio_ctx}"

        parts.append(frame_text)
        parts.append(_resize_for_gemini(_frame_to_pil(sk.image)))

    parts.append(
        'Return a JSON array — one object per frame, in order:\n'
        '[\n'
        '  {\n'
        '    "keyframe_id": <int>,\n'
        '    "description": "<rich, detailed description of what is visible and happening — 2-5 sentences covering subjects, actions, environment, lighting, composition, and narrative context>",\n'
        '    "camera_movement": "<static|pan_left|pan_right|tilt_up|tilt_down|zoom_in|zoom_out|cut|unknown>",\n'
        '    "actions": "<detailed movement, behaviors, or actions occurring — be specific about body language, interactions, and intent>",\n'
        '    "changes_from_previous": "<what changed since the previous frame — describe transitions, new elements, and narrative progression>"\n'
        '  }\n'
        ']'
    )
    return parts


def _call_with_retry(
    client,
    parts: list,
    max_retries: int = MAX_RETRIES,
    config: types.GenerateContentConfig | None = None,
    model: str = MODEL_NAME,
) -> str:
    """
    Call Gemini with exponential backoff retry. Raises on total failure.

    Always uses client.models.generate_content — both real genai.Client and
    test mocks must expose this interface.

    The model parameter defaults to MODEL_NAME (gemini-2.0-flash) but can be
    overridden — audio_analyzer uses this to pass its own model constant without
    coupling to vision_model.MODEL_NAME.
    """
    if config is None:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
        )

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=parts,
                config=config,
            )
            if response.text is None:
                raise ValueError("response.text is None — blocked or empty response")
            return response.text
        except Exception as exc:
            last_err = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(
        f"Gemini call failed after {max_retries} attempts. Last error: {last_err}"
    )


def _get_client(api_key: str | None = None) -> genai.Client:
    """Build and return a google-genai Client."""
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "No Gemini API key provided. "
            "Pass api_key= or set the GEMINI_API_KEY environment variable."
        )
    return genai.Client(api_key=key)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def describe_keyframes(
    scored_keyframes:   list[ScoredKeyframe],
    api_key:            str | None = None,
    batch_size:         int = BATCH_SIZE,
    client=None,
    audio_segments:     list[AudioSegment] | None = None,
    on_batch_complete=None,
) -> list[DescribedKeyframe]:
    """
    Run Gemini Flash on all keyframes in batches.

    Args:
        scored_keyframes:  Output from yolo_analyzer.analyze_keyframes().
        api_key:           Gemini API key (falls back to GEMINI_API_KEY env var).
        batch_size:        Frames per batch call (default 25).
        client:            Pre-configured genai.Client (used in tests to inject mocks).
        audio_segments:    Output from audio_analyzer.analyze_audio(). When provided,
                           each frame's batch prompt is augmented with the audio
                           content overlapping its timestamp window. Pass None or []
                           to skip audio injection (backward-compatible default).
        on_batch_complete: Optional callable(batch_num: int, total_batches: int) invoked
                           after each batch completes. Used by the Celery worker to emit
                           fine-grained progress updates. Ignored if None.

    Returns:
        List of DescribedKeyframe in the same order as input.
    """
    if not scored_keyframes:
        return []

    if client is None:
        client = _get_client(api_key)

    video_duration = scored_keyframes[-1].timestamp_end

    batches = [
        scored_keyframes[i: i + batch_size]
        for i in range(0, len(scored_keyframes), batch_size)
    ]
    total_batches = len(batches)

    all_descriptions: list[FrameDescription] = []
    prev_tail: list[FrameDescription] = []

    _PARSE_RETRIES = 1   # extra attempts when total JSON parse failure is detected

    for batch_num, batch in enumerate(batches, start=1):
        parts = _build_batch_parts(
            batch=batch,
            prev_tail=prev_tail,
            batch_num=batch_num,
            total_batches=total_batches,
            video_duration=video_duration,
            audio_segments=audio_segments or None,
        )

        expected_ids = [sk.keyframe_id for sk in batch]
        for parse_attempt in range(1 + _PARSE_RETRIES):
            raw_text = _call_with_retry(client, parts)
            descriptions = _parse_batch_response(raw_text, expected_ids)
            # Only retry on a total parse failure — where the response produced no
            # parseable list at all (truncated or malformed JSON).  Valid JSON that
            # happens to carry wrong IDs is a different failure mode; retrying won't
            # help and would waste credits.
            try:
                parsed = json.loads(_strip_markdown_json(raw_text))
                parse_ok = isinstance(parsed, list) and len(parsed) > 0
            except Exception:
                parse_ok = False
            if parse_ok:
                break
            if parse_attempt < _PARSE_RETRIES:
                time.sleep(2)

        all_descriptions.extend(descriptions)
        prev_tail = descriptions[-TAIL_SIZE:]
        if on_batch_complete:
            on_batch_complete(batch_num, total_batches)

    return [
        DescribedKeyframe(scored=sk, frame_desc=fd)
        for sk, fd in zip(scored_keyframes, all_descriptions)
    ]
