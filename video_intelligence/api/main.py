"""
Video Intelligence API — FastAPI application.

Endpoints:
  POST   /v1/analyze           Queue a video for async processing
  POST   /v1/analyze/sync      Synchronous pipeline for short videos (≤ MAX_SYNC_DURATION)
  GET    /v1/status/{video_id} Poll job status
  GET    /v1/result/{video_id} Fetch full output JSON
  DELETE /v1/result/{video_id} Delete result and job files

Start the API:
  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Start a Celery worker (separate terminal, from video_intelligence/ dir):
  celery -A workers.pipeline_worker worker --loglevel=info

Security measures implemented:
  - video_id validated against strict regex (vid_ + 32 hex chars) on every route
  - os.path.realpath containment check prevents path traversal (belt-and-suspenders)
  - SSRF guard: only https://, private IP blocklist, follow_redirects=False
  - Upload and download bytes capped at MAX_UPLOAD_BYTES before writing to disk
  - URL validated in API layer before being handed to the Celery worker
  - All 500 errors return opaque error references; full details logged server-side
  - Full 128-bit UUID video_ids prevent enumeration and collision
  - Generic 404/403 messages — never reflect user-supplied input verbatim
  - Bearer token auth on all endpoints (vi_live_... keys stored in SQLite)
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import socket
import threading
import uuid
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.auth import APIKey, require_api_key, require_auth
from api.schema import User
from api.auth_routes import router as auth_router
from api.config import settings
from api.database import init_db, SessionLocal
from api.models import AnalyzeResponse, StatusResponse
from workers.pipeline_worker import celery_app, execute_pipeline

# Work around google namespace package collision between google-auth and google-genai:
# using `import google.genai` (submodule path) instead of `from google import genai`
# lets Python's import machinery find the submodule even when google-auth has already
# populated sys.modules['google'] without a genai attribute.
try:
    import google.genai as genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = None       # type: ignore[assignment]
    genai_types = None # type: ignore[assignment]

# Create all DB tables on startup (idempotent — safe on every restart).
init_db()

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

# video_id format: "vid_" followed by exactly 32 lowercase hex chars (128-bit UUID4)
_VIDEO_ID_RE = re.compile(r"^vid_[0-9a-f]{32}$")

# Private, loopback, link-local, and cloud-metadata IP ranges (SSRF guard)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local + AWS/GCP/Azure metadata
    ipaddress.ip_network("100.64.0.0/10"),     # carrier-grade NAT
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),          # ULA IPv6
    ipaddress.ip_network("fe80::/10"),         # link-local IPv6
]

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(
    title="Video Intelligence API",
    version="1.0.0",
    description="Turns videos into structured timestamped JSON descriptions.",
)

app.include_router(auth_router)


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _validate_video_id(video_id: str) -> None:
    """
    Raise HTTP 400 if video_id does not match the expected format.

    Accepts only 'vid_' + 32 lowercase hex characters. This eliminates all
    path-traversal characters (slashes, dots, spaces) before any os.path call.
    """
    if not _VIDEO_ID_RE.fullmatch(video_id):
        raise HTTPException(400, "Invalid video_id")


def _job_dir(video_id: str) -> str:
    """
    Construct the job directory path with a path-containment assertion.

    The regex in _validate_video_id already prevents traversal, but this
    os.path.realpath check is an additional defense-in-depth guard against
    symlink attacks or unexpected filesystem behaviour.
    """
    base = os.path.realpath(settings.output_dir)
    candidate = os.path.realpath(os.path.join(settings.output_dir, video_id))
    # Ensure candidate is a strict child of base (not base itself, not a sibling)
    if not candidate.startswith(base + os.sep):
        raise HTTPException(400, "Invalid video_id")
    return candidate


def _result_path(job_dir: str) -> str:
    return os.path.join(job_dir, "result.json")


def _meta_path(job_dir: str) -> str:
    return os.path.join(job_dir, "meta.json")


def _write_meta(job_dir: str, user_id: str) -> None:
    with open(_meta_path(job_dir), "w") as f:
        json.dump({"user_id": user_id}, f)


def _read_meta_user_id(job_dir: str) -> Optional[str]:
    try:
        with open(_meta_path(job_dir)) as f:
            return json.load(f).get("user_id")
    except Exception:
        return None


def _upsert_job_record(
    video_id: str,
    user_id: str,
    status: str,
    input_type: Optional[str] = None,
    input_filename: Optional[str] = None,
    input_url: Optional[str] = None,
    fps_used: Optional[int] = None,
    progress_percent: int = 0,
    current_stage: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    """
    Create or update a Job row so PowerSync can sync real-time status
    to all connected clients.  Best-effort — never blocks the response.
    """
    from datetime import datetime, timezone as _tz
    from api.schema import Job as _Job
    try:
        db = SessionLocal()
        try:
            job = db.query(_Job).filter_by(id=video_id).first()
            now = datetime.now(tz=_tz.utc)
            if job is None:
                job = _Job(
                    id=video_id,
                    user_id=user_id,
                    status=status,
                    input_type=input_type,
                    input_filename=input_filename,
                    input_url=input_url,
                    fps_used=fps_used,
                    progress_percent=progress_percent,
                    current_stage=current_stage,
                    summary=summary,
                    queued_at=now if status == "queued" else None,
                    started_at=now if status == "processing" else None,
                    completed_at=now if status == "complete" else None,
                    failed_at=now if status == "failed" else None,
                )
                db.add(job)
            else:
                job.status = status
                job.progress_percent = progress_percent
                if current_stage is not None:
                    job.current_stage = current_stage
                if summary is not None:
                    job.summary = summary
                if status == "processing" and job.started_at is None:
                    job.started_at = now
                elif status == "complete":
                    job.completed_at = now
                elif status == "failed":
                    job.failed_at = now
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Could not upsert job record %s: %s", video_id, exc)


def _assert_owner(job_dir: str, user_id: str) -> None:
    """Raise 404 if the job doesn't exist or belongs to a different user."""
    if not os.path.isdir(job_dir):
        raise HTTPException(404, "Job not found")
    owner = _read_meta_user_id(job_dir)
    # Jobs created before ownership tracking have no meta.json — allow access
    # only if there is no owner recorded (legacy). Once all jobs have meta.json
    # this fallback can be removed.
    if owner is not None and owner != user_id:
        raise HTTPException(404, "Job not found")


