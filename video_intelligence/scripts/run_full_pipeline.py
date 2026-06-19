"""
Run a video through the full pipeline (all 8 stages):
  Preprocess → Keyframe extraction → YOLO → Vision model → Stitcher

Usage: python scripts/run_full_pipeline.py <input_video> [output_dir]
Requires: GEMINI_API_KEY env var (or set in .env)
"""

import sys
import json
import os
import time
import argparse
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai

from pipeline.preprocessor import preprocess
from pipeline.keyframe_extractor import extract_keyframes
from pipeline.yolo_analyzer import analyze_keyframes, load_model
from pipeline.audio_analyzer import analyze_audio
from pipeline.vision_model import describe_keyframes
from pipeline.stitcher import stitch


# Gemini 2.5 Flash pricing (non-thinking mode)
_INPUT_PRICE_PER_M  = 0.15   # $/1M input tokens  (text + image)
_OUTPUT_PRICE_PER_M = 0.60   # $/1M output tokens


class TokenTracker:
    """
    Thin wrapper around genai.Client that accumulates usage_metadata
    across every generate_content call (audio, vision, stitcher).
    """

    def __init__(self, client):
        self._client = client
        self.prompt_tokens     = 0
        self.candidates_tokens = 0
        self.thoughts_tokens   = 0
        self.calls             = 0

    class _ModelProxy:
        def __init__(self, real_models, tracker):
            self._real   = real_models
            self._tracker = tracker

        def generate_content(self, **kwargs):
            response = self._real.generate_content(**kwargs)
            u = getattr(response, "usage_metadata", None)
            if u:
                self._tracker.prompt_tokens     += getattr(u, "prompt_token_count",     0) or 0
                self._tracker.candidates_tokens += getattr(u, "candidates_token_count", 0) or 0
                self._tracker.thoughts_tokens   += getattr(u, "thoughts_token_count",   0) or 0
            self._tracker.calls += 1
            return response

    @property
    def models(self):
        return self._ModelProxy(self._client.models, self)

    # ---- cost helpers ----

    @property
    def total_input(self):
        return self.prompt_tokens

    @property
    def total_output(self):
        return self.candidates_tokens + self.thoughts_tokens

    @property
    def input_cost(self):
        return self.total_input * _INPUT_PRICE_PER_M / 1_000_000

    @property
    def output_cost(self):
        return self.total_output * _OUTPUT_PRICE_PER_M / 1_000_000

    @property
    def total_cost(self):
        return self.input_cost + self.output_cost


def fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:05.2f}"


