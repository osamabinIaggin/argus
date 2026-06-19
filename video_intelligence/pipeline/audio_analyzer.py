from __future__ import annotations
"""
Stage 4.5: Audio analysis via Gemini 2.0 Flash.

Analyzes the extracted audio track (.aac) produced by the preprocessor and
returns a list of AudioSegments covering the full audio timeline:

  - speech  : verbatim transcript with timestamps
  - event   : non-speech sounds (latex snap, engine rev, glass breaking)
  - ambient : continuous background texture (HVAC hum, outdoor wind, crowd murmur)
  - music   : genre and mood description
  - silence : quiet gaps

AudioSegments flow into the vision model stage (Stage 5) where
get_frame_audio_context() aligns them to each keyframe's timestamp window,
giving the vision model multi-modal grounding at no extra API calls.

Design decisions:
  - Single Gemini call for the full audio track — cheap (~$0.001 per 52s clip).
  - Audio sent as inline bytes (no Files API upload/delete complexity).
    Hard limit: 20 MB. Files above this are skipped and [] is returned.
    TODO: add Files API path for clips > 20 MB when longer videos are supported.
  - analyze_audio() is NON-FATAL — returns [] on any failure.
    Audio enriches the pipeline but is never required for it to complete.
    A video with no audio track (audio_path=None) is handled identically.
  - MIME type detected from file extension; falls back to audio/aac.
  - _parse_audio_response() never raises — fills safe defaults on failure.
  - Segments are sorted by start time; out-of-range or inverted timestamps discarded.
  - Temperature=0.1 — factual transcription, minimal creativity.
"""

import os
import json
import math
from pathlib import Path

from google import genai
from google.genai import types

from pipeline._shared import AudioSegment, get_frame_audio_context   # re-export for callers
from pipeline.vision_model import _call_with_retry, _strip_markdown_json


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AUDIO_MODEL    = "gemini-2.5-flash"
MAX_RETRIES    = 3
TEMPERATURE    = 0.1          # factual transcription; low creativity
MAX_TOKENS     = 4000
MAX_FILE_BYTES = 20 * 1024 * 1024   # 20 MB inline limit

VALID_TYPES = {"speech", "event", "ambient", "music", "silence"}

MIME_MAP: dict[str, str] = {
    ".aac":  "audio/aac",
    ".mp3":  "audio/mpeg",
    ".mp4":  "audio/mp4",
    ".ogg":  "audio/ogg",
    ".opus": "audio/ogg",
    ".wav":  "audio/wav",
    ".m4a":  "audio/mp4",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}

