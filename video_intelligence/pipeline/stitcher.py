from __future__ import annotations
"""
Stage 6+7: Stitching and summarization.

Takes the list of DescribedKeyframes, builds the final timeline, makes one
text-only LLM call for the overall video summary, and returns a dict that
matches the locked output schema.

The summary call is text-only (no images) — it reads the stitched timeline
as text and produces a coherent narrative. Cheap compared to vision batches.
"""

import os
import json
import time
import uuid
from dataclasses import dataclass

from google import genai
from google.genai import types

from pipeline.vision_model import DescribedKeyframe, _call_with_retry, _strip_markdown_json
from pipeline.preprocessor import PreprocessResult
from pipeline._shared import AudioSegment


SUMMARY_MODEL   = "gemini-2.5-flash"
MAX_RETRIES     = 3
TEMPERATURE     = 0.3
MAX_TOKENS      = 2000
THINKING_BUDGET = 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:05.2f}"


def _build_timeline_text(described: list[DescribedKeyframe]) -> str:
    """Format the timeline as readable text for the summary prompt."""
    lines = []
    for dk in described:
        lines.append(
            f"[{_fmt_ts(dk.timestamp_start)} → {_fmt_ts(dk.timestamp_end)}] "
            f"{dk.frame_desc.description}"
            + (f" (camera: {dk.frame_desc.camera_movement})" if dk.frame_desc.camera_movement != "static" else "")
            + (f" — {dk.frame_desc.actions}" if dk.frame_desc.actions else "")
        )
    return "\n".join(lines)


def _get_summary_client(api_key: str | None = None) -> genai.Client:
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "No Gemini API key provided. "
            "Pass api_key= or set the GEMINI_API_KEY environment variable."
        )
    return genai.Client(api_key=key)


def _build_summary_prompt(timeline_text: str, duration: float) -> str:
    return (
        "You are given a structured timeline of keyframe descriptions from a video "
        f"({_fmt_ts(duration)} long).\n\n"
        "Timeline:\n"
        f"{timeline_text}\n\n"
        "Produce a detailed 3-6 sentence summary of what happens in the video, "
        "as if describing it to someone who has not seen it. "
        "Cover the main subject(s), key actions, environment/setting, emotional tone, "
        "and overall narrative arc from beginning to end. "
        "Include specific visual details that make the description vivid and engaging. "
        "If the timeline descriptions seem inconsistent, use the most coherent interpretation.\n\n"
        'Return JSON: {"summary": "<your summary here>"}'
    )


def _parse_summary(text: str) -> str:
    try:
        data = json.loads(_strip_markdown_json(text))
        return str(data.get("summary", "")).strip() or "Summary unavailable."
    except (json.JSONDecodeError, AttributeError):
        # If JSON parsing fails, use the raw text as a fallback
        cleaned = _strip_markdown_json(text)
        return cleaned if cleaned else "Summary unavailable."


def _generate_video_id() -> str:
    return f"vid_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_timeline_entry(dk: DescribedKeyframe) -> dict:
    """Convert a single DescribedKeyframe into its output schema dict."""
    return {
        "keyframe_id":     dk.keyframe_id,
        "timestamp_start": _fmt_ts(dk.timestamp_start),
        "timestamp_end":   _fmt_ts(dk.timestamp_end),
        "description":     dk.frame_desc.description,
        "camera_movement": dk.frame_desc.camera_movement,
        "actions":         dk.frame_desc.actions,
        "changes_from_previous": dk.frame_desc.changes_from_previous,
        "detected_objects": dk.detected_objects,
        "scene_change":    bool(dk.scene_change),
        "confidence":      dk.frame_confidence,
    }


def stitch(
    described:          list[DescribedKeyframe],
    preprocess_result:  PreprocessResult,
    total_frames:       int,
    processing_time_s:  float,
    api_key:            str | None = None,
    video_id:           str | None = None,
    summary_model=None,   # kept for backward compat with tests (acts as client)
    audio_segments:     list[AudioSegment] | None = None,
) -> dict:
    """
    Build the final output JSON from described keyframes.

    Steps:
      1. Build timeline from described keyframes (code only, free)
      2. Call Gemini for overall summary (text only, cheap)
      3. Assemble and return the locked output schema dict

    Args:
        described:         Output from vision_model.describe_keyframes().
        preprocess_result: Output from preprocessor.preprocess().
        total_frames:      Total frames in the processed video.
        processing_time_s: Wall-clock seconds for the full pipeline.
        api_key:           Gemini API key (falls back to GEMINI_API_KEY env var).
        video_id:          Override video ID (generated if not provided).
        summary_model:     Pre-configured model instance (used in tests).

    Returns:
        Dict matching the locked output schema.
    """
    vid = video_id or _generate_video_id()
    meta = preprocess_result.metadata

    # Step 1 — build timeline (free)
    timeline = [build_timeline_entry(dk) for dk in described]

    # Step 2 — summary LLM call (text only)
    timeline_text = _build_timeline_text(described)
    summary_prompt = _build_summary_prompt(timeline_text, meta.duration_seconds)

    if summary_model is None:
        summary_model = _get_summary_client(api_key)

    summary_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
    )
    raw_summary = _call_with_retry(summary_model, [summary_prompt], config=summary_config)
    summary = _parse_summary(raw_summary)

    # Step 3 — assemble output schema
    keyframes_analyzed = len(described)
    duplicates_removed = total_frames - keyframes_analyzed

    audio_out = [
        {
            "start":        seg.start,
            "end":          seg.end,
            "content":      seg.content,
            "segment_type": seg.segment_type,
        }
        for seg in (audio_segments or [])
        if seg.segment_type != "silence"
    ]

    return {
        "video_id": vid,
        "status": "complete",
        "metadata": {
            "duration_seconds":       round(meta.duration_seconds, 2),
            "original_fps":           meta.original_fps,
            "processed_fps":          preprocess_result.processed_fps,
            "original_resolution":    f"{meta.original_width}x{meta.original_height}",
            "processed_resolution":   f"{preprocess_result.processed_width}x{preprocess_result.processed_height}",
            "total_frames_extracted": total_frames,
            "keyframes_analyzed":     keyframes_analyzed,
            "duplicates_removed":     duplicates_removed,
            "processing_time_seconds": round(processing_time_s, 2),
        },
        "summary": summary,
        "timeline": timeline,
        "audio_segments": audio_out,
    }
