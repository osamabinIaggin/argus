"""
The Frame — the single unit that flows through the live pipeline.

Design notes:
  * Pixel data is stored as an HxWx3 **RGB** uint8 ndarray. RGB (not BGR) is the
    canonical representation here because the downstream semantic models (VLMs,
    PIL, most APIs) expect RGB. The Tier-1 adapter converts to BGR only at the
    OpenCV/Ultralytics boundary, where that convention is required.
  * `ts_monotonic` is wall-clock-independent (time.monotonic) and is the
    timestamp the whole pipeline reasons about for latency and ordering. It is
    immune to NTP steps / clock changes, unlike time.time().
  * `pts` is the stream's own presentation timestamp in seconds, when available.
    Useful for A/V sync and detecting decode stalls; may be None for some live
    sources that do not provide it.
  * `seq` is a monotonically increasing decode counter for THIS source. Gaps
    between consecutive consumed `seq` values reveal how many frames were
    dropped under backpressure (which is expected and healthy — see
    LatestFrameSlot).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(slots=True)
class Frame:
    """One decoded video frame plus the metadata the pipeline needs."""

    data: np.ndarray          # HxWx3 RGB uint8
    seq: int                  # per-source monotonically increasing decode index
    ts_monotonic: float       # time.monotonic() captured at decode time
    source_id: str            # which source produced this frame
    pts: Optional[float] = None   # stream presentation timestamp (seconds), if known

    @property
    def width(self) -> int:
        return int(self.data.shape[1])

    @property
    def height(self) -> int:
        return int(self.data.shape[0])

    def age_seconds(self, now_monotonic: float) -> float:
        """How stale this frame is relative to `now`. Latency observability."""
        return now_monotonic - self.ts_monotonic
