"""
FrameSource — the base abstraction every camera/stream adapter implements.

Two robustness guarantees live here, so every concrete source inherits them for
free (this is the "so it does not break" requirement made structural):

  1. DROP-STALE, NEVER LAG (LatestFrameSlot)
     A dedicated decode thread writes frames into a size-1 slot. If a consumer
     is slower than the source, older frames are overwritten and counted as
     drops — the consumer always gets the *freshest* frame. In real-time vision,
     a dropped frame is correct behaviour; a growing backlog of stale frames is
     a bug. This is the single most important design choice in the ingest layer.

  2. AUTOMATIC RECONNECT WITH BACKOFF (supervision loop)
     Live streams die: Wi-Fi drops, a robot moves out of range, an IP camera
     reboots. The supervisor catches any decode error, transitions to
     RECONNECTING, backs off exponentially, and retries — surfacing state and
     failure counts so the UI can show live / reconnecting / offline honestly.

Subclasses implement exactly one method: `_open_and_iter()`, a generator that
connects and yields (rgb_ndarray, pts) tuples, raising on disconnect.
"""

from __future__ import annotations

import abc
import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional, Tuple

import numpy as np

from streaming.frame import Frame

logger = logging.getLogger(__name__)


class SourceState(str, enum.Enum):
    """Lifecycle state of a source, surfaced to the UI/consumers."""

    IDLE = "idle"                 # created, not started
    CONNECTING = "connecting"     # first connection attempt in progress
    LIVE = "live"                 # delivering frames normally
    RECONNECTING = "reconnecting" # lost connection, retrying with backoff
    STOPPED = "stopped"           # explicitly stopped, will not reconnect


# ---------------------------------------------------------------------------
# Latest-frame slot — the drop-stale primitive
# ---------------------------------------------------------------------------

