"""
Phase 3 — Tier 3 runner: source → Tier 1 (YOLO+track) → SceneTracker → live
scene state + derived event log.

This is the first time the three layers run together. Tier 1 produces
DetectionResults; the SceneTracker folds them into SceneState and emits events;
we print a compact live readout and stream events as they fire. Events are also
echoed through a subscriber to demonstrate the PowerSync-push seam (Tier 4).

Examples (from video_intelligence/, with the streaming venv):

  # Sample clip with people — best first test, no camera needed:
  ./.venv/bin/python -m streaming.run_tier3 --video ../stock-footage-lab-*.webm --seconds 15

  # With a restricted zone over the right third of the frame:
  ./.venv/bin/python -m streaming.run_tier3 --video ../stock-footage-lab-*.webm \
      --zone "vault:restricted:0.66,0,1,1" --seconds 15

  # Live camera / iPhone Continuity:
  ./.venv/bin/python -m streaming.run_tier3 --device 0

Zone syntax (repeatable):  NAME:KIND:x1,y1,x2,y2   (coords normalized 0..1,
KIND = area|restricted). Rectangles only from the CLI; richer polygons go
through the Zone API directly.
"""

from __future__ import annotations

import argparse
import logging
import signal
import time

from streaming.scene import SceneTracker, Zone, ZoneKind
from streaming.sources.ffmpeg_process import FFmpegProcessSource
from streaming.sources.pyav_source import PyAVSource
from streaming.tier1.yolo_detector import YoloDetector


def _build_source(args):
    if args.test:
        return FFmpegProcessSource.test("t3")
    if args.device is not None:
        return FFmpegProcessSource.avfoundation("t3", index=args.device)
    if args.rtsp:
        return PyAVSource.rtsp("t3", url=args.rtsp)
    return FFmpegProcessSource.file("t3", path=args.video)


def _parse_zone(spec: str) -> Zone:
    # NAME:KIND:x1,y1,x2,y2
    name, kind, coords = spec.split(":", 2)
    x1, y1, x2, y2 = (float(v) for v in coords.split(","))
    return Zone.rect(name, x1, y1, x2, y2, kind=ZoneKind(kind))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Tier 3 (scene state) runner")
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
    p.add_argument("--zone", action="append", default=[], help="NAME:KIND:x1,y1,x2,y2")
    p.add_argument("--max-fps", type=float, default=None)
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    classes = [int(c) for c in args.classes.split(",")] if args.classes else None
    detector = YoloDetector(args.model, conf=args.conf, imgsz=args.imgsz, classes=classes)
    zones = [_parse_zone(z) for z in args.zone]
    tracker = SceneTracker("t3", zones=zones)

    # Tier-4 seam: every derived event flows to this sink. Today it just prints;
    # tomorrow it is the PowerSync upsert.
    tracker.events.subscribe(
        lambda e: print(f"  ⚡ EVENT {e.type.value:16s} {e.message}")
    )

    source = _build_source(args)
    stop = {"v": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(v=True))

    source.start()
    print(f"[tier3] source started; loading model + warming up… zones={[z.name for z in zones]}")

    # Warmup (one-time model load / MPS compile / tracker init) — discard timing.
    while not stop["v"]:
        warm = source.read(timeout=2.0)
        if warm is not None:
            detector.detect(warm)
            break

    started = time.monotonic()
    last_report = started
    processed = 0
    min_interval = (1.0 / args.max_fps) if args.max_fps else 0.0

    try:
        while not stop["v"]:
            if args.seconds is not None and (time.monotonic() - started) >= args.seconds:
                break
            loop_t0 = time.monotonic()
            frame = source.read(timeout=1.0)
            if frame is None:
                print(f"[tier3] no frame (state={source.stats.state.value})")
                continue

            result = detector.detect(frame)
            state = tracker.update(result)
            processed += 1

            now = time.monotonic()
            if now - last_report >= 1.0:
                proc_fps = processed / (now - started)
                ents = state.confirmed_entities()
                occ = {k: len(v) for k, v in state.zone_occupancy.items() if v}
                print(
                    f"[tier3] proc_fps={proc_fps:5.1f} "
                    f"entities={len(ents):2d} "
                    f"activity={state.activity_label:6s}({state.activity_level:.3f}) "
                    f"zones={occ or '-'} "
                    f"events={len(tracker.events)}"
                )
                last_report = now

            if min_interval:
                spare = min_interval - (time.monotonic() - loop_t0)
                if spare > 0:
                    time.sleep(spare)
    finally:
        source.stop()
        import json
        print("\n[tier3] final scene snapshot:")
        print(json.dumps(state.snapshot(), indent=2))
        print(f"\n[tier3] stopped. processed={processed} events={len(tracker.events)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
