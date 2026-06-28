"""
FFmpegProcessSource — capture via an FFmpeg subprocess, read raw RGB from stdout.

Why this exists (and why it is the default for Mac cameras):
  PyAV's in-process avfoundation capture is fragile on recent macOS. libavdevice's
  avfoundation backend drives frame delivery through CoreFoundation run-loop
  callbacks (CFRunLoopRunInMode), which do not pump reliably when av.open() is
  called from a background worker thread — the exact pattern our multi-source
  design uses. The symptom is an immediate `[Errno 5] Input/output error` on open,
  even though the `ffmpeg` CLI opens the same device fine.

  Rather than fight that (forcing camera capture onto the main thread would break
  the whole "one supervised thread per source" model), we delegate capture to an
  `ffmpeg` subprocess. FFmpeg runs in its own process with its own run loop; we
  read a deterministic stream of raw rgb24 frames from its stdout. This is robust,
  matches a common production pattern, and keeps our threading model intact.

  PyAVSource is still the right tool for RTSP/network streams and the lavfi test
  source — this class is specifically for local capture devices.

Determinism: we always pipe through a `scale+pad` filter to a fixed output size,
so every frame is exactly width*height*3 bytes regardless of the device's native
resolution / aspect ratio (the camera here reports an odd 1552x1552, for example).
Aspect ratio is preserved via letterbox padding.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections import deque
from typing import Iterator, List, Optional, Tuple

import numpy as np

from streaming.sources.base import FrameSource

logger = logging.getLogger(__name__)


def _read_exact(stream, n: int, stop: threading.Event) -> Optional[bytes]:
    """Read exactly n bytes from a pipe, or None on EOF / stop."""
    buf = bytearray()
    while len(buf) < n:
        if stop.is_set():
            return None
        chunk = stream.read(n - len(buf))
        if not chunk:           # EOF — the subprocess exited
            return None
        buf += chunk
    return bytes(buf)


class FFmpegProcessSource(FrameSource):
    def __init__(
        self,
        source_id: str,
        *,
        input_args: List[str],
        width: int = 1280,
        height: int = 720,
        out_fps: int = 30,
        **supervisor_kwargs,
    ) -> None:
        """
        Args:
            input_args: FFmpeg args that select the INPUT, e.g.
                        ["-f", "avfoundation", "-framerate", "30", "-i", "0"].
            width/height: deterministic output frame size (scaled + letterboxed).
            out_fps: cap the output frame rate. avfoundation can free-run and
                     emit hundreds of DUPLICATE frames/sec; capping output here
                     means we never decode/copy/infer on dupes downstream. The
                     drop-stale slot would discard them anyway, but not producing
                     them in the first place saves real CPU and memory bandwidth.
        """
        super().__init__(source_id, **supervisor_kwargs)
        self._input_args = input_args
        self._w = width
        self._h = height
        self._out_fps = out_fps
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_tail: deque[str] = deque(maxlen=12)

    # -- convenience constructors -----------------------------------------

    @classmethod
    def avfoundation(
        cls, source_id: str, index: int = 0, *, fps: int = 30,
        width: int = 1280, height: int = 720, **kwargs,
    ) -> "FFmpegProcessSource":
        """Mac capture device (FaceTime / iPhone Continuity / USB cam) by index."""
        return cls(
            source_id,
            input_args=["-f", "avfoundation", "-framerate", str(fps), "-i", str(index)],
            width=width, height=height, out_fps=fps, **kwargs,
        )

    @classmethod
    def test(
        cls, source_id: str, *, fps: int = 30, width: int = 1280, height: int = 720, **kwargs,
    ) -> "FFmpegProcessSource":
        """Synthetic lavfi source via subprocess — exercises this exact read path."""
        return cls(
            source_id,
            input_args=["-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={fps}"],
            width=width, height=height, out_fps=fps, **kwargs,
        )

    @classmethod
    def file(
        cls, source_id: str, path: str, *, fps: int = 30,
        width: int = 1280, height: int = 720, loop: bool = True, **kwargs,
    ) -> "FFmpegProcessSource":
        """
        Play a local video file as if it were a live stream — for testing
        Tier 1+ on real footage with no camera.

        -re paces decoding at the file's native frame rate (so it behaves like a
        real ~realtime feed instead of decoding at thousands of fps), and
        -stream_loop -1 loops it seamlessly inside ffmpeg (no reconnect churn).
        """
        input_args = ["-re"]
        if loop:
            input_args += ["-stream_loop", "-1"]
        input_args += ["-i", path]
        return cls(source_id, input_args=input_args, width=width, height=height,
                   out_fps=fps, **kwargs)

    # -- FrameSource contract ---------------------------------------------

    def _build_cmd(self) -> List[str]:
        w, h = self._w, self._h
        # Letterbox to an exact WxH so each raw frame is a fixed byte count.
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        )
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-fflags", "nobuffer", "-flags", "low_delay",
            *self._input_args,
            "-vf", vf,
            "-r", str(self._out_fps),    # cap output rate — drop duplicate/over-produced frames
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ]

    def _open_and_iter(self) -> Iterator[Tuple[np.ndarray, Optional[float]]]:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found on PATH")

        cmd = self._build_cmd()
        logger.info("[%s] launching: %s", self.source_id, " ".join(cmd))
        # Hold a LOCAL reference and read from it in the hot loop. stop() may null
        # self._proc concurrently; the local ref keeps the read race-free (the
        # loop still exits promptly because _terminate_proc closes the pipe and
        # we check self._stop each iteration).
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
        )
        self._proc = proc

        # Drain stderr in a daemon thread so a full pipe never deadlocks the
        # capture, while keeping the last few lines for diagnostics.
        def _drain_stderr():
            for raw in iter(proc.stderr.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self._stderr_tail.append(line)

        threading.Thread(
            target=_drain_stderr, daemon=True,
            name=f"ffmpeg-stderr-{self.source_id}",
        ).start()

        frame_bytes = self._w * self._h * 3
        try:
            while not self._stop.is_set():
                buf = _read_exact(proc.stdout, frame_bytes, self._stop)
                if buf is None:
                    if self._stop.is_set():
                        return
                    rc = proc.poll()
                    tail = " | ".join(self._stderr_tail)
                    raise ConnectionError(
                        f"ffmpeg ended (returncode={rc}): {tail or 'no stderr'}"
                    )
                rgb = np.frombuffer(buf, np.uint8).reshape(self._h, self._w, 3)
                yield rgb, None
        finally:
            self._terminate_proc()

    # -- lifecycle ---------------------------------------------------------

    def _terminate_proc(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()

    def stop(self, join_timeout: float = 5.0) -> None:
        # Order matters: set the stop flag FIRST so the read loop treats the
        # imminent EOF as a clean shutdown (not a disconnect to reconnect from),
        # THEN terminate ffmpeg to unblock the blocking stdout read immediately.
        self._stop.set()
        self._terminate_proc()
        super().stop(join_timeout=join_timeout)
