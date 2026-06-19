"""
Run a video through the full pipeline (stages 1-4):
  Preprocess → Keyframe extraction → YOLO analysis

Usage: python scripts/run_pipeline.py <input_video> [output_dir]
"""

import sys
import json
import os
import time
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.preprocessor import preprocess
from pipeline.keyframe_extractor import extract_keyframes
from pipeline.yolo_analyzer import analyze_keyframes, load_model


def fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:05.2f}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_pipeline.py <input_video> [output_dir]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
    )
    frames_dir = os.path.join(output_dir, "keyframes_yolo")
    os.makedirs(frames_dir, exist_ok=True)

    total_start = time.time()

    # ------------------------------------------------------------------ #
    # Stage 1: Preprocess
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("STAGE 1 — FFmpeg Preprocessing")
    print("=" * 60)
    t0 = time.time()
    preprocess_result = preprocess(input_path, output_dir=output_dir)
    t_preprocess = time.time() - t0

    meta = preprocess_result.metadata
    print(f"  Original  : {meta.original_width}x{meta.original_height} @ {meta.original_fps}fps")
    print(f"  Processed : {preprocess_result.processed_width}x{preprocess_result.processed_height} @ 15fps")
    print(f"  Duration  : {meta.duration_seconds:.1f}s")
    print(f"  Audio     : {'extracted' if preprocess_result.audio_path else 'none'}")
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

    print(f"  Total frames in processed video : {total_frames}")
    print(f"  Keyframes extracted             : {len(keyframes)}")
    print(f"    Genuine (pHash change)        : {len(genuine)}")
    print(f"    Force-sampled (density gap)   : {len(force_sampled)}")
    print(f"  Frames dropped as duplicates    : {total_frames - len(keyframes)}")
    print(f"  Dedup rate                      : {(1 - len(keyframes)/total_frames)*100:.1f}%")
    print(f"  Time                            : {t_keyframes:.1f}s")

    # ------------------------------------------------------------------ #
    # Stage 4: YOLO
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("STAGE 4 — YOLOv8n Analysis")
    print("=" * 60)
    print("  Loading model...")
    t0 = time.time()
    model = load_model()
    scored = analyze_keyframes(keyframes, model=model)
    t_yolo = time.time() - t0

    frames_with_detections = [s for s in scored if s.yolo.detected_objects]
    all_objects = []
    for s in scored:
        all_objects.extend(s.yolo.detected_objects)
    unique_objects = sorted(set(all_objects))

    print(f"  Frames analyzed                 : {len(scored)}")
    print(f"  Frames with detections          : {len(frames_with_detections)}")
    print(f"  Frames with no detections       : {len(scored) - len(frames_with_detections)}")
    print(f"  Unique object classes found     : {unique_objects if unique_objects else 'none'}")
    print(f"  Time                            : {t_yolo:.1f}s")

    # ------------------------------------------------------------------ #
    # Save annotated keyframe images
    # ------------------------------------------------------------------ #
    print()
    print(f"Saving annotated keyframes to {frames_dir}/")
    for sk in scored:
        fname = f"kf_{sk.keyframe_id:04d}_{fmt_ts(sk.timestamp_start).replace(':', 'm').replace('.', 's')}.jpg"
        cv2.imwrite(os.path.join(frames_dir, fname), sk.image)

    total_time = time.time() - total_start

    # ------------------------------------------------------------------ #
    # Full timeline output
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("FULL KEYFRAME TIMELINE")
    print("=" * 60)
    for sk in scored:
        flags = []
        if sk.scene_change:
            flags.append("SCENE_CHANGE")
        if sk.force_sampled:
            flags.append("FORCE_SAMPLED")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        objects_str = f"  → {', '.join(sk.yolo.detected_objects)}" if sk.yolo.detected_objects else "  → (no detections)"
        conf_str = f"  conf={sk.yolo.frame_confidence:.2f}" if sk.yolo.frame_confidence > 0 else ""
        print(f"  [{sk.keyframe_id:3d}] {fmt_ts(sk.timestamp_start)} → {fmt_ts(sk.timestamp_end)}"
              f"{objects_str}{conf_str}{flag_str}")

    # ------------------------------------------------------------------ #
    # Build and write JSON report
    # ------------------------------------------------------------------ #
    report = {
        "pipeline_stages_run": ["preprocess", "keyframe_extraction", "yolo"],
        "timing": {
            "preprocess_seconds": round(t_preprocess, 2),
            "keyframe_extraction_seconds": round(t_keyframes, 2),
            "yolo_seconds": round(t_yolo, 2),
            "total_seconds": round(total_time, 2),
        },
        "video_metadata": {
            "original_resolution": f"{meta.original_width}x{meta.original_height}",
            "processed_resolution": f"{preprocess_result.processed_width}x{preprocess_result.processed_height}",
            "original_fps": meta.original_fps,
            "processed_fps": preprocess_result.processed_fps,
            "duration_seconds": round(meta.duration_seconds, 2),
        },
        "extraction_summary": {
            "total_frames": total_frames,
            "keyframes_extracted": len(keyframes),
            "genuine_keyframes": len(genuine),
            "force_sampled_keyframes": len(force_sampled),
            "frames_dropped": total_frames - len(keyframes),
            "dedup_rate_percent": round((1 - len(keyframes) / total_frames) * 100, 1),
        },
        "yolo_summary": {
            "frames_with_detections": len(frames_with_detections),
            "frames_no_detections": len(scored) - len(frames_with_detections),
            "unique_object_classes": unique_objects,
        },
        "keyframes": [
            {
                "keyframe_id": sk.keyframe_id,
                "scene_id": sk.scene_id,
                "timestamp_start": fmt_ts(sk.timestamp_start),
                "timestamp_end": fmt_ts(sk.timestamp_end),
                "timestamp_start_seconds": round(sk.timestamp_start, 3),
                "timestamp_end_seconds": round(sk.timestamp_end, 3),
                "scene_change": bool(sk.scene_change),
                "force_sampled": bool(sk.force_sampled),
                "yolo": {
                    "detected_objects": sk.yolo.detected_objects,
                    "frame_confidence": sk.yolo.frame_confidence,
                    "yolo_context": sk.yolo.yolo_context,
                },
            }
            for sk in scored
        ],
    }

    report_path = os.path.join(output_dir, "pipeline_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total pipeline time : {total_time:.1f}s")
    print(f"  Keyframes → vision  : {len(scored)} frames queued")
    print(f"  Report written to   : {report_path}")


if __name__ == "__main__":
    main()
