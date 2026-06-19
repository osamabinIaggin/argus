"""
Run a preprocessed video through the keyframe extractor and write a report.
Usage: python scripts/run_keyframe_extractor.py <processed_video> [output_dir]
"""

import sys
import json
import os
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.keyframe_extractor import extract_keyframes, detect_scenes


def fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:05.2f}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_keyframe_extractor.py <processed_video> [output_dir]")
        sys.exit(1)

    video_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
    )
    frames_dir = os.path.join(output_dir, "keyframes")
    os.makedirs(frames_dir, exist_ok=True)

    print(f"Video:      {video_path}")
    print(f"Output dir: {output_dir}")

    # --- Scene detection pass (for report) ---
    print("\n[1/2] Detecting scenes...")
    scenes = detect_scenes(video_path)
    print(f"      {len(scenes)} scene(s) detected")
    for i, (s, e) in enumerate(scenes, 1):
        print(f"      Scene {i}: {fmt_ts(s)} → {fmt_ts(e)}  ({e - s:.1f}s)")

    # --- Keyframe extraction ---
    print("\n[2/2] Extracting keyframes...")
    keyframes = extract_keyframes(video_path)
    print(f"      {len(keyframes)} keyframe(s) extracted")

    # --- Save keyframe images ---
    print(f"\nSaving keyframe images to {frames_dir}/")
    for kf in keyframes:
        fname = f"kf_{kf.keyframe_id:04d}_scene{kf.scene_id}_{fmt_ts(kf.timestamp_start).replace(':', 'm').replace('.', 's')}.jpg"
        fpath = os.path.join(frames_dir, fname)
        cv2.imwrite(fpath, kf.image)

    # --- Build report ---
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0
    cap.release()

    force_sampled = [kf for kf in keyframes if kf.force_sampled]
    scene_changes = [kf for kf in keyframes if kf.scene_change]

    report = {
        "video_path": video_path,
        "video_stats": {
            "total_frames": total_frames,
            "fps": fps,
            "duration_seconds": round(duration, 2),
        },
        "extraction_summary": {
            "scenes_detected": len(scenes),
            "keyframes_extracted": len(keyframes),
            "frames_dropped_as_duplicates": total_frames - len(keyframes),
            "dedup_rate_percent": round((1 - len(keyframes) / total_frames) * 100, 1),
            "force_sampled_count": len(force_sampled),
            "scene_change_keyframes": len(scene_changes),
        },
        "scenes": [
            {"scene_id": i + 1, "start": round(s, 3), "end": round(e, 3), "duration": round(e - s, 2)}
            for i, (s, e) in enumerate(scenes)
        ],
        "keyframes": [
            {
                "keyframe_id": kf.keyframe_id,
                "scene_id": kf.scene_id,
                "timestamp_start": fmt_ts(kf.timestamp_start),
                "timestamp_end": fmt_ts(kf.timestamp_end),
                "timestamp_start_seconds": round(kf.timestamp_start, 3),
                "timestamp_end_seconds": round(kf.timestamp_end, 3),
                "scene_change": bool(kf.scene_change),
                "force_sampled": bool(kf.force_sampled),
                "frame_number": kf.frame_number,
            }
            for kf in keyframes
        ],
    }

    report_path = os.path.join(output_dir, "keyframe_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # --- Console summary ---
    print("\n" + "=" * 55)
    print("KEYFRAME EXTRACTION SUMMARY")
    print("=" * 55)
    print(f"  Total frames in video : {total_frames}")
    print(f"  Keyframes kept        : {len(keyframes)}")
    print(f"  Frames dropped (dedup): {total_frames - len(keyframes)}")
    print(f"  Dedup rate            : {report['extraction_summary']['dedup_rate_percent']}%")
    print(f"  Scenes detected       : {len(scenes)}")
    print(f"  Force-sampled frames  : {len(force_sampled)}")
    print(f"  Scene-change frames   : {len(scene_changes)}")
    print("=" * 55)
    print("\nKeyframe timeline:")
    for kf in keyframes:
        flags = []
        if kf.scene_change:
            flags.append("SCENE_CHANGE")
        if kf.force_sampled:
            flags.append("FORCE_SAMPLED")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  [{kf.keyframe_id:3d}] {fmt_ts(kf.timestamp_start)} → {fmt_ts(kf.timestamp_end)}  scene={kf.scene_id}{flag_str}")

    print(f"\nFull report: {report_path}")
    print(f"Keyframe images: {frames_dir}/")


if __name__ == "__main__":
    main()
