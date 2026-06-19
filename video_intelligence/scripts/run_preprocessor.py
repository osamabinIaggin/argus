"""
Quick script to run a video through the preprocessor and write the result to a file.
Usage: python scripts/run_preprocessor.py <input_video> [output_dir]
"""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.preprocessor import preprocess

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_preprocessor.py <input_video> [output_dir]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output"
    )

    print(f"Input:      {input_path}")
    print(f"Output dir: {output_dir}")
    print("Running preprocessor...")

    result = preprocess(input_path, output_dir=output_dir)

    report = {
        "processed_video_path": result.processed_video_path,
        "audio_path": result.audio_path,
        "processed_width": result.processed_width,
        "processed_height": result.processed_height,
        "metadata": {
            "duration_seconds": result.metadata.duration_seconds,
            "original_fps": result.metadata.original_fps,
            "original_resolution": f"{result.metadata.original_width}x{result.metadata.original_height}",
            "processed_resolution": f"{result.processed_width}x{result.processed_height}",
            "is_portrait": result.metadata.is_portrait,
        }
    }

    report_path = os.path.join(output_dir, "preprocess_report.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print("\nDone.")
    print(json.dumps(report, indent=2))
    print(f"\nReport written to: {report_path}")

if __name__ == "__main__":
    main()
