"""
Runs stages 1-4 then shows exactly what would be sent to the Gemini vision API,
without making any actual API call.
"""

import sys
import os
import cv2
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.preprocessor import preprocess
from pipeline.keyframe_extractor import extract_keyframes
from pipeline.yolo_analyzer import analyze_keyframes, load_model
from pipeline.vision_model import (
    _build_batch_parts, BATCH_SIZE, SYSTEM_PROMPT,
    MODEL_NAME, MAX_TOKENS, TEMPERATURE,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_vision_payload.py <input_video>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
    )
    os.makedirs(output_dir, exist_ok=True)

    # ── Stages 1-4 (silent) ──────────────────────────────────────────────
    preprocess_result = preprocess(input_path, output_dir=output_dir)
    keyframes = extract_keyframes(preprocess_result.processed_video_path)
    cap = cv2.VideoCapture(preprocess_result.processed_video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    yolo_model = load_model()
    scored = analyze_keyframes(keyframes, model=yolo_model)

    # ── Build batches ────────────────────────────────────────────────────
    batches = [
        scored[i: i + BATCH_SIZE]
        for i in range(0, len(scored), BATCH_SIZE)
    ]
    total_batches = len(batches)
    video_duration = scored[-1].timestamp_end

    print("=" * 70)
    print("VISION MODEL CALL OVERVIEW")
    print("=" * 70)
    print(f"  Model        : {MODEL_NAME}")
    print(f"  Total frames : {len(scored)}")
    print(f"  Batch size   : {BATCH_SIZE}")
    print(f"  Batches      : {total_batches}  →  {' + '.join(str(len(b)) for b in batches)} frames")
    print(f"  Max tokens   : {MAX_TOKENS} per call")
    print(f"  Temperature  : {TEMPERATURE}")

    print()
    print("=" * 70)
    print("SYSTEM PROMPT (sent once, applies to all batches)")
    print("=" * 70)
    print(SYSTEM_PROMPT)

    for batch_num, batch in enumerate(batches, start=1):
        parts = _build_batch_parts(
            batch=batch,
            prev_tail=[],   # show first batch as-is; tail is runtime state
            batch_num=batch_num,
            total_batches=total_batches,
            video_duration=video_duration,
        )

        text_parts  = [p for p in parts if isinstance(p, str)]
        image_parts = [p for p in parts if isinstance(p, Image.Image)]

        print()
        print("=" * 70)
        print(f"BATCH {batch_num}/{total_batches}  —  frames {batch[0].keyframe_id}–{batch[-1].keyframe_id}")
        print("=" * 70)
        print(f"  Parts breakdown: {len(text_parts)} text blocks + {len(image_parts)} images")
        print()

        for part in parts:
            if isinstance(part, str):
                print("── TEXT PART " + "─" * 55)
                print(part)
                print()
            elif isinstance(part, Image.Image):
                kf_index = image_parts.index(part) + (batch_num - 1) * BATCH_SIZE + 1
                print(f"── IMAGE  [{part.width}×{part.height} RGB  frame in batch position {image_parts.index(part)+1}] ──")
                print()

        # Rough token estimate (text only; images billed separately by resolution)
        total_chars = sum(len(p) for p in text_parts)
        est_text_tokens = total_chars // 4
        # Gemini Flash image cost: 258 tokens per image at ≤384px short side
        # Our images are 852x480 — short side 480 > 384, so billed as tiles
        # 480/384 rounds to 1 tile high, 852/384 rounds to 2 tiles wide → ~4 tiles
        img_tokens = len(image_parts) * 258 * 2   # rough: 2 tiles each
        print(f"── TOKEN ESTIMATE (batch {batch_num}) " + "─" * 35)
        print(f"  Text characters    : {total_chars:,}")
        print(f"  Est. text tokens   : ~{est_text_tokens:,}")
        print(f"  Images             : {len(image_parts)}  ×  ~516 tokens  =  ~{img_tokens:,}")
        print(f"  Est. INPUT total   : ~{est_text_tokens + img_tokens:,} tokens")
        print(f"  Max OUTPUT tokens  : {MAX_TOKENS}  (for {len(batch)} frame descriptions)")
        print()

    print("=" * 70)
    print("EXPECTED RESPONSE SCHEMA (one object per frame)")
    print("=" * 70)
    print("""[
  {
    "keyframe_id": <int>,
    "description": "<what is visible and happening, 1-3 sentences>",
    "camera_movement": "<static|pan_left|pan_right|tilt_up|tilt_down|zoom_in|zoom_out|cut|unknown>",
    "actions": "<movement or actions occurring, empty string if none>",
    "changes_from_previous": "<what changed since the previous frame>"
  },
  ...  (one entry per frame in the batch)
]""")


if __name__ == "__main__":
    main()
