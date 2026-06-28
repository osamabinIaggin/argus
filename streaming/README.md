# streaming/ — real-time live camera understanding

The live counterpart to the batch `pipeline/` module. Ingests an *unbounded*
stream (webcam, iPhone, IP camera, robot) and maintains a continuously-updated
understanding of what is happening, pushed to clients in real time.

> Status: **Phases 1–4 done.** Ingest, Tier 1 (detection+tracking), Tier 3 (scene
> state + event log), and Tier 2 (gated VLM, off the critical path) run together
> in real time. The PowerSync push / dashboard is next.

## Architecture (tiered cascade)

```
sources → Tier 1 (YOLO + tracker, always on)   ~real-time, no LLM cost     [done]
        → Tier 2 (gated VLM, on trigger/heartbeat)   ~1 fps, semantic       [done]
        → Tier 3 (scene state + derived event log)                          [done]
        → PowerSync → dashboard / chat / robot planner                      [next]
```

Data flows Tier 1 → Tier 3: the detector emits `DetectionResult`s, the
`SceneTracker` folds them into the source-of-truth `SceneState`, and the event
log falls out of state transitions. Tier 2's semantic text is injected into the
same state via `note_semantic` — it is never on the critical path, so if the VLM
is down the geometric state stays fully live (just flagged stale).

Two robustness guarantees are built into the ingest base class so every source
inherits them:

1. **Drop-stale, never lag.** A decode thread writes into a size-1 slot; a slow
   consumer gets *fewer* frames but always the *freshest* one. Latency stays
   bounded under backpressure. (`LatestFrameSlot` in `sources/base.py`.)
2. **Automatic reconnect with backoff.** Any decode error → `RECONNECTING` →
   exponential backoff → retry, with state + failure counts surfaced.

## Setup

```bash
# from the repo root
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

## Try it (Phase 3 — scene state, end to end)

Runs source → Tier 1 → Tier 3 together and streams the derived event log. Needs
the Tier 1 deps (torch/ultralytics) in the venv.

```bash
# Sample clip with people — no camera needed:
./.venv/bin/python -m streaming.run_tier3 --video stock-footage-lab-*.webm --seconds 12

# Add a restricted zone over the right half (entry → zone_breach events):
./.venv/bin/python -m streaming.run_tier3 --video stock-footage-lab-*.webm \
    --zone "right_half:restricted:0.5,0,1,1" --seconds 12

# Live camera / iPhone Continuity:
./.venv/bin/python -m streaming.run_tier3 --device 0
```

Zone CLI syntax (repeatable): `NAME:KIND:x1,y1,x2,y2`, coords normalized 0..1,
`KIND` = `area | restricted`. Programmatic polygons go through the `Zone` API.

## Layout

```
streaming/
  frame.py              Frame dataclass (RGB ndarray + seq/ts/pts metadata)
  detection.py          Tier 1 output: Detection / DetectionResult (model-agnostic)
  sources/
    base.py             FrameSource (supervision + reconnect) + LatestFrameSlot
    pyav_source.py      PyAV adapter: RTSP / network URL / lavfi-test
    ffmpeg_process.py   FFmpeg-subprocess adapter: Mac capture devices (avfoundation)
  tier1/
    detector.py         Detector ABC (swappable)
    yolo_detector.py    YOLO26 + ByteTrack on MPS (default)
  scene/                Tier 3 — scene state (source of truth)
    state.py            Entity / SemanticState / SceneState (+ JSON snapshot)
    zones.py            Zone (normalized polygons, ray-cast containment)
    events.py           Event / EventLog (derived, bounded ring + subscribers)
    tracker.py          SceneTracker — DetectionResults → state → events
  tier2/                Tier 2 — gated semantic understanding ("what's happening")
    understanding.py    SceneUnderstander ABC + SceneObservation (swappable)
    controller.py       Tier2Controller — gating (triggers + heartbeat), off critical path
    fastvlm_mlx.py      FastVLM on MLX (Apple Silicon) backend
    stub.py             StubSceneUnderstander (deterministic, for tests/offline)
  spike.py              Phase 1 ingest CLI harness
  run_tier1.py          Phase 2 detection+tracking CLI
  run_tier3.py          Phase 3/4 CLI (source → Tier 1 → Tier 3, optional --vlm Tier 2)
  tests/                drop-stale + reconnect + subprocess + scene-state + tier2 tests
