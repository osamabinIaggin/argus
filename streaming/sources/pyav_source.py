"""
PyAVSource — a single adapter that covers (almost) every source we care about.

PyAV (FFmpeg bindings) decodes local capture devices AND network streams, so
one class handles:
  * Mac webcam / iPhone Continuity Camera  → avfoundation device index
  * IP camera / robot                       → rtsp:// URL
  * Anything mediamtx republishes           → rtsp:// (or http/whep) URL

We deliberately use PyAV rather than OpenCV's VideoCapture for ingest: it gives
direct access to FFmpeg's low-latency flags, hardware decoders, and presentation
timestamps, and it does not silently buffer frames the way some VideoCapture
backends do.

The class only implements `_open_and_iter()`; all the drop-stale + reconnect
machinery is inherited from FrameSource.
"""

from __future__ import annotations

import logging
from typing import Iterator, Optional, Tuple

import av
import numpy as np

from streaming.sources.base import FrameSource

logger = logging.getLogger(__name__)

# FFmpeg options that minimise latency on live network streams. nobuffer +
# low_delay tell FFmpeg not to accumulate frames before handing them to us.
_LOW_LATENCY_NET_OPTS = {
    "fflags": "nobuffer",
    "flags": "low_delay",
    "rtsp_transport": "tcp",   # TCP avoids UDP packet-loss artefacts; switch to udp for LAN if needed
    "stimeout": "5000000",     # 5s socket timeout (microseconds) so a dead stream raises instead of hanging
}


class PyAVSource(FrameSource):
    def __init__(
        self,
        source_id: str,
        *,
        file: str,
        format: Optional[str] = None,
        options: Optional[dict] = None,
        **supervisor_kwargs,
    ) -> None:
        """
        Args:
            file:    avfoundation device index ("0") or a stream URL.
            format:  FFmpeg input format, e.g. "avfoundation" for a Mac device.
                     None lets FFmpeg auto-detect (correct for rtsp/http URLs).
            options: FFmpeg demuxer options (merged over the latency defaults).
        """
        super().__init__(source_id, **supervisor_kwargs)
        self._file = file
        self._format = format
        self._options = options or {}

    # -- convenience constructors -----------------------------------------

    @classmethod
    def webcam(cls, source_id: str, index: int = 0, **kwargs) -> "PyAVSource":
        """Mac capture device by index (see `ffmpeg -f avfoundation -list_devices true -i ''`)."""
        return cls(source_id, file=str(index), format="avfoundation", **kwargs)

    @classmethod
    def rtsp(cls, source_id: str, url: str, **kwargs) -> "PyAVSource":
        """IP camera / robot / mediamtx-republished RTSP stream."""
        return cls(source_id, file=url, **kwargs)

    @classmethod
    def file(cls, source_id: str, path: str, **kwargs) -> "PyAVSource":
        """
        Local video file — handy for testing Tier 1+ on sample footage with real
        objects (no camera needed). On EOF the supervisor 'reconnects', so the
        clip loops. No network/low-latency options are applied.
        """
        return cls(source_id, file=path, format=None, **kwargs)

    # -- FrameSource contract ---------------------------------------------

    def _open_and_iter(self) -> Iterator[Tuple[np.ndarray, Optional[float]]]:
        # Only apply low-latency network options to actual network URLs — not to
        # local files (which also have format=None but no "://" scheme).
        is_network = self._format is None and "://" in self._file
        opts = dict(_LOW_LATENCY_NET_OPTS) if is_network else {}
        opts.update(self._options)

        logger.info("[%s] opening %s (format=%s)", self.source_id, self._file, self._format)
        container = av.open(self._file, format=self._format, options=opts)
        try:
            stream = container.streams.video[0]
            # Multi-threaded decode keeps us off the critical path on HD streams.
            stream.thread_type = "AUTO"
            time_base = stream.time_base

            for frame in container.decode(stream):
                if self._stop.is_set():
                    return
                # rgb24 → contiguous HxWx3 uint8 RGB (our canonical format).
                rgb = frame.to_ndarray(format="rgb24")
                pts = float(frame.pts * time_base) if frame.pts is not None and time_base else None
                yield rgb, pts
        finally:
            container.close()