class LatestFrameSlot:
    """
    A thread-safe size-1 mailbox holding only the most recent frame.

    put() overwrites whatever is there (counting a drop if the previous frame
    was never consumed). get() blocks until a fresh frame is available or the
    optional timeout elapses. This is intentionally lossy: it trades frame
    completeness for bounded latency.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame: Optional[Frame] = None
        self._unconsumed = False
        self._closed = False
        self.dropped = 0       # frames overwritten before being consumed
        self.delivered = 0     # frames handed to a consumer

    def put(self, frame: Frame) -> None:
        with self._cond:
            if self._unconsumed:
                self.dropped += 1
            self._frame = frame
            self._unconsumed = True
            self._cond.notify()

    def get(self, timeout: Optional[float] = None) -> Optional[Frame]:
        """Return the freshest frame, or None if timeout elapses / slot closed."""
        with self._cond:
            if not self._unconsumed and not self._closed:
                self._cond.wait(timeout)
            if self._closed or not self._unconsumed:
                return None
            frame = self._frame
            self._unconsumed = False
            self.delivered += 1
            return frame

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


# ---------------------------------------------------------------------------
# Stats — lightweight observability per source
# ---------------------------------------------------------------------------

@dataclass
class SourceStats:
    state: SourceState = SourceState.IDLE
    frames_decoded: int = 0
    consecutive_failures: int = 0
    total_reconnects: int = 0
    last_error: Optional[str] = None
    connected_at_monotonic: Optional[float] = None
    last_frame_at_monotonic: Optional[float] = None
    # Exponential moving average of decode FPS (smooths instantaneous jitter).
    fps_ema: float = 0.0
    _ema_alpha: float = field(default=0.1, repr=False)

    def note_frame(self, now: float) -> None:
        if self.last_frame_at_monotonic is not None:
            dt = now - self.last_frame_at_monotonic
            if dt > 0:
                inst = 1.0 / dt
                self.fps_ema = (
                    inst if self.fps_ema == 0.0
                    else (1 - self._ema_alpha) * self.fps_ema + self._ema_alpha * inst
                )
        self.last_frame_at_monotonic = now
        self.frames_decoded += 1


# ---------------------------------------------------------------------------
# FrameSource — base class with supervision + reconnect
# ---------------------------------------------------------------------------

class FrameSource(abc.ABC):
    """
    Base class for all frame sources.

    Lifecycle:
        src = ConcreteSource(source_id="cam0", ...)
        src.start()
        while True:
            frame = src.read(timeout=1.0)   # freshest frame or None
            ...
        src.stop()
    """

    def __init__(
        self,
        source_id: str,
        *,
        backoff_initial: float = 0.5,
        backoff_max: float = 10.0,
        max_consecutive_failures: Optional[int] = None,  # None = retry forever
    ) -> None:
        self.source_id = source_id
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._max_failures = max_consecutive_failures

        self._slot = LatestFrameSlot()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seq = 0
        self.stats = SourceStats()

    # -- public API --------------------------------------------------------

    def start(self) -> "FrameSource":
        if self._thread is not None:
            raise RuntimeError(f"Source {self.source_id} already started")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._supervise, name=f"src-{self.source_id}", daemon=True
        )
        self._thread.start()
        return self

    def read(self, timeout: Optional[float] = None) -> Optional[Frame]:
        """Return the freshest decoded frame, or None on timeout."""
        return self._slot.get(timeout=timeout)

    def stop(self, join_timeout: float = 5.0) -> None:
        self._stop.set()
        self._slot.close()
        self.stats.state = SourceState.STOPPED
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- subclass contract -------------------------------------------------

    @abc.abstractmethod
    def _open_and_iter(self) -> Iterator[Tuple[np.ndarray, Optional[float]]]:
        """
        Connect to the underlying source and yield (rgb_ndarray, pts) tuples.

        Must raise an exception when the connection is lost / ends so the
        supervisor can trigger a reconnect. Must respect self._stop by exiting
        the generator promptly when it is set.
        """
        raise NotImplementedError

    # -- internals ---------------------------------------------------------

    def _supervise(self) -> None:
        """Run the connect→stream→reconnect loop until stopped."""
        backoff = self._backoff_initial
        while not self._stop.is_set():
            self.stats.state = (
                SourceState.CONNECTING
                if self.stats.total_reconnects == 0 and self.stats.frames_decoded == 0
                else SourceState.RECONNECTING
            )
            try:
                for rgb, pts in self._open_and_iter():
                    if self._stop.is_set():
                        break
                    now = time.monotonic()
                    # First frame after a (re)connect → we are LIVE; reset backoff.
                    if self.stats.state != SourceState.LIVE:
                        self.stats.state = SourceState.LIVE
                        self.stats.connected_at_monotonic = now
                        self.stats.consecutive_failures = 0
                        backoff = self._backoff_initial
                        logger.info("[%s] live", self.source_id)
                    self._seq += 1
                    self.stats.note_frame(now)
                    self._slot.put(
                        Frame(
                            data=rgb,
                            seq=self._seq,
                            ts_monotonic=now,
                            source_id=self.source_id,
                            pts=pts,
                        )
                    )
                # Generator returned without error → treat as a normal disconnect.
                if not self._stop.is_set():
                    raise ConnectionError("stream ended")

            except Exception as exc:  # noqa: BLE001 — supervisor must catch all
                if self._stop.is_set():
                    break
                self.stats.consecutive_failures += 1
                self.stats.total_reconnects += 1
                self.stats.last_error = str(exc)
                logger.warning(
                    "[%s] disconnected (%s) — reconnect in %.1fs (failure #%d)",
                    self.source_id, exc, backoff, self.stats.consecutive_failures,
                )
                if (
                    self._max_failures is not None
                    and self.stats.consecutive_failures >= self._max_failures
                ):
                    logger.error(
                        "[%s] giving up after %d consecutive failures",
                        self.source_id, self.stats.consecutive_failures,
                    )
                    break
                # Interruptible sleep: wake immediately if stop() is called.
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self._backoff_max)

        self.stats.state = SourceState.STOPPED
        self._slot.close()
        logger.info("[%s] supervisor exited", self.source_id)
