# Video Intelligence API — Architecture Plan

## What This Is

An orchestration layer, not an AI model. Takes video input, runs it through a smart
preprocessing pipeline, and returns a structured timestamped JSON description of the
entire video — intended as context for LLMs or AI agents.

Core insight: reduce thousands of frames to hundreds before touching an expensive
vision model. You pay for ~250 frames instead of 3,600.

---

## Input Types

| Type | Notes |
|---|---|
| File upload | mp4, mov, avi, mkv, webm |
| URL | YouTube, Dropbox, direct links — download first |
| Live stream | RTSP/HLS — v2 only, different pipeline |

---

## The Full Pipeline (locked)

```
INPUT (file / URL)
      ↓
[1] INGEST & VALIDATE
    - Check format (mp4, mov, avi, mkv, webm)
    - Check duration (enforce limits per plan)
    - Download if URL
      ↓
[2] PREPROCESSING (FFmpeg)
    - Reduce to 15fps
    - Resize: 854x480 landscape / 640px wide portrait (maintain aspect ratio)
    - Strip audio to separate track (future audio analysis)
      ↓
[3] KEYFRAME EXTRACTION
    a) PySceneDetect — hard cut detection (streaming, outputs boundaries as found)
    b) OpenCV pHash dedup within each scene segment (starts per-scene as boundaries arrive)
    c) Temporal density fallback:
       - If scene segment > 4s AND density < 1 keyframe/3s → force-sample to fill gaps
       - Guarantees coverage of slow camera movements (zoom, pan, tilt)
    - Timestamp each keyframe: start = frame_number / 15, end = next keyframe start
      ↓
[4] STAGE 1 — YOLOv8n (per keyframe, in memory)
    - Object detection → detected_objects list (feeds output schema directly)
    - Confidence scoring → confidence field in output
    - Oversensitive tuning (false positive preferred over false negative)
    - Minimum-per-scene guarantee: never hard-remove last frame of a scene
    - Low confidence frames deprioritized, not hard-removed (unless scene has others)
    - YOLO output injected as context into vision model prompt
      ↓
[5] STAGE 2 — Vision Model (per keyframe, in memory)
    - Input: frame image + YOLO detected objects + previous frame description
    - Prompt: structured, asks for objects, actions, scene, changes
    - Model: Gemini Flash (switchable)
    - Returns: JSON description per frame
      ↓
[6] STITCHING & SUMMARIZATION
    - Merge frame descriptions into timeline
    - Final LLM pass for overall summary + coherence check
      ↓
[7] OUTPUT
    - Structured JSON stored and returned via video_id
```

---

## Key Design Decisions (locked)

| Decision | Choice | Reason |
|---|---|---|
| Dedup method | pHash (perceptual hash) | Faster, robust to compression artifacts |
| Resolution | 854x480 landscape, 640px wide portrait | Maintains AR, enough detail for vision model |
| YOLO role | Object detection + confidence scoring (not just filter) | Populates detected_objects schema field, enriches vision model prompt |
| Scene guarantee | Minimum 1 keyframe per scene always kept | Prevents blind spots in single-shot scenes |
| Temporal fallback | Force-sample if density < 1/3s in segments > 4s | Covers slow zoom/pan/tilt video |
| Memory vs disk | Only FFmpeg output + final JSON touch disk | Everything else in memory to avoid I/O bottleneck |
| Processing | PySceneDetect streams boundaries → OpenCV starts per-scene immediately | Don't wait for full PySceneDetect pass |

---

## Output Schema (locked)

```json
{
  "video_id": "vid_abc123",
  "status": "complete",
  "metadata": {
    "duration_seconds": 127,
    "original_fps": 30,
    "processed_fps": 15,
    "original_resolution": "1920x1080",
    "processed_resolution": "854x480",
    "total_frames_extracted": 1905,
    "keyframes_analyzed": 280,
    "duplicates_removed": 285,
    "processing_time_seconds": 42
  },
  "summary": "A person assembles a robotic arm on a workbench...",
  "timeline": [
    {
      "keyframe_id": 1,
      "timestamp_start": "0:00",
      "timestamp_end": "0:04",
      "description": "A workbench with electronic components visible. A soldering iron is heating up on the right side.",
      "detected_objects": ["soldering iron", "workbench", "wires"],
      "scene_change": false,
      "confidence": 0.94
    }
  ]
}
```

---

## Performance Baseline (2 min standard phone video)

| Stage | Frames In | Frames Out | Est. Time |
|---|---|---|---|
| Raw video | 3,600 | 3,600 | — |
| 15fps reduction | 3,600 | 1,800 | ~5s |
| pHash dedup | 1,800 | 1,530 | ~8s |
| Scene + keyframe extraction | 1,530 | ~280 | ~10s |
| YOLOv8n Stage 1 | 280 | ~250 | ~8s |
| Vision model Stage 2 | 250 | 250 descriptions | ~40-60s |
| Stitching + summary | — | final JSON | ~5-10s |
| **Total** | | | **~80-100s** |

