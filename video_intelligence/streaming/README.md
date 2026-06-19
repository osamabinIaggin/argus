# streaming/ — real-time live camera understanding

The live counterpart to the batch `pipeline/` module. Ingests an *unbounded*
stream (webcam, iPhone, IP camera, robot) and maintains a continuously-updated
understanding of what is happening, pushed to clients in real time.

> Status: **Phase 1 (ingest layer) — done & proven.** Tiers 1–3 follow.

## Architecture (tiered cascade)

```
sources → Tier 1 (YOLO + tracker, always on)   ~real-time, no LLM cost
        → Tier 2 (gated VLM, on trigger/heartbeat)   ~1 fps, semantic "what's happening"
        → Tier 3 (scene state + derived event log)
        → PowerSync → dashboard / chat / robot planner
```

Two robustness guarantees are built into the ingest base class so every source
inherits them:

1. **Drop-stale, never lag.** A decode thread writes into a size-1 slot; a slow
   consumer gets *fewer* frames but always the *freshest* one. Latency stays
   bounded under backpressure. (`LatestFrameSlot` in `sources/base.py`.)
2. **Automatic reconnect with backoff.** Any decode error → `RECONNECTING` →
   exponential backoff → retry, with state + failure counts surfaced.

## Setup

```bash
# from video_intelligence/
python3.12 -m venv .venv
./.venv/bin/pip install -r streaming/requirements.txt
```

## Try it (Phase 1 ingest spike)

```bash
# Synthetic source — no camera/network needed (good for CI):
./.venv/bin/python -m streaming.spike --test --seconds 5

# Demonstrate drop-stale: slow consumer drops frames but age stays ~constant:
./.venv/bin/python -m streaming.spike --test --slow-consumer 200 --seconds 5

# Built-in FaceTime camera (needs camera permission — see below):
./.venv/bin/python -m streaming.spike --device 0 --snapshot /tmp/frame.ppm

# iPhone via Continuity Camera (check index with the ffmpeg command below):
./.venv/bin/python -m streaming.spike --device 1

# IP camera / robot / mediamtx-republished stream:
./.venv/bin/python -m streaming.spike --rtsp rtsp://user:pass@host/stream
```

List camera device indices:

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

### macOS camera capture (why it goes through an ffmpeg subprocess)

PyAV's *in-process* avfoundation capture is unreliable on recent macOS: libav's
avfoundation backend drives frames via CoreFoundation run-loop callbacks that do
not pump correctly when `av.open()` runs on a background worker thread (our
model), giving an immediate `[Errno 5] Input/output error` even though the
`ffmpeg` CLI works. So `--device N` is handled by `FFmpegProcessSource`, which
runs `ffmpeg` in its own process and reads raw rgb24 frames from its stdout.
PyAV is still used for `--rtsp` (network) and `--test` (lavfi).

Camera capture still needs **camera permission** for the app running the command
(grant in System Settings → Privacy & Security → Camera, then reopen the
terminal). Verify the device opens at all with:

```bash
ffmpeg -f avfoundation -framerate 30 -i "0" -frames:v 1 -update 1 -y /tmp/cam.jpg
```

## Layout

```
streaming/
  frame.py              Frame dataclass (RGB ndarray + seq/ts/pts metadata)
  sources/
    base.py             FrameSource (supervision + reconnect) + LatestFrameSlot
    pyav_source.py      PyAV adapter: RTSP / network URL / lavfi-test
    ffmpeg_process.py   FFmpeg-subprocess adapter: Mac capture devices (avfoundation)
  spike.py              Phase 1 CLI harness
  tests/                drop-stale + reconnect + subprocess-source tests
```

## Tests

```bash
./.venv/bin/python -m pytest streaming/tests/ -q
```