def main():
    parser = argparse.ArgumentParser(
        description="Run a video through the full pipeline."
    )
    parser.add_argument("input_video", help="Path to the input video file")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
        ),
        help="Directory for output files (default: video_intelligence/output/)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=5,
        metavar="N",
        help="Target frame rate for preprocessing (default: 5). "
             "Higher values (e.g. 15) improve temporal resolution at extra cost.",
    )
    args = parser.parse_args()

    input_path = args.input_video
    output_dir = args.output_dir
    target_fps = args.fps
    os.makedirs(output_dir, exist_ok=True)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set.")
        sys.exit(1)

    # Single tracked client shared across all API-calling stages
    tracker = TokenTracker(genai.Client(api_key=api_key))

    total_start = time.time()

    # ------------------------------------------------------------------ #
    # Stage 1: Preprocess
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("STAGE 1 — FFmpeg Preprocessing")
    print("=" * 60)
    t0 = time.time()
    preprocess_result = preprocess(input_path, output_dir=output_dir, target_fps=target_fps)
    t_preprocess = time.time() - t0
    meta = preprocess_result.metadata
    print(f"  Original  : {meta.original_width}x{meta.original_height} @ {meta.original_fps}fps")
    print(f"  Processed : {preprocess_result.processed_width}x{preprocess_result.processed_height} @ {target_fps}fps")
    print(f"  Duration  : {meta.duration_seconds:.1f}s")
    print(f"  Time      : {t_preprocess:.1f}s")

    # ------------------------------------------------------------------ #
    # Stage 2+3: Keyframe extraction
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("STAGE 2+3 — Scene Detection + Keyframe Extraction")
    print("=" * 60)
    t0 = time.time()
    keyframes = extract_keyframes(preprocess_result.processed_video_path)
    t_keyframes = time.time() - t0

    cap = cv2.VideoCapture(preprocess_result.processed_video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    force_sampled = [kf for kf in keyframes if kf.force_sampled]
    genuine = [kf for kf in keyframes if not kf.force_sampled]
    print(f"  Total frames   : {total_frames}")
    print(f"  Keyframes      : {len(keyframes)}  ({len(genuine)} genuine / {len(force_sampled)} force-sampled)")
    print(f"  Dropped        : {total_frames - len(keyframes)}  ({(1 - len(keyframes)/total_frames)*100:.1f}% dedup)")
    print(f"  Time           : {t_keyframes:.1f}s")

    # ------------------------------------------------------------------ #
    # Stage 4: YOLO
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("STAGE 4 — YOLOv8n Object Detection")
    print("=" * 60)
    t0 = time.time()
    yolo_model = load_model()
    scored = analyze_keyframes(keyframes, model=yolo_model)
    t_yolo = time.time() - t0
    all_objects = sorted(set(obj for sk in scored for obj in sk.yolo.detected_objects))
    print(f"  Frames analyzed     : {len(scored)}")
    print(f"  With detections     : {sum(1 for s in scored if s.yolo.detected_objects)}")
    print(f"  Unique classes      : {all_objects if all_objects else 'none'}")
    print(f"  Time                : {t_yolo:.1f}s")

    # ------------------------------------------------------------------ #
    # Stage 4.5: Audio analysis
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("STAGE 4.5 — Audio Analysis (Gemini Flash)")
    print("=" * 60)
    t0 = time.time()
    audio_segments = analyze_audio(
        preprocess_result.audio_path,
        duration=meta.duration_seconds,
        client=tracker,
    )
    t_audio = time.time() - t0
    tokens_after_audio = tracker.prompt_tokens + tracker.candidates_tokens
    if preprocess_result.audio_path is None:
        print("  No audio track — skipped")
    elif not audio_segments:
        print("  Audio track present but no segments returned (API issue or silent)")
    else:
        speech  = [s for s in audio_segments if s.segment_type == "speech"]
        events  = [s for s in audio_segments if s.segment_type == "event"]
        ambient = [s for s in audio_segments if s.segment_type == "ambient"]
        music   = [s for s in audio_segments if s.segment_type == "music"]
        silence = [s for s in audio_segments if s.segment_type == "silence"]
        print(f"  Segments detected  : {len(audio_segments)}")
        print(f"    speech           : {len(speech)}")
        print(f"    event            : {len(events)}")
        print(f"    ambient          : {len(ambient)}")
        print(f"    music            : {len(music)}")
        print(f"    silence          : {len(silence)}")
        print(f"  Tokens (this stage): {tokens_after_audio:,}")
        print(f"  Time               : {t_audio:.1f}s")

    # ------------------------------------------------------------------ #
    # Stage 5: Vision model (Gemini Flash)
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("STAGE 5 — Vision Model (Gemini Flash) — per-keyframe description")
    print("=" * 60)
    print(f"  Sending {len(scored)} frames in batches of 25...")
    if audio_segments:
        print(f"  Audio context      : {len(audio_segments)} segments injected per frame window")
    tokens_before_vision = tracker.prompt_tokens + tracker.candidates_tokens
    t0 = time.time()
    described = describe_keyframes(
        scored,
        client=tracker,
        audio_segments=audio_segments or None,
    )
    t_vision = time.time() - t0
    tokens_vision = (tracker.prompt_tokens + tracker.candidates_tokens) - tokens_before_vision
    print(f"  Described          : {len(described)} frames")
    print(f"  Tokens (this stage): {tokens_vision:,}")
    print(f"  Time               : {t_vision:.1f}s")

    # ------------------------------------------------------------------ #
    # Stage 6+7: Stitcher + summary
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("STAGE 6+7 — Stitcher + Summary LLM call")
    print("=" * 60)
    tokens_before_stitch = tracker.prompt_tokens + tracker.candidates_tokens
    t0 = time.time()
    result = stitch(
        described=described,
        preprocess_result=preprocess_result,
        total_frames=total_frames,
        processing_time_s=time.time() - total_start,
        summary_model=tracker,
    )
    t_stitch = time.time() - t0
    tokens_stitch = (tracker.prompt_tokens + tracker.candidates_tokens) - tokens_before_stitch
    print(f"  Summary generated  : {t_stitch:.1f}s")
    print(f"  Tokens (this stage): {tokens_stitch:,}")
    print(f"  Video ID           : {result['video_id']}")
    print(f"  Status             : {result['status']}")

    total_time = time.time() - total_start

    # ------------------------------------------------------------------ #
    # Print final output
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  {result['summary']}")
    print()
    print("TIMELINE")
    print("-" * 60)
    for entry in result["timeline"]:
        flags = []
        if entry["scene_change"]:
            flags.append("SCENE_CHANGE")
        camera = f"  [{entry['camera_movement']}]" if entry["camera_movement"] != "static" else ""
        objs = f"  → {', '.join(entry['detected_objects'])}" if entry["detected_objects"] else ""
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  [{entry['keyframe_id']:3d}] {entry['timestamp_start']} → {entry['timestamp_end']}"
              f"{camera}{objs}{flag_str}")
        print(f"       {entry['description']}")
        if entry["actions"]:
            print(f"       Actions: {entry['actions']}")
        print()

    # ------------------------------------------------------------------ #
    # Cost report
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("TOKEN & COST REPORT")
    print("=" * 60)
    print(f"  API calls          : {tracker.calls}")
    print(f"  Input tokens       : {tracker.total_input:>10,}")
    print(f"  Output tokens      : {tracker.total_output:>10,}")
    if tracker.thoughts_tokens:
        print(f"    of which thinking: {tracker.thoughts_tokens:>10,}")
    print(f"  ──────────────────────────────")
    print(f"  Input cost         :     ${tracker.input_cost:.5f}  (@ ${_INPUT_PRICE_PER_M}/1M)")
    print(f"  Output cost        :     ${tracker.output_cost:.5f}  (@ ${_OUTPUT_PRICE_PER_M}/1M)")
    print(f"  Total cost         :     ${tracker.total_cost:.5f}")
    print()
    print(f"  Total pipeline time : {total_time:.1f}s")

    # Write full JSON output
    out_path = os.path.join(output_dir, "full_pipeline_result.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full result written : {out_path}")


if __name__ == "__main__":
    main()