def _new_video_id() -> str:
    """Generate a 128-bit random video ID (non-guessable, collision-resistant)."""
    return f"vid_{uuid.uuid4().hex}"   # 32 hex chars — 128 bits of entropy


def _hash_file(path: str) -> str:
    """Return SHA-256 hex digest of a file without loading it fully into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_duplicate_by_hash(sha256: str) -> Optional[str]:
    """Return video_id if this SHA-256 hash was already successfully processed, else None."""
    path = os.path.join(os.path.realpath(settings.output_dir), "hash_index.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            index = json.load(f)
        vid_id = index.get(sha256)
        if vid_id and _VIDEO_ID_RE.fullmatch(vid_id):
            return vid_id
    except Exception:
        pass
    return None


def check_url_safety(url: str) -> None:
    """
    Guard against SSRF attacks.

    Enforces:
      - https:// scheme only (blocks plain-HTTP metadata endpoints, MITM)
      - No explicit IP literals in the private/reserved ranges
      - Hostname resolves to a public IP (blocks internal DNS names)
      - No custom ports (standard video hosts use 443)

    IMPORTANT: DNS-rebinding attacks (hostname resolves to public IP now but
    private IP at request time) cannot be fully mitigated by a single DNS check.
    A production deployment should use a dedicated egress proxy with its own DNS
    resolver that enforces these rules at the network layer.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(400, "Malformed URL")

    if parsed.scheme != "https":
        raise HTTPException(400, "Only https:// URLs are accepted")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(400, "URL must include a hostname")

    # Reject explicit private-range IP literals in the URL
    try:
        literal = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
            if literal in net:
                raise HTTPException(400, "URL points to a private or reserved IP address")
    except ValueError:
        pass  # not a bare IP address — proceed to DNS resolution

    # Resolve hostname and reject if it maps to a private/reserved range
    try:
        ip_str = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(ip_str)
    except (socket.gaierror, ValueError):
        raise HTTPException(400, "URL hostname cannot be resolved")

    for net in _BLOCKED_NETWORKS:
        if addr in net:
            raise HTTPException(400, "URL resolves to a private or reserved IP address")

    # Reject explicit non-standard ports (standard HTTPS uses 443 / default)
    if parsed.port is not None and parsed.port != 443:
        raise HTTPException(400, "Custom ports are not allowed in video URLs")


# ---------------------------------------------------------------------------
# Upload / download helpers
# ---------------------------------------------------------------------------

def _validate_extension(filename: Optional[str]) -> str:
    ext = os.path.splitext(filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported format. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


def _save_upload(upload: UploadFile, dest_dir: str) -> str:
    """
    Save an UploadFile to dest_dir, enforcing MAX_UPLOAD_BYTES before any
    data is written beyond the limit. Returns the saved file path.
    """
    ext = _validate_extension(upload.filename)
    dest = os.path.join(dest_dir, f"input_video{ext}")
    max_bytes = settings.max_upload_bytes
    written = 0
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = upload.file.read(65_536)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        413,
                        f"Upload exceeds the {max_bytes // (1024 * 1024)} MB size limit",
                    )
                f.write(chunk)
    except HTTPException:
        # Clean up partial file before re-raising
        if os.path.exists(dest):
            os.unlink(dest)
        raise
    return dest


def _download_url(url: str, dest_dir: str) -> str:
    """
    Download a URL to dest_dir, enforcing MAX_UPLOAD_BYTES.

    Caller is responsible for calling check_url_safety(url) first.
    follow_redirects=False: prevents redirect-based SSRF bypass.
    """
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[-1].lower() or ".mp4"
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".mp4"
    dest = os.path.join(dest_dir, f"input_video{ext}")
    max_bytes = settings.max_upload_bytes
    written = 0
    try:
        with httpx.stream("GET", url, follow_redirects=False, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65_536):
                    written += len(chunk)
                    if written > max_bytes:
                        raise HTTPException(
                            413,
                            f"Download exceeds the {max_bytes // (1024 * 1024)} MB size limit",
                        )
                    f.write(chunk)
    except HTTPException:
        if os.path.exists(dest):
            os.unlink(dest)
        raise
    return dest


