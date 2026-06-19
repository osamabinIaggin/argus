"""
Real-time live-streaming camera understanding pipeline.

This package is the live counterpart to the batch `pipeline/` module. Where
`pipeline/` ingests a finite video file and produces a single result.json, this
package ingests an *unbounded* live stream (webcam, iPhone, IP camera, robot)
and maintains a continuously-updated understanding of what is happening.

Architecture (tiered cascade):
  ingest gateway → Tier 1 (YOLO + tracker, always on) → Tier 2 (gated VLM)
                 → Tier 3 (scene state + event log) → PowerSync → clients

Phase 1 (this commit): the ingest layer only — getting frames off any source
into Python reliably, with drop-stale latest-frame semantics and automatic
reconnection. This is the riskiest plumbing, so it is proven first.
"""

__all__ = ["Frame", "FrameSource", "SourceState", "PyAVSource", "FFmpegProcessSource"]

from streaming.frame import Frame
from streaming.sources.base import FrameSource, SourceState
from streaming.sources.pyav_source import PyAVSource
from streaming.sources.ffmpeg_process import FFmpegProcessSource
