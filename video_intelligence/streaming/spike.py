"""
Phase 1 ingest spike — prove a robust live frame loop from any source.

Run from the video_intelligence/ directory with the streaming venv:

  # Built-in FaceTime camera
  ./.venv/bin/python -m streaming.spike --device 0

  # iPhone via Continuity Camera (usually device index 1 — check with:
  #   ffmpeg -f avfoundation -list_devices true -i "")
  ./.venv/bin/python -m streaming.spike --device 1

  # IP camera / robot / mediamtx-republished stream
  ./.venv/bin/python -m streaming.spike --rtsp rtsp://user:pass@192.168.1.50/stream

Useful flags:
  --seconds N        stop after N seconds (default: run until Ctrl+C)
  --slow-consumer MS sleep MS each loop to demonstrate drop-stale under backpressure
  --snapshot PATH    write the first frame to a .ppm file (opens in Preview) to prove real pixels

What this validates:
  * frames actually decode off the source
  * the consumer always gets the FRESHEST frame (age stays low even when slow)
  * dropped-frame accounting works under backpressure
  * pulling the cable / closing the stream triggers automatic reconnect
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from streaming.sources.pyav_source import PyAVSource
from streaming.sources.ffmpeg_process import FFmpegProcessSource


def _save_ppm(path: str, rgb) -> None:
    """Write an RGB ndarray as a binary PPM — zero-dependency, opens in Preview."""
    h, w, _ = rgb.shape
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(rgb.tobytes())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live ingest spike")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--device", type=int, help="avfoundation device index (e.g. 0)")
    group.add_argument("--rtsp", type=str, help="rtsp:// (or any) stream URL")
    group.add_argument("--test", action="store_true",
                       help="synthetic FFmpeg lavfi source — needs no camera/network")
    parser.add_argument("--seconds", type=float, default=None, help="auto-stop after N seconds")
    parser.add_argument("--slow-consumer", type=float, default=0.0,
                        help="ms to sleep each loop, to demo backpressure/drops")
    parser.add_argument("--snapshot", type=str, default=None,
                        help="write the first frame to this .ppm path")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.test:
        # FFmpeg's built-in test pattern generator — a moving test card with a
        # timestamp, at 30fps. Exercises the entire decode→ndarray→slot→consumer
        # path with no camera permission or network required.
        source = PyAVSource("spike", file="testsrc2=size=1280x720:rate=30",
                            format="lavfi")
    elif args.device is not None:
        # Mac capture devices go through an ffmpeg subprocess — PyAV's in-process
        # avfoundation capture is unreliable from a background thread on macOS.
        source = FFmpegProcessSource.avfoundation("spike", index=args.device)
    else:
        source = PyAVSource.rtsp("spike", url=args.rtsp)

    # Graceful Ctrl+C: flip a flag, let the loop unwind and stop() the source.
    stop_requested = {"v": False}

    def _handle_sigint(_sig, _frame):
        print("\n[spike] stopping…", file=sys.stderr)
        stop_requested["v"] = True

    signal.signal(signal.SIGINT, _handle_sigint)

    source.start()
    print(f"[spike] started source '{source.source_id}'. Reading frames… (Ctrl+C to stop)")
    if args.device is not None:
        print("[spike] NOTE: macOS will prompt for camera permission on first run.")

    started = time.monotonic()
    last_report = started
    snapshot_saved = args.snapshot is None
    sleep_s = args.slow_consumer / 1000.0

    try:
        while not stop_requested["v"]:
            if args.seconds is not None and (time.monotonic() - started) >= args.seconds:
                break

            frame = source.read(timeout=1.0)
            if frame is None:
                # No fresh frame within the timeout — report liveness state.
                print(f"[spike] no frame (state={source.stats.state.value}, "
                      f"last_error={source.stats.last_error})")
                continue

            if not snapshot_saved:
                _save_ppm(args.snapshot, frame.data)
                print(f"[spike] wrote first frame → {args.snapshot} "
                      f"({frame.width}x{frame.height})")
                snapshot_saved = True

            if sleep_s:
                time.sleep(sleep_s)  # simulate a slow downstream consumer

            now = time.monotonic()
            if now - last_report >= 1.0:
                s = source.stats
                age_ms = frame.age_seconds(now) * 1000.0
                print(
                    f"[spike] state={s.state.value:11s} "
                    f"fps={s.fps_ema:5.1f} "
                    f"decoded={s.frames_decoded:6d} "
                    f"delivered={source._slot.delivered:6d} "
                    f"dropped={source._slot.dropped:6d} "
                    f"latest_age={age_ms:6.1f}ms "
                    f"res={frame.width}x{frame.height} "
                    f"reconnects={s.total_reconnects}"
                )
                last_report = now
    finally:
        source.stop()
        s = source.stats
        print(f"[spike] stopped. decoded={s.frames_decoded} "
              f"delivered={source._slot.delivered} dropped={source._slot.dropped} "
              f"reconnects={s.total_reconnects}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
