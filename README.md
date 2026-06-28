# Argus

**Real-time camera intelligence.** Argus turns any live video stream into a
continuously-updated, queryable understanding of what is happening — on-device,
in real time, with sub-frame latency.

Point it at a webcam, an iPhone, an IP camera, or a robot's eyes, and it
maintains a live scene graph of every entity, zone, and event in view — and lets
you ask it questions in natural language.

---

## Why

Cameras are everywhere; understanding is not. Most "video AI" is batch: upload a
clip, wait, get JSON. That model collapses the moment the stream never ends.
Real-world perception — surveillance, robotics, live operations — needs
*continuous* understanding with bounded latency, not a job queue.

Argus is built for the unbounded stream: an always-on perception loop that never
falls behind, layered with semantic reasoning that fires only when it matters.

## How it works — a tiered perception cascade

```
 sources  ──►  Tier 1: always-on perception   (real-time, no LLM cost)
 WebRTC        NMS-free detection + multi-object tracking on-device
 RTSP / SRT          │
 HLS / robot         ▼
               Tier 2: gated semantic understanding   (~1 fps, triggered)
               vision-language model — "what is happening", in words
                     │
                     ▼
               Tier 3: scene state = source of truth
               live scene graph (entities · zones · activity · semantics)
               event log is *derived* from state transitions
                     │
                     ▼
               real-time sync  ──►  dashboard · chat · robot planner
```

- **Tier 1 — Always-on perception.** NMS-free, end-to-end object detection with
  persistent multi-object tracking (ByteTrack), running real-time on Apple
  Silicon (MLX / Metal). Stable identities, motion, and zone/tripwire logic with
  zero inference cost beyond the local GPU.
- **Tier 2 — Gated semantic reasoning.** A vision-language model describes the
  scene in natural language — fired on triggers from Tier 1 plus a heartbeat
  floor, never on every frame. The model layer is fully **swappable**: local
  on-device VLMs or a cloud model, hot-swapped behind one interface.
- **Tier 3 — Scene state as truth.** A continuously-updated scene graph is the
  single source of truth; the event log is **event-sourced** from state
  transitions (entity entered, zone breached, activity shifted, semantic note).
- **Real-time sync.** Live state and events stream **local-first** to any client —
  an ops dashboard, a conversational query layer, or a robot's planner.

## Design principles

- **Drop-stale, never lag.** Backpressure-aware, size-1 latest-frame slots keep
  end-to-end latency bounded — a slow consumer sees *fewer, fresher* frames, never
  a growing backlog.
- **Edge-native & self-hosted.** Inference runs on your hardware. No frames leave
  the box unless you want them to.
- **Model-agnostic.** Detectors and VLMs sit behind clean abstractions — swap
  YOLO for a transformer detector, or a local VLM for a cloud one, without
  touching the pipeline.
- **Graceful degradation.** Every layer fails soft: if semantics drop, geometric
  perception stays live; sources reconnect with exponential backoff; one stream's
  crash never takes down another.

## Architecture

| Layer | Technology |
|---|---|
| Ingest gateway | WebRTC / WHIP · RTSP · SRT · HLS, normalized to one stream |
| Decode | PyAV / FFmpeg, zero-copy frames |
| Detection + tracking | YOLO (NMS-free) + ByteTrack on Apple Silicon (MPS) |
| Semantic understanding | Vision-language models via MLX (on-device) or cloud |
| Scene state & events | Event-sourced scene graph |
| Real-time sync | **PowerSync** (local-first, WASM SQLite) |
| Query layer | Conversational agent over live + historical state |

## Quickstart

```bash
git clone https://github.com/osamabinIaggin/argus.git
cd argus

# Dedicated inference environment (Apple Silicon)
python3.12 -m venv .venv
./.venv/bin/pip install -r streaming/requirements.txt ultralytics

# Live perception on your webcam — detection, tracking, scene state, events
./.venv/bin/python -m streaming.run_tier3 --device 0
```

See [`streaming/README.md`](streaming/README.md) for sources
(iPhone, RTSP, robot), zone configuration, and the semantic layer.

## Contributing

Argus is open source and contributions are welcome — new sources, detectors,
VLM backends, and sync targets all plug into existing interfaces. Open an issue
to discuss a direction, or send a PR. Run the test suite with:

```bash
./.venv/bin/python -m pytest streaming/tests/ -q
```

## License

MIT