# ---------------------------------------------------------------------------
# Celery status helper
# ---------------------------------------------------------------------------

def _celery_status(video_id: str) -> StatusResponse:
    """
    Map a Celery AsyncResult to a StatusResponse.
    Failed task errors are logged server-side; callers receive only a generic message.
    """
    task = celery_app.AsyncResult(video_id)
    state = task.state

    if state == "PENDING":
        return StatusResponse(video_id=video_id, status="queued", progress_percent=0)
    if state == "STARTED":
        return StatusResponse(video_id=video_id, status="processing", progress_percent=5)
    if state == "PROGRESS":
        meta = task.info or {}
        return StatusResponse(
            video_id=video_id,
            status="processing",
            progress_percent=meta.get("pct", 0),
            current_stage=meta.get("stage"),
        )
    if state == "SUCCESS":
        return StatusResponse(video_id=video_id, status="complete", progress_percent=100)
    if state == "FAILURE":
        # Log full exception server-side; never expose it to the caller.
        logger.error("Task %s failed: %s", video_id, task.result, exc_info=False)
        return StatusResponse(
            video_id=video_id,
            status="failed",
            error="Processing failed. Contact support with your video_id.",
        )
    return StatusResponse(video_id=video_id, status="processing", progress_percent=0)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/v1/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze_async(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    fps: int = Form(settings.default_fps),
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    Queue a video for async processing. Returns video_id immediately.

    Accepts either a file upload (multipart/form-data) or a URL (form field).
    Poll /v1/status/{video_id} for progress.
    """
    if not file and not url:
        raise HTTPException(400, "Provide either 'file' or 'url'")
    if file and url:
        raise HTTPException(400, "Provide either 'file' or 'url', not both")
    if fps < 1 or fps > 30:
        raise HTTPException(400, "fps must be between 1 and 30")

    user, _ = _auth
    video_id = _new_video_id()
    jdir = _job_dir(video_id)
    os.makedirs(jdir, exist_ok=True)
    _write_meta(jdir, user.id)

    try:
        if file:
            input_source = _save_upload(file, jdir)
        else:
            # Validate URL eagerly so callers get immediate feedback.
            # The worker performs the same check again before fetching (defence-in-depth).
            check_url_safety(url)
            input_source = url  # worker downloads; see workers/pipeline_worker.py
    except HTTPException:
        shutil.rmtree(jdir, ignore_errors=True)
        raise

    # ── Write job to DB (powers PowerSync real-time sync) ─────────────────
    _upsert_job_record(
        video_id=video_id,
        user_id=user.id,
        status="queued",
        input_type="file" if file else "url",
        input_filename=getattr(file, "filename", None),
        input_url=url if not file else None,
        fps_used=fps,
    )

    # ── Duplicate detection ────────────────────────────────────────────────
    sha256: Optional[str] = None
    try:
        if file:
            sha256 = _hash_file(input_source)
        else:
            sha256 = hashlib.sha256((url or "").encode()).hexdigest()
        if sha256:
            existing = _find_duplicate_by_hash(sha256)
            if existing and existing != video_id:
                existing_dir = _job_dir(existing)
                # Only reuse if the existing result belongs to the same user
                existing_owner = _read_meta_user_id(existing_dir)
                if (existing_owner is None or existing_owner == user.id) and os.path.exists(_result_path(existing_dir)):
                    shutil.rmtree(jdir, ignore_errors=True)
                    return AnalyzeResponse(video_id=existing, status="complete", eta_seconds=0)
    except Exception:
        pass  # dedup is best-effort — never block a legitimate job

    # ── Queue via Celery; fall back to background thread if Redis is down ──
    try:
        from workers.pipeline_worker import run_pipeline
        run_pipeline.apply_async(
            kwargs={"video_id": video_id, "input_source": input_source, "fps": fps, "input_sha256": sha256},
            task_id=video_id,
        )
        logger.info("Celery task dispatched for %s", video_id)
    except Exception as _celery_exc:
        logger.warning("Celery unavailable for %s: %s — falling back to background thread", video_id, _celery_exc)
        _sha = sha256  # capture for closure

        def _run_in_thread() -> None:
            try:
                execute_pipeline(video_id, input_source, fps=fps, input_sha256=_sha)
            except Exception as exc:
                logger.error("[%s] Background thread pipeline failed: %s", video_id, exc, exc_info=True)

        threading.Thread(target=_run_in_thread, daemon=True, name=f"pipeline-{video_id}").start()

    return AnalyzeResponse(video_id=video_id, status="queued", eta_seconds=120)


@app.post("/v1/analyze/sync", status_code=200)
async def analyze_sync(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    fps: int = Form(settings.default_fps),
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    Synchronous pipeline — runs inline and returns full result JSON.

    Only for short videos (≤ MAX_SYNC_DURATION_SECONDS). Use /v1/analyze for
    longer videos.
    """
    if not file and not url:
        raise HTTPException(400, "Provide either 'file' or 'url'")
    if file and url:
        raise HTTPException(400, "Provide either 'file' or 'url', not both")
    if fps < 1 or fps > 30:
        raise HTTPException(400, "fps must be between 1 and 30")

    from pipeline.preprocessor import probe_video

    user, _ = _auth
    video_id = _new_video_id()
    jdir = _job_dir(video_id)
    os.makedirs(jdir, exist_ok=True)
    _write_meta(jdir, user.id)

    try:
        if file:
            input_path = _save_upload(file, jdir)
        else:
            check_url_safety(url)
            try:
                input_path = _download_url(url, jdir)
            except httpx.HTTPStatusError:
                raise HTTPException(400, "Failed to download the provided URL")
    except HTTPException:
        shutil.rmtree(jdir, ignore_errors=True)
        raise

    # ── Duplicate detection ────────────────────────────────────────────────
    sha256: Optional[str] = None
    try:
        if file:
            sha256 = _hash_file(input_path)
        else:
            sha256 = hashlib.sha256((url or "").encode()).hexdigest()
        if sha256:
            existing = _find_duplicate_by_hash(sha256)
            if existing and existing != video_id:
                existing_dir = _job_dir(existing)
                rp = _result_path(existing_dir)
                if os.path.exists(rp):
                    shutil.rmtree(jdir, ignore_errors=True)
                    with open(rp) as f:
                        return JSONResponse(content=json.load(f))
    except Exception:
        pass  # dedup is best-effort

    meta = probe_video(input_path)
    if meta.duration_seconds > settings.max_sync_duration_seconds:
        shutil.rmtree(jdir, ignore_errors=True)
        raise HTTPException(
            413,
            f"Video is {meta.duration_seconds:.0f}s — exceeds the sync limit of "
            f"{settings.max_sync_duration_seconds}s. Use POST /v1/analyze instead.",
        )

    # Generate an opaque error reference so support can correlate logs ↔ API errors
    ref = secrets.token_hex(4)
    try:
        execute_pipeline(video_id, input_path, fps=fps, input_sha256=sha256)
    except Exception as exc:
        logger.error(
            "Sync pipeline error [ref=%s] video_id=%s: %s",
            ref, video_id, exc, exc_info=True,
        )
        shutil.rmtree(jdir, ignore_errors=True)
        raise HTTPException(500, f"Processing failed (ref: {ref})")

    with open(_result_path(jdir)) as f:
        return JSONResponse(content=json.load(f))


@app.get("/v1/status/{video_id}", response_model=StatusResponse)
async def get_status(
    video_id: str,
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Poll the processing status of a queued video."""
    _validate_video_id(video_id)
    user, _ = _auth
    jdir = _job_dir(video_id)

    # Try filesystem first (active jobs on this machine)
    if os.path.isdir(jdir):
        owner = _read_meta_user_id(jdir)
        if owner is None or owner == user.id:
            if os.path.exists(_result_path(jdir)):
                return StatusResponse(video_id=video_id, status="complete", progress_percent=100)
            status_path = os.path.join(jdir, "status.json")
            if os.path.exists(status_path):
                try:
                    with open(status_path) as _sf:
                        _s = json.load(_sf)
                    return StatusResponse(
                        video_id=video_id,
                        status=_s.get("status", "processing"),
                        progress_percent=_s.get("progress_percent", 0),
                        current_stage=_s.get("stage"),
                        error=_s.get("error"),
                    )
                except Exception:
                    pass
            try:
                return _celery_status(video_id)
            except Exception:
                pass

    # Fall back to database (jobs from other deployments synced via Supabase)
    from api.schema import Job as _Job
    row = db.query(_Job).filter(_Job.id == video_id, _Job.user_id == user.id).first()
    if row:
        return StatusResponse(
            video_id=video_id,
            status=row.status or "queued",
            progress_percent=row.progress_percent or 0,
            current_stage=row.current_stage,
        )

    raise HTTPException(404, "Job not found")


@app.get("/v1/result/{video_id}")
async def get_result(
    video_id: str,
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Fetch the full output JSON for a completed video."""
    _validate_video_id(video_id)
    user, _ = _auth
    jdir = _job_dir(video_id)

    # Try filesystem first (active jobs on this machine)
    rp = _result_path(jdir)
    if os.path.exists(rp):
        owner = _read_meta_user_id(jdir)
        if owner is None or owner == user.id:
            with open(rp) as f:
                return JSONResponse(content=json.load(f))

    # Fall back to database — reconstruct result from Job + TimelineEntry rows
    from api.schema import Job as _Job, TimelineEntry as _TE
    row = db.query(_Job).filter(_Job.id == video_id, _Job.user_id == user.id).first()
    if not row:
        raise HTTPException(404, "Job not found")

    if row.status == "failed":
        raise HTTPException(500, "Processing failed.")
    if row.status != "complete":
        raise HTTPException(202, "Processing not yet complete")

    # Build timeline from timeline_entries table
    entries = (
        db.query(_TE)
        .filter(_TE.job_id == video_id)
        .order_by(_TE.keyframe_index)
        .all()
    )

    def _fmt_ts(seconds: float) -> str:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}:{s:05.2f}"

    timeline = []
    for e in entries:
        objs = []
        if e.detected_objects:
            try:
                objs = json.loads(e.detected_objects)
            except Exception:
                objs = [o.strip() for o in e.detected_objects.split(",") if o.strip()]
        timeline.append({
            "keyframe_id":     e.keyframe_index,
            "timestamp_start": _fmt_ts(e.timestamp_start),
            "timestamp_end":   _fmt_ts(e.timestamp_end),
            "description":     e.description or "",
            "camera_movement": e.camera_movement or "unknown",
            "detected_objects": objs,
            "scene_change":    False,
            "confidence":      e.confidence or 0.0,
        })

    dur = float(row.duration_seconds) if row.duration_seconds else 0
    return JSONResponse(content={
        "video_id": video_id,
        "status": "complete",
        "metadata": {
            "duration_seconds":       dur,
            "original_fps":           25.0,
            "processed_fps":          5,
            "original_resolution":    "unknown",
            "processed_resolution":   "unknown",
            "total_frames_extracted": len(timeline),
            "keyframes_analyzed":     len(timeline),
            "duplicates_removed":     0,
            "processing_time_seconds": 0,
        },
        "summary": row.summary or "Summary unavailable.",
        "timeline": timeline,
        "audio_segments": [],
    })


@app.delete("/v1/result/{video_id}", status_code=204)
async def delete_result(
    video_id: str,
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Delete a job's result and all associated files."""
    _validate_video_id(video_id)
    user, _ = _auth
    jdir = _job_dir(video_id)

    # Delete from filesystem if present
    if os.path.isdir(jdir):
        owner = _read_meta_user_id(jdir)
        if owner is not None and owner != user.id:
            raise HTTPException(404, "Job not found")
        shutil.rmtree(jdir, ignore_errors=True)

    # Delete from database
    from api.schema import Job as _Job, TimelineEntry as _TE, ChatMessage as _CM
    row = db.query(_Job).filter(_Job.id == video_id, _Job.user_id == user.id).first()
    if not row and not os.path.isdir(jdir):
        raise HTTPException(404, "Job not found")
    if row:
        db.query(_TE).filter(_TE.job_id == video_id).delete()
        db.query(_CM).filter(_CM.video_id == video_id).delete()
        db.delete(row)
        db.commit()

    # Best-effort task revocation
    try:
        celery_app.control.revoke(video_id, terminate=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Key self-service routes
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel

class _CreateKeyRequest(_BaseModel):
    name: str
    plan: str = "free"


@app.post("/v1/keys", status_code=201)
async def create_key_endpoint(body: _CreateKeyRequest):
    """
    Create a free-trial API key (no auth required).

    Creates a minimal anonymous user account alongside the key.  The account
    can be upgraded later (email + password) via POST /v1/auth/claim.
    Rate-limiting should be added before production.
    """
    from api.auth import create_anonymous_user_with_key as _create_anon
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    if body.plan not in ("free", "starter", "pro", "enterprise"):
        raise HTTPException(400, "plan must be one of: free, starter, pro, enterprise")
    try:
        user, api_key, raw_key = _create_anon(body.name.strip(), body.plan)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"key": raw_key, "name": api_key.label, "plan": user.plan}


@app.get("/v1/keys/me")
async def get_key_me(
    current_auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """Return the authenticated user's primary key info.

    Accepts both API key and JWT Bearer tokens so the web dashboard can call
    this endpoint after logging in with email/password or Google OAuth.
    """
    user, api_key = current_auth
    # JWT auth — look up the user's first active key.
    if api_key is None:
        from api.auth import list_keys as _list_keys
        keys = _list_keys(user.id)
        if not keys:
            raise HTTPException(404, "No API key found for this account")
        api_key = keys[0]
    return {
        "key": api_key.key_prefix + "…",
        "key_prefix": api_key.key_prefix,
        "name": api_key.label,
        "plan": user.plan,   # plan lives on User; avoid lazy-loading api_key.user after session close
        "is_active": api_key.is_active,
        "total_requests": api_key.total_requests,
        "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
        "last_used_at": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
    }


@app.post("/v1/keys/{key_value}/revoke", status_code=204)
async def revoke_key_endpoint(key_value: str, current_key: APIKey = Depends(require_api_key)):
    """Revoke the currently authenticated key (self-service)."""
    # Verify the caller is revoking their own key by comparing SHA-256 hashes.
    # The raw key is never stored, so we hash the URL param and compare to the
    # stored hash — equivalent to comparing raw keys without exposing them.
    import hashlib as _hashlib
    if _hashlib.sha256(key_value.encode()).hexdigest() != current_key.key_hash:
        raise HTTPException(403, "You can only revoke your own key")
    from api.auth import revoke_key as _revoke_key
    _revoke_key(key_value)


# ---------------------------------------------------------------------------
# Jobs listing route
# ---------------------------------------------------------------------------

@app.get("/v1/jobs")
async def list_jobs(
    db: Session = Depends(get_db),
    current_auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    List all jobs for the authenticated user.
    Reads from the database (Postgres) so results persist across deployments
    and are consistent with PowerSync.
    """
    from api.schema import Job as _Job

    user, _ = current_auth
    rows = (
        db.query(_Job)
        .filter(_Job.user_id == user.id)
        .order_by(_Job.created_at.desc())
        .all()
    )

    jobs = []
    for row in rows:
        submitted_at = row.created_at.isoformat() if row.created_at else None
        jobs.append({
            "video_id": row.id,
            "status": row.status or "queued",
            "progress_percent": row.progress_percent or 0,
            "submitted_at": submitted_at,
            "duration_seconds": row.duration_seconds,
            "summary": row.summary,
        })

    return jobs


# ---------------------------------------------------------------------------
# Chat endpoint — query a completed video analysis with natural language
# ---------------------------------------------------------------------------

class _ChatMessage(_BaseModel):
    role: str     # "user" | "model"
    content: str


class _ChatRequest(_BaseModel):
    video_id: str
    message: str
    history: list[_ChatMessage] = []


def _build_video_context(result: dict) -> str:
    """Build a compact text context from a pipeline result dict for Gemini."""
    meta = result.get("metadata", {})
    lines = [
        "=== VIDEO ANALYSIS DATA ===",
        f"Summary: {result.get('summary', '')}",
        "",
        "Metadata:",
        f"  Duration: {meta.get('duration_seconds', '?')}s",
        f"  Resolution: {meta.get('processed_resolution', '?')}",
        f"  Keyframes analysed: {meta.get('keyframes_analyzed', '?')}",
        f"  Duplicates removed: {meta.get('duplicates_removed', '?')}",
        "",
    ]

    # Audio transcript — speech and notable audio events
    audio_segments = [
        seg for seg in result.get("audio_segments", [])
        if seg.get("segment_type") not in ("silence", "ambient")
    ]
    if audio_segments:
        lines.append("Audio transcript:")
        for seg in audio_segments:
            seg_type = seg.get("segment_type", "")
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            content = seg.get("content", "")
            m_s, s_s = int(start // 60), start % 60
            m_e, s_e = int(end // 60), end % 60
            ts = f"{m_s}:{s_s:05.2f}–{m_e}:{s_e:05.2f}"
            prefix = "[speech]" if seg_type == "speech" else f"[{seg_type}]"
            lines.append(f"  {ts} {prefix} {content}")
        lines.append("")

    lines.append("Timeline (keyframe-by-keyframe):")
    for kf in result.get("timeline", []):
        sc = "SCENE_CHANGE" if kf.get("scene_change") else ""
        objs = ", ".join(kf.get("detected_objects") or []) or "—"
        cam = kf.get("camera_movement") or "—"
        actions = kf.get("actions") or ""
        desc = kf.get("description", "")
        ts = f"[{kf.get('timestamp_start','?')}–{kf.get('timestamp_end','?')}]"
        header = f"{ts} {sc}  cam:{cam}  obj:[{objs}]"
        if actions:
            header += f"  action:{actions}"
        lines.append(f"  {header}")
        lines.append(f"    {desc}")
    return "\n".join(lines)


@app.get("/v1/chats/{video_id}")
async def get_chat_messages(
    video_id: str,
    db: Session = Depends(get_db),
    current_auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """Return persisted chat messages for a completed video, ordered chronologically."""
    _validate_video_id(video_id)
    user, _ = current_auth
    from api.schema import ChatMessage as _ChatMsg
    msgs = (
        db.query(_ChatMsg)
        .filter(_ChatMsg.video_id == video_id, _ChatMsg.user_id == user.id)
        .order_by(_ChatMsg.created_at)
        .all()
    )
    return [{"id": m.id, "role": m.role, "content": m.content} for m in msgs]


@app.post("/v1/chat")
async def chat_about_video(
    body: _ChatRequest,
    db: Session = Depends(get_db),
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    Answer natural-language questions about a completed video analysis.
    Sends the structured JSON as context to Gemini and streams back a response.
    Maintains conversation history via the `history` field.
    """
    _validate_video_id(body.video_id)
    user, _ = _auth
    jdir = _job_dir(body.video_id)
    _assert_owner(jdir, user.id)
    rp = _result_path(jdir)

    if not os.path.exists(rp):
        raise HTTPException(409, "Analysis not yet complete")

    with open(rp) as f:
        result = json.load(f)

    context = _build_video_context(result)

    system_instruction = (
        "You are a knowledgeable, conversational video analyst. "
        "A user has uploaded a video and you have access to a detailed frame-by-frame analysis of it below.\n\n"
        "When answering questions, respond like a person who has actually watched the video — "
        "write in a natural, narrative style, not a dry technical list. "
        "Describe what happens as if you're telling someone about it: paint a picture, mention the mood, "
        "reference what's on screen in plain language, and group related moments into coherent paragraphs.\n\n"
        "You also have access to Google Search. Use it proactively whenever the video references real people, "
        "brands, events, songs, locations, or anything where external context would meaningfully enrich your answer. "
        "For example: if a name appears on screen, search for who that person is; if a song is playing, search for it; "
        "if an event is referenced, search for background on it. Blend that real-world knowledge naturally into your answer.\n\n"
        "Use **bold** for emphasis on key moments or subjects. "
        "Use section headers (## like this) when breaking a longer answer into clear parts. "
        "When mentioning specific moments, weave timestamps naturally into the prose "
        "(e.g. 'Around the 0:30 mark…' or 'By 1:15, the scene shifts to…'). "
        "Never output raw JSON, object notation, or keyframe IDs — translate everything into plain English.\n\n"
        "If the analysis data doesn't contain enough information to answer confidently, say so honestly "
        "rather than fabricating details.\n\n"
        + context
    )

    if genai is None:
        raise HTTPException(500, "Chat service not available (google-genai not installed)")

    client = genai.Client(
        api_key=settings.gemini_api_key.get_secret_value()
    )

    contents = []
    for msg in body.history:
        role = msg.role if msg.role in ("user", "model") else "user"
        contents.append(
            genai_types.Content(role=role, parts=[genai_types.Part(text=msg.content)])
        )
    contents.append(
        genai_types.Content(role="user", parts=[genai_types.Part(text=body.message)])
    )

    ref = secrets.token_hex(4)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=8000),
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
            ),
        )
    except Exception as exc:
        logger.error("Chat error [ref=%s] video_id=%s: %s", ref, body.video_id, exc)
        raise HTTPException(500, f"Chat failed (ref: {ref})")

    # Persist messages to DB (best-effort — never block the response)
    try:
        from api.schema import ChatMessage as _ChatMsg
        user, _ = _auth
        db.add(_ChatMsg(video_id=body.video_id, user_id=user.id, role="user",      content=body.message))
        db.add(_ChatMsg(video_id=body.video_id, user_id=user.id, role="assistant", content=response.text))
        db.commit()
    except Exception as _pe:
        logger.warning("Failed to persist chat messages: %s", _pe)

    return {
        "response": response.text,
        "video_id": body.video_id,
    }


# ---------------------------------------------------------------------------
# Push notifications — FCM token registration
# ---------------------------------------------------------------------------

class _RegisterFcmTokenRequest(_BaseModel):
    token: str


@app.post("/v1/notifications/register", status_code=204)
async def register_fcm_token(
    body: _RegisterFcmTokenRequest,
    db: Session = Depends(get_db),
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    Upsert an FCM device registration token for the authenticated user.
    Called by the frontend after the user grants notification permission.
    """
    from api.schema import FcmToken as _FcmToken
    user, _ = _auth
    if not body.token:
        raise HTTPException(400, "Token required")
    existing = db.query(_FcmToken).filter_by(user_id=user.id, token=body.token).first()
    if not existing:
        db.add(_FcmToken(user_id=user.id, token=body.token))
        db.commit()


# ---------------------------------------------------------------------------
# PowerSync — JWT token vending for real-time client sync
# ---------------------------------------------------------------------------

@app.get("/v1/powersync/token")
async def get_powersync_token(
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    Vend a short-lived JWT for the PowerSync client.

    The client calls this from BackendConnector.fetchCredentials() on connect
    and whenever the token is about to expire.  The JWT is signed with
    POWERSYNC_JWT_SECRET and carries {sub: user_id} so PowerSync Sync Streams
    can filter data with auth.user_id().
    """
    if not settings.powersync_url or not settings.powersync_jwt_secret.get_secret_value():
        raise HTTPException(503, "PowerSync is not configured on this server")

    import base64 as _b64
    import jwt as _jwt
    from datetime import datetime, timedelta, timezone as _tz

    user, _ = _auth
    now = datetime.now(tz=_tz.utc)
    payload = {
        "sub": user.id,
        "aud": settings.powersync_url,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    # PowerSync stores HS256 secrets as base64url-encoded.  Decode to get
    # the raw key bytes so our HMAC signature matches what PowerSync expects.
    _raw_secret = settings.powersync_jwt_secret.get_secret_value()
    _padded = _raw_secret + "=" * (-len(_raw_secret) % 4)
    _key = _b64.urlsafe_b64decode(_padded)
    token = _jwt.encode(
        payload,
        _key,
        algorithm="HS256",
        headers={"kid": "HS256 authentication token"},
    )
    return {"token": token, "powersync_url": settings.powersync_url}


# ---------------------------------------------------------------------------
# Backfill — populate jobs + timeline_entries for pre-existing analyses
# ---------------------------------------------------------------------------

@app.post("/v1/admin/backfill", status_code=200)
async def backfill_timeline_entries(
    db: Session = Depends(get_db),
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    One-time backfill: scan all vid_* directories owned by the authenticated
    user, upsert a row in `jobs`, and populate `timeline_entries` from
    result.json.  Safe to call multiple times — uses upsert logic.
    """
    import glob as _glob
    from datetime import datetime, timezone as _tz
    from api.schema import Job as _Job, TimelineEntry as _TE

    user, _ = _auth
    output_base = os.path.realpath(settings.output_dir)
    job_dirs = sorted(_glob.glob(os.path.join(output_base, "vid_*")))

    upserted_jobs = 0
    upserted_entries = 0

    for jdir in job_dirs:
        vid_id = os.path.basename(jdir)
        if not _VIDEO_ID_RE.fullmatch(vid_id):
            continue

        owner = _read_meta_user_id(jdir)
        if owner is None or owner != user.id:
            continue

        rp = _result_path(jdir)
        if not os.path.exists(rp):
            continue

        try:
            with open(rp) as f:
                result = json.load(f)
        except Exception:
            continue

        meta = result.get("metadata", {})

        # Upsert the job row
        existing_job = db.query(_Job).filter_by(id=vid_id).first()
        if existing_job is None:
            mtime = os.path.getmtime(jdir)
            created = datetime.fromtimestamp(mtime, tz=_tz.utc)
            input_filename = meta.get("input_filename") or vid_id
            db.add(_Job(
                id=vid_id,
                user_id=user.id,
                status="complete",
                input_filename=input_filename,
                input_type="file",
                fps_used=meta.get("fps_used") or meta.get("processed_fps") or 5,
                duration_seconds=meta.get("duration_seconds"),
                progress_percent=100,
                current_stage=None,
                summary=result.get("summary"),
                queued_at=created,
                started_at=created,
                completed_at=created,
                created_at=created,
            ))
            db.flush()
            upserted_jobs += 1
        else:
            if existing_job.summary is None:
                existing_job.summary = result.get("summary")

        # Upsert timeline_entries
        def _parse_ts(v):
            if v is None: return 0.0
            try: return float(v)
            except (ValueError, TypeError):
                try:
                    s = str(v)
                    if ':' in s:
                        p = s.split(':')
                        return float(p[0]) * 60 + float(p[1])
                except Exception: pass
                return 0.0

        timeline = result.get("timeline", [])
        for idx, kf in enumerate(timeline):
            entry_id = f"{vid_id}_{idx:06d}"
            if db.query(_TE).filter_by(id=entry_id).first() is None:
                objs = kf.get("detected_objects") or []
                objs_str = json.dumps(objs) if isinstance(objs, list) else str(objs)
                db.add(_TE(
                    id=entry_id,
                    job_id=vid_id,
                    user_id=user.id,
                    keyframe_index=idx,
                    timestamp_start=_parse_ts(kf.get("timestamp_start")),
                    timestamp_end=_parse_ts(kf.get("timestamp_end")),
                    description=kf.get("description"),
                    detected_objects=objs_str,
                    camera_movement=kf.get("camera_movement"),
                    confidence=float(kf.get("confidence")) if kf.get("confidence") is not None else None,
                ))
                upserted_entries += 1

    db.commit()
    return {"upserted_jobs": upserted_jobs, "upserted_entries": upserted_entries}


# ---------------------------------------------------------------------------
# Library — cross-video Mastra agent proxy
# ---------------------------------------------------------------------------

class _LibraryChatRequest(_BaseModel):
    message: str


@app.get("/v1/library/messages")
async def get_library_messages(
    db: Session = Depends(get_db),
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """Return the authenticated user's cross-video library chat history."""
    user, _ = _auth
    from api.schema import LibraryMessage as _LibMsg
    msgs = (
        db.query(_LibMsg)
        .filter(_LibMsg.user_id == user.id)
        .order_by(_LibMsg.created_at)
        .all()
    )
    return [{"id": m.id, "role": m.role, "content": m.content} for m in msgs]


@app.post("/v1/library/chat")
async def library_chat(
    body: _LibraryChatRequest,
    _auth: tuple[User, Optional[APIKey]] = Depends(require_auth),
):
    """
    Proxy a cross-video question to the Mastra library agent service.

    The Mastra service handles tool calls (timeline FTS, list_videos) and
    persists both messages to library_messages → PowerSync syncs them.
    """
    user, _ = _auth
    mastra_url = os.environ.get("MASTRA_URL", "http://mastra:3001")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{mastra_url}/chat",
                json={"user_id": user.id, "message": body.message},
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Mastra agent error: %s", exc)
        raise HTTPException(502, "Library agent unavailable")
    except Exception as exc:
        logger.error("Mastra proxy error: %s", exc)
        raise HTTPException(502, "Library agent unavailable")


# ---------------------------------------------------------------------------
# SPA static file serving (must come last — after all API routes)
# ---------------------------------------------------------------------------

import pathlib as _pathlib

_web_dist = _pathlib.Path(__file__).parent.parent / "web" / "dist"

if _web_dist.is_dir():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse as _FileResponse

    # Required for PowerSync WASM (SharedArrayBuffer) in production.
    # The Vite dev server sets these headers; we must mirror them here.
    # COOP: same-origin-allow-popups enables SharedArrayBuffer while still
    # allowing Google Sign-In popups (GIS) to post credentials back to the
    # opener.  "same-origin" blocks this cross-origin postMessage relay.
    # COEP: credentialless allows cross-origin fetches (PowerSync WebSocket)
    # without requiring them to send CORP headers.
    _COOP_HEADERS = {
        "Cross-Origin-Opener-Policy":   "same-origin-allow-popups",
        "Cross-Origin-Embedder-Policy": "credentialless",
    }

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        static_file = _web_dist / full_path
        target = str(static_file) if static_file.is_file() else str(_web_dist / "index.html")
        return _FileResponse(target, headers=_COOP_HEADERS)

    app.mount("/assets", StaticFiles(directory=str(_web_dist / "assets")), name="assets")