AUDIO_PROMPT = """\
Analyze this audio recording and identify every distinct segment of content.

Return a JSON array where each object describes one continuous segment:
[
  {
    "start":   <float — start time in seconds>,
    "end":     <float — end time in seconds>,
    "content": "<description: for speech include VERBATIM quoted words and note \
the speaker if distinguishable; for sound events be precise ('latex glove snap', \
'vial click', 'car engine revving at high RPM', 'glass breaking'); \
for ambient describe the background environment; \
for music describe genre, tempo, and mood>",
    "type": "<speech | event | ambient | music | silence>"
  }
]

Rules:
1. Cover the ENTIRE recording duration — do not leave gaps.
2. speech  : transcribe verbatim; identify speaker if possible (e.g. 'healthcare worker: ...').
3. event   : name the specific sound precisely — never vague terms like 'a noise' or 'a sound'.
4. ambient : describe the continuous background texture of the environment.
5. music   : describe genre, tempo, and emotional mood.
6. silence : mark silence explicitly with type="silence" and content="silence".
7. Merge adjacent segments only if both type AND content are identical.
8. Use a MINIMUM segment duration of 2 seconds. Never create sub-second segments.
   Merge consecutive same-type sounds shorter than 2 seconds into a single segment.
9. Timestamps must be as accurate as possible — do not round to nearest whole second.
10. Return ONLY valid JSON — no markdown fences, no explanation text.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_mime(path: str) -> str:
    """Map file extension to MIME type. Falls back to audio/aac."""
    return MIME_MAP.get(Path(path).suffix.lower(), "audio/aac")


def _parse_audio_response(text: str, duration: float) -> list[AudioSegment]:
    """
    Parse Gemini's JSON response into a sorted list of AudioSegments.

    Guards applied per item (bad items are dropped, never raise):
      - Must be a dict with parseable start/end/content/type fields
      - start clamped to >= 0
      - end clamped to <= duration + 1s tolerance (Gemini rounding)
      - end must be strictly greater than start after clamping
      - Unknown segment_type mapped to 'event'
      - Empty content string dropped

    Returns [] on total parse failure (malformed JSON, non-list root, etc).
    """
    try:
        raw = json.loads(_strip_markdown_json(text))
        if not isinstance(raw, list):
            return []
    except (json.JSONDecodeError, AttributeError):
        return []

    segments: list[AudioSegment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start    = float(item.get("start", 0))
            end      = float(item.get("end", 0))
            content  = str(item.get("content", "")).strip()
            seg_type = str(item.get("type", "")).lower().strip()
        except (TypeError, ValueError):
            continue

        if not content:
            continue

        # Clamp timestamps
        if start < 0:
            start = 0.0
        if end > duration + 1.0:
            end = duration

        # Discard inverted or zero-length segments
        if end <= start:
            continue

        # Normalise unknown types rather than discarding the segment
        if seg_type not in VALID_TYPES:
            seg_type = "event"

        segments.append(AudioSegment(
            start=round(start, 3),
            end=round(end, 3),
            content=content,
            segment_type=seg_type,
        ))

    segments.sort(key=lambda s: s.start)
    return segments


def _get_client(api_key: str | None = None) -> genai.Client:
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

def analyze_audio(
    audio_path: str | None,
    duration:   float = float("inf"),
    api_key:    str | None = None,
    client=None,
) -> list[AudioSegment]:
    """
    Run Gemini Flash audio analysis on the extracted audio track.

    NON-FATAL: returns [] on any failure so the pipeline always completes.
    Audio context enriches vision model descriptions but is never required.

    Args:
        audio_path: Path to the audio file (PreprocessResult.audio_path).
                    Pass None when the source video had no audio — returns []
                    immediately without any API call.
        duration:   Video duration in seconds (from VideoMetadata.duration_seconds).
                    Used only to clamp out-of-range timestamps in the parsed
                    response. Defaults to inf (no clamping) if not provided.
        api_key:    Gemini API key (falls back to GEMINI_API_KEY env var).
        client:     Pre-configured genai.Client (injected in tests).

    Returns:
        List of AudioSegment sorted by start time, or [] on any failure.
    """
    # Early exits — no API call made
    if not audio_path:
        return []
    if not os.path.exists(audio_path):
        return []

    file_size = os.path.getsize(audio_path)
    if file_size == 0:
        return []
    if file_size > MAX_FILE_BYTES:
        # Large file: skip rather than fail loudly.
        # TODO: route through Files API when > 20 MB.
        return []

    try:
        if client is None:
            client = _get_client(api_key)

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        mime  = _detect_mime(audio_path)
        parts = [
            types.Part.from_bytes(data=audio_bytes, mime_type=mime),
            AUDIO_PROMPT,
        ]
        # Scale token budget with duration: ~15 tokens/second of audio (generous).
        # Bounded between MAX_TOKENS (4 000) and 16 000.
        # Beyond 20 MB the file is already rejected above, so 16 000 covers
        # the full inline-bytes range (~21 min at 128 kbps).
        # Guard against duration=inf (the default when caller omits it).
        finite_dur = duration if math.isfinite(duration) else 1_200.0
        token_budget = min(16_000, max(MAX_TOKENS, int(finite_dur * 150)))
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=token_budget,
            temperature=TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=1024),
        )

        raw_text = _call_with_retry(client, parts, config=config, model=AUDIO_MODEL)
        return _parse_audio_response(raw_text, duration)

    except Exception:
        # Audio analysis is enhancement-only — never crash the pipeline.
        return []