---

## Token Cost (real-world measured — 49.8s portrait 4K @ 5fps)

| Stage | Tokens | Cost |
|---|---|---|
| Audio analysis | 3,578 | ~$0.001 |
| Vision model (181 frames, 8 batches) | 76,755 | ~$0.012 |
| Stitcher + summary | 10,531 | ~$0.006 |
| **Total** | **90,864** | **$0.022** |

Pricing basis: Gemini 2.5 Flash, non-thinking mode
- Input: $0.15/1M tokens
- Output: $0.60/1M tokens
- Images resized to ≤768px (1 tile = 258 tokens each)

**Measured rate: ~$0.026/min of video**

Extrapolated to 2-min video: **~$0.05** (previously estimated $0.03 — old estimate
was based on 500 tokens/image; actual image tile size is 258 tokens at ≤768px)

---

## Tech Stack

| Layer | Technology |
|---|---|
| API server | FastAPI (Python) |
| Job queue | Redis + Celery |
| Video processing | FFmpeg + OpenCV + PySceneDetect |
| Stage 1 filter | YOLOv8n (Ultralytics) |
| Stage 2 vision | Gemini Flash (switchable) |
| Summary LLM | Gemini Flash |
| Storage | S3 / Cloudflare R2 |
| Database | PostgreSQL |
| Hosting | Hetzner / DigitalOcean VPS |
| Auth | API keys (JWT later) |

---

## API Endpoints

```
POST   /v1/analyze              → { video_id, status: "queued", eta_seconds }
GET    /v1/status/{video_id}    → { status, progress_percent }
GET    /v1/result/{video_id}    → full output JSON
DELETE /v1/result/{video_id}    → deletes result
POST   /v1/analyze/sync         → synchronous, short videos <60s only
```

---

## Pricing Tiers

| Plan | Price | Included | Overage | Token cost | Margin |
|---|---|---|---|---|---|
| Free | $0 | 10 min/month | N/A | ~$0.26 | Loss-leader |
| Starter | $19/mo | 300 min/month | $0.10/min | ~$7.80 | ~$11 (58%) |
| Pro | $79/mo | 1,500 min/month | $0.07/min | ~$39.00 | ~$40 (51%) |
| Enterprise | Custom | Unlimited | Custom | Negotiated | TBD |

Token cost basis: $0.026/min (measured, Gemini 2.5 Flash non-thinking, 5fps, 1-tile images)

Notes:
- Previous estimate of ~$135 for Pro was wrong — based on 500 tokens/image.
  Actual is 258 tokens/image (1 tile ≤768px). Pro margin is healthy at ~51%.
- Overage pricing ($0.07–0.10/min) gives ~2.7–3.8x markup over cost.
- At scale, Gemini volume discounts or a self-hosted model improve margins further.
- Free tier costs ~$0.26/month per active user — acceptable for conversion funnel.

---

## Build Order (MVP)

- [x] Plan locked
- [x] 1. Project structure + dependencies
- [x] 2. FFmpeg preprocessing (fps reduction + resize)          — 16 tests passing
- [x] 3. PySceneDetect scene boundary detection (streaming)     — 17 tests passing
- [x] 4. OpenCV pHash dedup + keyframe extraction per scene     — 17 tests passing
- [x] 5. Temporal density fallback (force-sample slow movement) — 17 tests passing
- [x] 6. YOLOv8n per keyframe (object detection + confidence)   — 25 tests passing (23 unit + 2 integration)
- [x] 7. Vision model call per keyframe (Gemini Flash)          — 52 tests passing
- [x] 8. JSON stitcher + output schema                          — 39 tests passing
- [x] 8.5 Audio analyzer                                        — 245 tests passing total
- [x] 9. FastAPI wrapper + async job queue (Redis + Celery)     ← DONE
- [x] 10. API key auth                                          ← DONE
- [ ] 11. Stripe billing                                        ← NEXT

### Validated on real video (file_example_MP4_1280_10MG.mp4 — Earth rotation, 30.5s)
- Full pipeline stages 1-4 run in 2.4s total
- 451 frames → 12 keyframes (97.3% dedup — correct for near-static content)
- YOLO: 11/12 frames with detections, misclassified Earth as bowl/donut/vase (expected — not a COCO class)
- Frame survival guarantee confirmed: 1 frame with zero detections still passed through

---

## What's v2 (not MVP)

- Live stream (RTSP/HLS) — completely different pipeline
- Audio analysis — track stripped but unused
- GPU inference — CPU-only for MVP
- Optical flow camera motion detection
