"""
Celery worker for the Video Intelligence pipeline.

Startup (from the video_intelligence/ directory):
  celery -A workers.pipeline_worker worker --loglevel=info

Required env vars:
  GEMINI_API_KEY   Gemini API key
  REDIS_URL        Redis URL (default: redis://localhost:6379/0)
  OUTPUT_DIR       Job output directory (default: <project_root>/output)
"""

import ipaddress
import json
import math
import os
import socket
import sys
from typing import Optional
from urllib.parse import urlparse

# Make pipeline/ importable regardless of where the worker is invoked from
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load .env file from project root if present — lets both the API server and
# the Celery worker pick up GEMINI_API_KEY without needing shell exports.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass  # python-dotenv not installed — rely on environment variables only
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from celery import Celery
from celery.utils.log import get_task_logger

# Module-level import — avoids google namespace package collision when
# google-auth is also installed.  Must use `import google.genai` (submodule
# path) rather than `from google import genai` for the same reason.
try:
    import google.genai as genai
except ImportError:
    genai = None  # type: ignore[assignment]

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "video_intelligence",
    broker=_redis_url,
    backend=_redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=86400,           # keep results in Redis for 24 h
    worker_prefetch_multiplier=1,   # one task at a time per worker (pipeline is heavy)
    task_acks_late=True,            # ack only after task completes (safe crash recovery)
    task_time_limit=3600,           # hard-kill worker after 1 h (hung FFmpeg/Gemini guard)
    task_soft_time_limit=3300,      # SIGTERM 5 min before hard kill for graceful cleanup
)

logger = get_task_logger(__name__)

# Maximum bytes to download from a user-supplied URL (500 MB)
_MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024

# Private, loopback, link-local, and cloud-metadata IP ranges (SSRF guard)
# Mirrored from api/main.py — worker validates independently (defence-in-depth).
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

# Absolute path to YOLO weights — set once at module import time so it
# does not require per-task global mutation (which would be thread-unsafe).
_YOLO_WEIGHTS = os.path.join(_project_root, "yolov8n.pt")


# ---------------------------------------------------------------------------
# Worker-side SSRF guard (independent of API layer validation)
# ---------------------------------------------------------------------------

