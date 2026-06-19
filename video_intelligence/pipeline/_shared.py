from __future__ import annotations
"""
Shared data types and pure utility functions used across multiple pipeline stages.

Kept in a separate module to avoid circular imports between vision_model and
audio_analyzer (both need AudioSegment; audio_analyzer imports _call_with_retry
from vision_model, so vision_model cannot import from audio_analyzer).
"""

from dataclasses import dataclass


@dataclass
class AudioSegment:
    """One detected audio event or speech segment with timestamp boundaries."""
    start:        float   # start time in seconds
    end:          float   # end time in seconds
    content:      str     # verbatim speech quote or precise event description
    segment_type: str     # speech | event | ambient | music | silence


def get_frame_audio_context(
    segments: list[AudioSegment],
    ts_start: float,
    ts_end:   float,
) -> str:
    """
    Return a formatted audio context string for the time window [ts_start, ts_end].

    Includes every segment that overlaps the window — partial overlap counts.
    Silence segments are excluded: injecting "silence" into a frame description
    adds no useful information for the vision model.

    Returns "" when no relevant audio overlaps the window.

    Overlap condition: segment.start < ts_end  AND  segment.end > ts_start
    This is the standard interval overlap check (exclusive boundaries).
    A segment that ends exactly at ts_start, or starts exactly at ts_end,
    does NOT overlap and is excluded.
    """
    overlapping = [
        s for s in segments
        if s.start < ts_end and s.end > ts_start and s.segment_type != "silence"
    ]
    if not overlapping:
        return ""
    return "Audio: " + "; ".join(s.content for s in overlapping)
