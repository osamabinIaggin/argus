"""Frame sources — adapters that turn any camera/stream into a Frame feed."""

from streaming.sources.base import FrameSource, SourceState, LatestFrameSlot
from streaming.sources.pyav_source import PyAVSource
from streaming.sources.ffmpeg_process import FFmpegProcessSource

__all__ = [
    "FrameSource", "SourceState", "LatestFrameSlot",
    "PyAVSource", "FFmpegProcessSource",
]