def _check_url_safety(url: str) -> None:
    """
    Raise ValueError if url is unsafe to fetch (SSRF guard).

    This is called inside execute_pipeline before any network request.
    The API layer performs the same check before enqueueing; this is an
    independent defence-in-depth layer in case the task message is
    injected directly into Redis or the API validation is bypassed.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    if parsed.scheme != "https":
        raise ValueError("Only https:// URLs are accepted")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a hostname")

    # Reject explicit private-range IP literals
    try:
        literal = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
            if literal in net:
                raise ValueError("URL points to a private or reserved IP address")
    except ValueError as exc:
        if "private" in str(exc) or "reserved" in str(exc):
            raise
        # Not a bare IP address — proceed to DNS resolution

    try:
        ip_str = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(ip_str)
    except (socket.gaierror, ValueError) as exc:
        raise ValueError(f"URL hostname cannot be resolved: {exc}") from exc

    for net in _BLOCKED_NETWORKS:
        if addr in net:
            raise ValueError("URL resolves to a private or reserved IP address")

    if parsed.port is not None and parsed.port != 443:
        raise ValueError("Custom ports are not allowed in video URLs")


# ---------------------------------------------------------------------------
# Hash-index helper — persists sha256 → video_id after successful pipeline runs
# ---------------------------------------------------------------------------

def _update_hash_index(output_base: str, sha256: str, video_id: str) -> None:
    """Atomically update hash_index.json with a new sha256 → video_id mapping."""
    path = os.path.join(output_base, "hash_index.json")
    index: dict = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                index = json.load(f)
        except Exception:
            pass
    index[sha256] = video_id
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(index, f, indent=2)
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning("Could not update hash_index.json: %s", exc)


# ---------------------------------------------------------------------------
# Push notification helper
# ---------------------------------------------------------------------------

def _send_completion_push(video_id: str, success: bool) -> None:
    """
    Send an FCM push notification to the job owner when a pipeline finishes.
    Completely best-effort — any exception is swallowed so it never affects the task.
    """
    try:
        output_base = os.environ.get("OUTPUT_DIR") or os.path.join(_project_root, "output")
        meta_path = os.path.join(output_base, video_id, "meta.json")
        if not os.path.exists(meta_path):
            return

        with open(meta_path) as f:
            user_id = json.load(f).get("user_id")
        if not user_id:
            return

        from api.database import SessionLocal
        from api.schema import FcmToken as _FcmToken
        db = SessionLocal()
        try:
            tokens = [row.token for row in db.query(_FcmToken).filter_by(user_id=user_id).all()]
        finally:
            db.close()

        if not tokens:
            return

        from api.notifications import send_push
        if success:
            send_push(
                tokens,
                title="Analysis complete ✓",
                body="Your video has been analysed. Tap to chat with it.",
                data={"video_id": video_id},
                link=f"/jobs/{video_id}",
            )
        else:
            send_push(
                tokens,
                title="Analysis failed",
                body="Something went wrong processing your video. Tap to retry.",
                data={"video_id": video_id},
                link=f"/jobs/{video_id}",
            )
    except Exception as exc:
        logger.warning("Push notification error for %s: %s", video_id, exc)


# ---------------------------------------------------------------------------
# DB progress helper — writes job status to Postgres so PowerSync can sync it
# ---------------------------------------------------------------------------

def _update_job_in_db(
    video_id: str,
    status: str,
    progress: int,
    stage: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    """Update job row for real-time PowerSync sync. Best-effort — never raises."""
    try:
        from datetime import datetime, timezone as _tz
        from api.database import SessionLocal
        from api.schema import Job as _Job

        db = SessionLocal()
        try:
            job = db.query(_Job).filter_by(id=video_id).first()
            if job is None:
                return
            job.status = status
            job.progress_percent = progress
            if stage is not None:
                job.current_stage = stage
            if summary is not None:
                job.summary = summary
            now = datetime.now(tz=_tz.utc)
            if status == "processing" and job.started_at is None:
                job.started_at = now
            elif status == "complete" and job.completed_at is None:
                job.completed_at = now
            elif status == "failed" and job.failed_at is None:
                job.failed_at = now
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug("DB job update skipped for %s: %s", video_id, exc)


# ---------------------------------------------------------------------------
# Timeline entries — write per-keyframe rows for Mastra cross-video search
# ---------------------------------------------------------------------------

def _parse_ts(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        try:
            s = str(v)
            if ':' in s:
                p = s.split(':')
                return float(p[0]) * 60 + float(p[1])
        except Exception:
            pass
        return 0.0


def _write_timeline_entries(video_id: str, result: dict) -> None:
    """
    Upsert per-keyframe timeline_entries rows after pipeline completes.

    Each row is: id = "{video_id}_{index:06d}", denormalized with user_id
    so PowerSync can filter with auth.user_id().  Best-effort — never raises.
    """
    try:
        from api.database import SessionLocal
        from api.schema import TimelineEntry as _TE, Job as _Job

        db = SessionLocal()
        try:
            job = db.query(_Job).filter_by(id=video_id).first()
            if job is None:
                return
            user_id = job.user_id

            timeline = result.get("timeline", []) if isinstance(result, dict) else []
            for idx, kf in enumerate(timeline):
                entry_id = f"{video_id}_{idx:06d}"
                existing = db.query(_TE).filter_by(id=entry_id).first()
                objs = kf.get("detected_objects") or []
                objs_str = json.dumps(objs) if isinstance(objs, list) else str(objs)
                if existing is None:
                    db.add(_TE(
                        id=entry_id,
                        job_id=video_id,
                        user_id=user_id,
                        keyframe_index=idx,
                        timestamp_start=_parse_ts(kf.get("timestamp_start")),
                        timestamp_end=_parse_ts(kf.get("timestamp_end")),
                        description=kf.get("description"),
                        detected_objects=objs_str,
                        camera_movement=kf.get("camera_movement"),
                        confidence=float(kf.get("confidence")) if kf.get("confidence") is not None else None,
                    ))
                else:
                    existing.description = kf.get("description")
                    existing.detected_objects = objs_str
                    existing.camera_movement = kf.get("camera_movement")
            db.commit()
            logger.info("[%s] Wrote %d timeline entries", video_id, len(timeline))
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Timeline entries write skipped for %s: %s", video_id, exc)


# ---------------------------------------------------------------------------
# Core pipeline execution
# ---------------------------------------------------------------------------

def execute_pipeline(
    video_id: str,
    input_source: str,
    fps: int = 5,
    progress_cb=None,
    input_sha256: Optional[str] = None,
) -> dict:
    """
    Run the full pipeline for one video.

    Args:
        video_id:     Unique job identifier — used as the output subdirectory name.
        input_source: Local file path OR https:// URL.
        fps:          Target preprocessing frame rate (default 5).
        progress_cb:  Optional callable(stage: str, pct: int) for progress updates.

    Returns:
        {"video_id": ..., "status": "complete"}

    Side-effects:
        Writes <OUTPUT_DIR>/<video_id>/result.json on success (atomic rename).
    """
    # Re-insert project root into sys.path here — not just at module level —
    # because Celery prefork child processes can lose module-level sys.path
    # modifications made in the parent process before forking.
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    import cv2
    import httpx
    from ultralytics import YOLO as _YOLO

    from pipeline.preprocessor import preprocess
    from pipeline.keyframe_extractor import extract_keyframes
    from pipeline.yolo_analyzer import analyze_keyframes
    from pipeline.audio_analyzer import analyze_audio
    from pipeline.vision_model import describe_keyframes
    from pipeline.stitcher import stitch

    # ------------------------------------------------------------------
    # Input validation — worker must not blindly trust task arguments
    # ------------------------------------------------------------------
    if genai is None:
        raise ValueError("google-genai is not installed — cannot run pipeline")
    if not (1 <= fps <= 30):
        raise ValueError(f"Invalid fps value: {fps}. Must be 1–30.")

    output_base = os.environ.get("OUTPUT_DIR") or os.path.join(_project_root, "output")
    output_dir = os.path.join(output_base, video_id)
    os.makedirs(output_dir, exist_ok=True)

    _status_path = os.path.join(output_dir, "status.json")

    def _progress(stage: str, pct: int):
        _status = "complete" if stage == "complete" else "processing"
        # Write status.json (Redis-independent fallback for get_status)
        try:
            with open(_status_path, "w") as _sf:
                json.dump({"status": _status, "stage": stage, "progress_percent": pct}, _sf)
        except Exception:
            pass
        # Update DB row so PowerSync syncs progress to all connected clients
        _update_job_in_db(video_id, _status, pct, stage=stage if _status != "complete" else None)
        if progress_cb:
            progress_cb(stage, pct)

    # ------------------------------------------------------------------
    # Optional: download input if URL
    # ------------------------------------------------------------------
    input_path = input_source
    if input_source.startswith(("http://", "https://")):
        _progress("downloading", 2)

        # Re-validate URL inside the worker (defence-in-depth against direct
        # Redis task injection that bypasses the API layer).
        _check_url_safety(input_source)

        ext = os.path.splitext(urlparse(input_source).path)[-1].lower() or ".mp4"
        allowed = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        if ext not in allowed:
            ext = ".mp4"
        input_path = os.path.join(output_dir, f"input_video{ext}")

        logger.info("Downloading %s → %s", input_source, input_path)
        written = 0
        with httpx.stream("GET", input_source, follow_redirects=False, timeout=60) as r:
            r.raise_for_status()
            with open(input_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65_536):
                    written += len(chunk)
                    if written > _MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"Download exceeded {_MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB limit"
                        )
                    f.write(chunk)

    # ------------------------------------------------------------------
    # Stage 1: FFmpeg preprocessing
    # ------------------------------------------------------------------
    _progress("preprocessing", 10)
    logger.info("[%s] Stage 1 — preprocessing @ %dfps", video_id, fps)
    pr = preprocess(input_path, output_dir=output_dir, target_fps=fps)

    # ------------------------------------------------------------------
    # Stage 2+3: Scene detection + keyframe extraction
    # ------------------------------------------------------------------
    _progress("extracting_keyframes", 25)
    logger.info("[%s] Stage 2+3 — keyframe extraction", video_id)
    keyframes = extract_keyframes(pr.processed_video_path)

    cap = cv2.VideoCapture(pr.processed_video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    logger.info("[%s] %d keyframes from %d total frames", video_id, len(keyframes), total_frames)

    # ------------------------------------------------------------------
    # Stage 4: YOLO object detection
    # Use absolute _YOLO_WEIGHTS path — avoids CWD dependency and
    # the thread-unsafe module-global mutation pattern.
    # ------------------------------------------------------------------
    _progress("yolo_analysis", 40)
    logger.info("[%s] Stage 4 — YOLO analysis", video_id)
    yolo_model = _YOLO(_YOLO_WEIGHTS)
    scored = analyze_keyframes(keyframes, model=yolo_model)

    # ------------------------------------------------------------------
    # Gemini client — shared across audio, vision, and stitcher
    # ------------------------------------------------------------------
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------
    # Stage 4.5: Audio analysis
    # ------------------------------------------------------------------
    _progress("audio_analysis", 50)
    logger.info("[%s] Stage 4.5 — audio analysis", video_id)
    audio_segments = analyze_audio(
        pr.audio_path,
        duration=pr.metadata.duration_seconds,
        client=client,
    )
    logger.info("[%s] %d audio segments", video_id, len(audio_segments))

    # ------------------------------------------------------------------
    # Stage 5: Vision model — per-keyframe description
    # Emit incremental progress from 55 → 85 as batches complete.
    # ------------------------------------------------------------------
    _progress("vision_analysis", 55)
    logger.info("[%s] Stage 5 — vision model (%d frames)", video_id, len(scored))
    total_batches = max(1, math.ceil(len(scored) / 25))

    def _on_batch(batch_num: int, _total: int):
        pct = 55 + int((batch_num / total_batches) * 30)   # 55 → 85
        _progress("vision_analysis", pct)

    described = describe_keyframes(
        scored,
        client=client,
        audio_segments=audio_segments or None,
        on_batch_complete=_on_batch,
    )

    # ------------------------------------------------------------------
    # Stage 6+7: Stitch + LLM summary
    # ------------------------------------------------------------------
    _progress("stitching", 90)
    logger.info("[%s] Stage 6+7 — stitching", video_id)
    result = stitch(
        described=described,
        preprocess_result=pr,
        total_frames=total_frames,
        processing_time_s=0.0,
        video_id=video_id,
        summary_model=client,
        audio_segments=audio_segments or None,
    )

    # ------------------------------------------------------------------
    # Persist result — atomic rename so readers never see a partial file
    # (LOW-5: eliminates the TOCTOU race between writing and reading)
    # ------------------------------------------------------------------
    result_path = os.path.join(output_dir, "result.json")
    tmp_path = result_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(result, f, indent=2)
    os.replace(tmp_path, result_path)   # atomic on POSIX; near-atomic on Windows
    logger.info("[%s] Result written to %s", video_id, result_path)

    # Register in hash index so duplicate submissions return this result
    if input_sha256:
        _update_hash_index(output_base, input_sha256, video_id)

    # status.json is now superseded by result.json — remove it
    try:
        os.unlink(_status_path)
    except OSError:
        pass

    # Write per-keyframe timeline entries to DB → PowerSync syncs to all clients
    _write_timeline_entries(video_id, result)

    # Update DB to "complete" with summary for PowerSync sync
    _summary = result.get("summary") if isinstance(result, dict) else None
    _update_job_in_db(video_id, "complete", 100, stage=None, summary=_summary)

    # Push notification (best-effort — never fail the task over this)
    _send_completion_push(video_id, success=True)

    _progress("complete", 100)
    return {"video_id": video_id, "status": "complete"}


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="workers.pipeline_worker.run_pipeline")
def run_pipeline(self, video_id: str, input_source: str, fps: int = 5, input_sha256: Optional[str] = None):
    """Celery task — wraps execute_pipeline with Celery progress state updates."""
    def progress_cb(stage: str, pct: int):
        self.update_state(
            state="PROGRESS",
            meta={"stage": stage, "pct": pct},
        )

    try:
        return execute_pipeline(video_id, input_source, fps=fps, progress_cb=progress_cb, input_sha256=input_sha256)
    except Exception as exc:
        logger.error("[%s] Pipeline failed: %s", video_id, exc, exc_info=True)
        # Write failed status to status.json so get_status can report it without Redis
        output_base = os.environ.get("OUTPUT_DIR") or os.path.join(_project_root, "output")
        status_path = os.path.join(output_base, video_id, "status.json")
        try:
            with open(status_path, "w") as f:
                json.dump({"status": "failed", "error": str(exc)}, f)
        except Exception:
            pass
        _update_job_in_db(video_id, "failed", 0)
        _send_completion_push(video_id, success=False)
        raise
