"""
Phase 2 — Tier 1 runner: source → YOLO detection + tracking → live readout.

Reads frames from any source (the same FrameSource proven in Phase 1), runs
YOLO-with-tracking on each freshest frame, and reports detections + processing
rate. Optionally saves annotated frames so you can SEE the boxes.

Examples (from video_intelligence/, with the streaming venv):

  # Sample video file with real objects — best first test, no camera needed:
  ./.venv/bin/python -m streaming.run_tier1 --video ../stock-footage-*.webm --seconds 15 --save-dir /tmp/t1

  # Live Mac camera / iPhone Continuity:
  ./.venv/bin/python -m streaming.run_tier1 --device 0 --save-dir /tmp/t1

  # Synthetic source (validates the inference path + MPS; finds ~no objects):
  ./.venv/bin/python -m streaming.run_tier1 --test --seconds 5

Flags:
  --model PATH     YOLO weights (default yolo26n.pt, NMS-free; yolov8n.pt etc. work)
  --imgsz N        inference size (default 640; lower = faster)
  --conf F         confidence threshold (default 0.25)
  --classes a,b    restrict to class ids (e.g. 0 for person)
  --max-fps N      cap processing rate (avoid pegging the GPU when idle)
  --save-dir DIR   write annotated frames here (JPEG); --save-every controls cadence
  --save-every S   seconds between saved frames (default 1.0)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

from streaming.sources.pyav_source import PyAVSource
from streaming.sources.ffmpeg_process import FFmpegProcessSource
from streaming.tier1.yolo_detector import YoloDetector


def _build_source(args):
    if args.test:
        return FFmpegProcessSource.test("t1")
    if args.device is not None:
        return FFmpegProcessSource.avfoundation("t1", index=args.device)
    if args.rtsp:
        return PyAVSource.rtsp("t1", url=args.rtsp)
    return FFmpegProcessSource.file("t1", path=args.video)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Tier 1 (YOLO + tracking) runner")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--device", type=int, help="avfoundation device index")
    g.add_argument("--rtsp", type=str, help="rtsp:// (or any) stream URL")
    g.add_argument("--video", type=str, help="local video file (loops)")
    g.add_argument("--test", action="store_true", help="synthetic source")
    p.add_argument("--seconds", type=float, default=None)
    p.add_argument("--model", type=str, default="yolo26n.pt")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--classes", type=str, default=None, help="comma-separated class ids")
    p.add_argument("--max-fps", type=float, default=None)
    p.add_argument("--save-dir", type=str, default=None)
    p.add_argument("--save-every", type=float, default=1.0)
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    classes = [int(c) for c in args.classes.split(",")] if args.classes else None
    detector = YoloDetector(
        args.model, conf=args.conf, imgsz=args.imgsz, classes=classes,
    )
    source = _build_source(args)

    if args.save_dir:
        os.makedirs(args.save_dir, exist_ok=True)

    stop = {"v": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(v=True))

    source.start()
    print(f"[tier1] source started; loading model + warming up…")

    # Warmup: the first detect() pays one-time costs (model load, MPS graph
    # compile, tracker init). Run it once on the first real frame and discard the
    # timing so reported fps reflects steady-state, not startup.
    while not stop["v"]:
        warm = source.read(timeout=2.0)
        if warm is not None:
            t0 = time.monotonic()
            detector.detect(warm)
            print(f"[tier1] warmup detect: {(time.monotonic()-t0)*1000:.0f}ms "
                  f"(one-time costs) — now measuring steady state")
            break

    started = time.monotonic()
    last_report = started
    last_save = 0.0
    processed = 0
    min_interval = (1.0 / args.max_fps) if args.max_fps else 0.0

    try:
        while not stop["v"]:
            if args.seconds is not None and (time.monotonic() - started) >= args.seconds:
                break

            loop_t0 = time.monotonic()
            frame = source.read(timeout=1.0)
            if frame is None:
                print(f"[tier1] no frame (state={source.stats.state.value})")
                continue

            result = detector.detect(frame)
            processed += 1

            # Save an annotated frame on cadence.
            if args.save_dir and (time.monotonic() - last_save) >= args.save_every:
                try:
                    import cv2
                    rgb = detector.annotate(frame, result)
                    path = os.path.join(args.save_dir, f"f_{result.frame_seq:08d}.jpg")
                    cv2.imwrite(path, rgb[:, :, ::-1])   # cv2 expects BGR
                    last_save = time.monotonic()
                except Exception as exc:
                    logging.warning("annotate/save failed: %s", exc)

            now = time.monotonic()
            if now - last_report >= 1.0:
                proc_fps = processed / (now - started)
                print(
                    f"[tier1] proc_fps={proc_fps:5.1f} "
                    f"infer={result.infer_ms:5.1f}ms "
                    f"objs={len(result.detections):2d} "
                    f"[{result.summary()}] "
                    f"src_fps={source.stats.fps_ema:5.1f} "
                    f"dropped={source._slot.dropped}"
                )
                last_report = now

            # Optional consumer-side rate cap.
            if min_interval:
                spare = min_interval - (time.monotonic() - loop_t0)
                if spare > 0:
                    time.sleep(spare)
    finally:
        source.stop()
        print(f"[tier1] stopped. processed={processed} "
              f"src_decoded={source.stats.frames_decoded} "
              f"src_dropped={source._slot.dropped}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