```

## Tier 3 design (scene state)

- **State is truth, events are derived.** `SceneState` holds current reality
  (entities, zone occupancy, activity, last semantic read). The event log is
  produced *only* from transitions in that state.
- **Debounced lifecycle (robustness).** A new track id is `tentative` until it
  persists for `confirm_seconds` (default 0.3s) → then `entity_entered` fires
  once. A vanished entity is kept through `exit_grace_seconds` (default 1.5s)
  before `entity_exited`, absorbing ByteTrack id flicker so the log stays clean.
- **Resolution-independent zones.** Polygons live in normalized 0..1 coords, so
  the same config works at 640×480 or 4K and survives a reconnect at a new size.
  Membership uses the bottom-center (ground-contact) anchor by default.
- **Activity** is a smoothed mean of confirmed-entity center speed, banded
  idle/low/medium/high, emitting `activity_change` on band crossings.
- **Semantic slot** is owned by Tier 2 via `note_semantic`; Tier 3 only stores
  it and tracks staleness — graceful degradation if the VLM is down.
- **Tier-4 seam:** `tracker.events.subscribe(cb)` delivers every event to a sink
  (the future PowerSync push). Subscriber exceptions are isolated.

## Tier 2 design (gated semantic understanding)

The expensive "what is happening" layer — a vision-language model — run sparingly
and never on the critical path.

- **Swappable backend.** `SceneUnderstander.observe(frame, context)` is the only
  contract; `FastVLMUnderstander` (Apple FastVLM on MLX), `StubSceneUnderstander`
  (tests/offline), and future Ollama / Qwen3-VL / Gemini backends all implement
  it. Default model: `mlx-community/FastVLM-0.5B-bf16`.
- **Gating = triggers OR heartbeat.** A trigger-worthy Tier-1 event (new entity,
  zone breach, activity-band change) marks the scene dirty and earns a refresh;
  a `heartbeat_s` floor guarantees the read never goes silently ancient. A
  `min_interval_s` rate cap matches realistic on-device VLM throughput (~1 fps).
- **Off the critical path.** A worker thread does the slow inference; the Tier-3
  loop only calls `controller.offer(frame)` (cheap peek-latest). The worker
  always reasons over the *freshest* frame (drop-stale), so a slow model means
  fewer, fresher reads — never a backlog. Tier 1/3 stay real-time.
- **Graceful degradation.** A backend failure is counted and backed off; the
  scene keeps its last semantic read, flagged stale. The pipeline never crashes
  on a model hiccup — `observe()` returns `SceneObservation.failure(...)`, never
  raises.
- **Grounded prompt.** The VLM gets a compact text summary of Tier-1 truth
  (entity counts, zones, activity) alongside the image, so it describes the real
  scene rather than hallucinating from pixels alone.

Run it: `--vlm stub` (no model) or `--vlm fastvlm` (needs `pip install mlx-vlm pillow`).

## Roadmap — researched bleeding-edge upgrades (apply in-phase)

Validated against the live 2026 landscape; each is parked at the phase it belongs
to so we adopt it where it actually pays off rather than chasing hype everywhere.

| Upgrade | Phase | Status | Notes |
|---|---|---|---|
| **YOLO26** (NMS-free, end-to-end) as Tier-1 default | Tier 1 (done) | **applied** | Verified on MPS: ~30fps, 12-18ms, stable ByteTrack ids. Swappable; `yolov8n.pt` stays as offline fallback. |
| **yolo-mlx** MLX-native backend | Tier 1 | parked | 1.1-2.6x faster than PyTorch-MPS on Apple Silicon. Add as a `Detector` subclass behind the existing ABC. |
| **RF-DETR** (DINOv2 transformer) | Tier 1 | parked | Leads accuracy/occlusion but heavier & NVIDIA-tuned — a precision-mode swappable option, not the default. |
| **FastVLM** (Apple, MLX) as Tier-2 default | Tier 2 (done) | **applied** | Gated VLM behind `SceneUnderstander`; off critical path; graceful degradation. Moondream/Qwen3-VL/Gemini are drop-in alternates. |
| Image/KV caching (encode once, ask many) | Tier 6 chat | parked | The 21.7s→0.78s path — matters for multi-question grounding, not the heartbeat. Add via a `prepare`/`ask` seam on `SceneUnderstander`. |
| **TOON** (Token-Oriented Object Notation) at the LLM boundary | Tier 4 / chat | parked | ~40% fewer tokens, equal/better parse accuracy, on **uniform arrays** (our `entities[]` + event log). Hybrid: TOON for tables, compact JSON for nested/scalar. Keep JSON `snapshot()` for PowerSync/storage. Pure-Python `toon-format` lib. |
| **Token benchmark** (JSON vs TOON on a real snapshot) | Tier 4 / chat | parked | Adopt TOON on measured numbers, not blog claims. |

## Tests

```bash
./.venv/bin/python -m pytest streaming/tests/ -q
```
