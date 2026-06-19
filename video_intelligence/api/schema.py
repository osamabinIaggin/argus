"""
SQLAlchemy ORM models — complete application schema.

Tables
------
users                   Core identity record.
email_verifications     One-time token to confirm an email address.
password_reset_tokens   One-time token for password recovery.
refresh_tokens          JWT refresh tokens (SHA-256 hash stored, never the raw token).
api_keys                Machine-to-machine API keys (SHA-256 hash stored, never the raw key).
jobs                    One row per video-processing job.
usage_events            Append-only billing ledger; one row per billable event.
invoices                Monthly invoice rollups.

Security notes
--------------
* Passwords         — hashed with argon2id (argon2-cffi). Never stored in plaintext.
* API keys          — only SHA-256(raw_key) stored. Raw key is returned once at
                      creation and never persisted. A compromised DB exposes only
                      hashes with 128-bit pre-image resistance — unusable without the
                      original random key.
* Refresh tokens    — only SHA-256(raw_token) stored. Raw token lives on the client
                      (httpOnly cookie or secure storage). Same rationale as API keys.
* Email / PW reset  — same SHA-256-hash-on-store pattern; expire after fixed TTL.
* User PKs          — UUID4 strings, non-sequential, to prevent enumeration attacks.
* Soft deletes      — users.deleted_at is set instead of issuing DELETE. ON DELETE
                      CASCADE on child FKs handles hard-deletion of child rows in the DB
                      when a user is eventually purged (e.g. GDPR erasure).
* Monetary values   — stored as NUMERIC (exact decimal), never FLOAT.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.database import Base


# ---------------------------------------------------------------------------
# Domain enums
# Used in application code for type safety; stored as plain VARCHAR in the DB
# for portability across SQLite (dev) and PostgreSQL (production).
# ---------------------------------------------------------------------------

class Plan(str, enum.Enum):
    free       = "free"
    starter    = "starter"
    pro        = "pro"
    enterprise = "enterprise"


class JobStatus(str, enum.Enum):
    queued     = "queued"
    processing = "processing"
    complete   = "complete"
    failed     = "failed"


class UsageEventType(str, enum.Enum):
    video_processed = "video_processed"   # billable: seconds of video processed
    api_request     = "api_request"       # informational: one per authenticated call
    storage_gb_day  = "storage_gb_day"    # billable: GB × days of result retention


class InvoiceStatus(str, enum.Enum):
    draft = "draft"   # accumulating; not yet sent to customer
    open  = "open"    # sent to customer; awaiting payment
    paid  = "paid"    # payment confirmed by Stripe webhook
    void  = "void"    # cancelled or refunded


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(Base):
    """
    Core identity record.  One row per registered user.

    Plan lives here, not on APIKey: a single plan applies to all of a user's
    keys.  Changing the plan in one place takes effect everywhere.

    Soft-delete via deleted_at preserves audit history and satisfies referential
    integrity.  Downstream rows are removed by ON DELETE CASCADE when the user
    record is eventually hard-deleted (e.g. GDPR erasure request).
    """
    __tablename__ = "users"

    id = Column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Stored lowercase and stripped.  Application MUST normalise (lower + strip)
    # before every insert and lookup to prevent duplicate accounts.
    email = Column(String(254), nullable=False, unique=True)

    # Null until the user clicks the verification link sent to their inbox.
    email_verified_at = Column(DateTime(timezone=True), nullable=True)

    # argon2id hash produced by argon2-cffi.
    # Null for API-key-only accounts created before the user set a password
    # (e.g. via the legacy unauthenticated POST /v1/keys endpoint).
    password_hash = Column(String(255), nullable=True)

    # Free-form name shown in the dashboard.  Not used for authentication.
    display_name = Column(String(100), nullable=True)

    # "free" | "starter" | "pro" | "enterprise"
    plan = Column(
        String(20), nullable=False,
        default=Plan.free.value, server_default="free",
    )

    # Populated when the Stripe Customer object is created for this user.
    stripe_customer_id = Column(String(64), nullable=True, unique=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    # Soft delete.  Set this field instead of issuing DELETE on the users row.
    # ON DELETE CASCADE FKs will remove child rows when the user is hard-deleted.
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    api_keys              = relationship("APIKey",              back_populates="user",  cascade="all, delete-orphan")
    refresh_tokens        = relationship("RefreshToken",        back_populates="user",  cascade="all, delete-orphan")
    email_verifications   = relationship("EmailVerification",   back_populates="user",  cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken",  back_populates="user",  cascade="all, delete-orphan")
    jobs                  = relationship("Job",                 back_populates="user",  passive_deletes=True)
    usage_events          = relationship("UsageEvent",          back_populates="user",  passive_deletes=True)
    invoices              = relationship("Invoice",             back_populates="user",  passive_deletes=True)
    chat_messages         = relationship("ChatMessage",         back_populates="user",  cascade="all, delete-orphan")
    fcm_tokens            = relationship("FcmToken",            back_populates="user",  cascade="all, delete-orphan")
    timeline_entries      = relationship("TimelineEntry",       back_populates="user",  cascade="all, delete-orphan")
    library_messages      = relationship("LibraryMessage",      back_populates="user",  cascade="all, delete-orphan")

    __table_args__ = (
        # Speeds up "list all active users" and soft-delete filter queries.
        Index("ix_users_deleted_at", "deleted_at"),
    )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class EmailVerification(Base):
    """
    One-time token emailed to the user to confirm their address.

    Security model:
      1. Generate 32 random bytes → 64-char lowercase hex string (raw_token).
      2. Store SHA-256(raw_token) in token_hash; put raw_token in the email link.
      3. On click: SHA-256 the URL param, query by hash, check expiry + used_at.
      4. Mark used_at immediately to prevent replay within the validity window.

    Tokens expire after 24 hours (enforced in application code).
    """
    __tablename__ = "email_verifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256(raw_token) hex digest — 64 chars.  The only lookup column.
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="email_verifications")

    __table_args__ = (
        Index("ix_email_verifications_token_hash", "token_hash"),
        Index("ix_email_verifications_user_id",    "user_id"),
    )


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------

class PasswordResetToken(Base):
    """
    One-time token for password recovery.

    Same SHA-256-hash-on-store security model as EmailVerification.
    Tokens expire after 1 hour (enforced in application code).
    Only the most recent unused token for a user is valid; older ones
    should be invalidated on new requests (enforced in application code).
    """
    __tablename__ = "password_reset_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="password_reset_tokens")

    __table_args__ = (
        Index("ix_password_reset_tokens_token_hash", "token_hash"),
        Index("ix_password_reset_tokens_user_id",    "user_id"),
    )


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

class RefreshToken(Base):
    """
    Rotating refresh tokens for JWT sessions.

    Token lifecycle:
      - Access tokens (JWT): short-lived (15 min), verified by signature only —
        no DB lookup required per request.
      - Refresh tokens: long-lived (30 days), stored here as SHA-256 hashes.
        The raw token is sent to the client once (httpOnly cookie or secure storage).

    Rotation (RFC 6749 Security BCP §2.2.2):
      - On every POST /auth/refresh, issue a new token and revoke the old one.
      - All tokens in one logical session share the same `family` UUID.
      - If a previously-revoked token from a family is presented, it means the
        token was stolen: immediately revoke ALL tokens in that family.

    Audit trail:
      - ip_address and user_agent are recorded at creation for security review.
        They are never used for authentication decisions.
    """
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256(raw_token) hex — 64 chars.  The lookup column.
    token_hash = Column(String(64), nullable=False, unique=True)
    # Groups all rotated tokens for one logical session.  Used for family revocation.
    family     = Column(String(36), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Audit fields — stored but never used for auth decisions.
    ip_address = Column(String(45),  nullable=True)   # max IPv6 length = 45 chars
    user_agent = Column(String(512), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash"),
        Index("ix_refresh_tokens_user_id",    "user_id"),
        Index("ix_refresh_tokens_family",     "family"),
    )


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

class APIKey(Base):
    """
    Machine-to-machine API keys.

    Security model:
      - Raw key format: vi_live_<32 lowercase hex chars>  (128 bits of entropy).
      - Only SHA-256(raw_key) is persisted.  The plaintext key is returned once
        at creation, shown to the user, and never stored.  A compromised database
        exposes only SHA-256 hashes — reversing them requires finding a 128-bit
        pre-image, which is computationally infeasible.
      - Authenticated requests: SHA-256(Bearer token) → key_hash index lookup.
      - Note: SHA-256 is appropriate here because the raw key is random (high
        entropy).  Passwords use argon2id (slow, salted) precisely because they
        are low-entropy.  API keys don't need the extra cost.

    Plan lives on User, not here: one plan covers all of a user's keys.

    key_prefix (first 16 chars of the raw key, e.g. "vi_live_4a2f8c4d") is safe
    to store and display — it is not a secret and cannot be used to reconstruct
    or brute-force the full key.
    """
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # SHA-256(raw_key) hex — 64 chars.  The only lookup column for auth.
    key_hash   = Column(String(64), nullable=False, unique=True)
    # First 16 chars of raw key — safe to store and display.
    key_prefix = Column(String(16), nullable=False)
    # User-assigned label, e.g. "Production", "Staging", "CI Pipeline".
    label      = Column(String(100), nullable=False, default="Default")

    is_active      = Column(Boolean, nullable=False, default=True,  server_default="1")
    total_requests = Column(Integer, nullable=False, default=0,     server_default="0")

    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at   = Column(DateTime(timezone=True), nullable=True)
    # Optional hard expiry date.  None = key never expires until explicitly revoked.
    expires_at   = Column(DateTime(timezone=True), nullable=True)

    user         = relationship("User",       back_populates="api_keys")
    jobs         = relationship("Job",        back_populates="api_key",  passive_deletes=True)
    usage_events = relationship("UsageEvent", back_populates="api_key",  passive_deletes=True)

    __table_args__ = (
        Index("ix_api_keys_user_id",  "user_id"),
        Index("ix_api_keys_key_hash", "key_hash"),
    )

    # ------------------------------------------------------------------
    # Convenience properties
    # Delegate plan/name to the parent User so endpoint handlers can use
    # key.plan and key.name without changing with every schema migration.
    # ------------------------------------------------------------------

    @property
    def plan(self) -> str:
        """The owning user's plan string, e.g. 'free'."""
        return self.user.plan if self.user else Plan.free.value

    @property
    def name(self) -> str:
        """Alias for label — used by legacy endpoints that predate multi-key support."""
        return self.label


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class Job(Base):
    """
    One row per video-processing job.

    The job ID reuses the vid_<32hex> format already used by the pipeline so
    that existing output directories and result.json files remain valid during
    the migration from directory-only to database-backed job tracking.

    api_key_id uses SET NULL on delete so that revoking or deleting a key does
    not wipe out the audit trail of jobs it submitted.
    """
    __tablename__ = "jobs"

    # "vid_" (4) + 32 hex chars = 36 chars total.
    id = Column(String(36), primary_key=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Preserved for audit even after the key is revoked or deleted.
    api_key_id = Column(
        String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )

    # "queued" | "processing" | "complete" | "failed"
    status = Column(
        String(20), nullable=False,
        default=JobStatus.queued.value, server_default="queued",
    )

    # "file" or "url"
    input_type     = Column(String(4),   nullable=True)
    input_filename = Column(String(255), nullable=True)   # original upload filename
    # Original URL — stored for audit, never re-fetched from here.
    input_url      = Column(Text,        nullable=True)
    input_size_bytes = Column(Integer,   nullable=True)
    fps_used         = Column(Integer,   nullable=True)

    # Populated once the pipeline has probed the video.
    duration_seconds = Column(Numeric(10, 3), nullable=True)

    # Relative path to result.json within OUTPUT_DIR.
    output_path = Column(String(500), nullable=True)

    # Opaque 8-char hex ref returned in 500 errors so support can correlate
    # a user's error report with the server-side log entry.
    error_ref = Column(String(8), nullable=True)

    queued_at    = Column(DateTime(timezone=True), nullable=True)
    started_at   = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at    = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Real-time sync fields — updated live by the pipeline worker and synced to
    # clients via PowerSync so the UI never needs to poll.
    progress_percent = Column(Integer, nullable=False, default=0, server_default="0")
    current_stage    = Column(String(50), nullable=True)
    # Cached from result.json after completion — avoids disk reads in /v1/jobs.
    summary          = Column(Text, nullable=True)

    user         = relationship("User",       back_populates="jobs")
    api_key      = relationship("APIKey",     back_populates="jobs")
    usage_events = relationship("UsageEvent", back_populates="job", passive_deletes=True)

    __table_args__ = (
        Index("ix_jobs_user_id",        "user_id"),
        # Covers "list all queued jobs for user X" without a full table scan.
        Index("ix_jobs_user_id_status", "user_id", "status"),
        Index("ix_jobs_api_key_id",     "api_key_id"),
        Index("ix_jobs_created_at",     "created_at"),
    )


# ---------------------------------------------------------------------------
# Usage events  (append-only billing ledger)
# ---------------------------------------------------------------------------

class UsageEvent(Base):
    """
    Immutable billing ledger.  Application code MUST NOT update or delete rows.

    One row per billable (or informational) event:
      video_processed  — quantity = video duration in seconds.
      api_request      — quantity = 1 per authenticated API call.
      storage_gb_day   — quantity = GB × days of result file retention.

    unit_cost_usd is a SNAPSHOT of the price at the moment the event occurs.
    Prices can change over time; stored historical costs must never be
    recalculated from current prices.  This is the standard approach used by
    Stripe, AWS, and similar platforms.

    billing_period ("YYYY-MM") partitions events into calendar months for fast
    invoice rollup queries without date arithmetic on every row.

    invoice_id is null until the monthly billing job closes the period and
    creates an Invoice record.
    """
    __tablename__ = "usage_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL FKs: deleting a job, key, or invoice preserves the billing record.
    job_id = Column(
        String(36), ForeignKey("jobs.id",     ondelete="SET NULL"), nullable=True
    )
    api_key_id = Column(
        String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    invoice_id = Column(
        String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )

    # "video_processed" | "api_request" | "storage_gb_day"
    event_type = Column(String(30), nullable=False)
    # Seconds of video, count of requests, or GB-days of storage.
    quantity   = Column(Numeric(12, 4), nullable=False)
    # Human-readable unit matching event_type: "seconds", "requests", "gb_day".
    unit       = Column(String(20),     nullable=False)

    # Price snapshot — NEVER recalculate from current prices retroactively.
    unit_cost_usd  = Column(Numeric(10, 6), nullable=False, default=0)
    total_cost_usd = Column(Numeric(10, 4), nullable=False, default=0)

    # "YYYY-MM" — partitioning key for O(1) monthly rollup queries.
    billing_period = Column(String(7), nullable=False)

    # Set by the billing job when this event is included in an invoice.
    billed_at  = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user    = relationship("User",    back_populates="usage_events")
    job     = relationship("Job",     back_populates="usage_events")
    api_key = relationship("APIKey",  back_populates="usage_events")
    invoice = relationship("Invoice", back_populates="usage_events")

    __table_args__ = (
        Index("ix_usage_events_user_id",             "user_id"),
        # Primary rollup query: all events for user X in month YYYY-MM.
        Index("ix_usage_events_user_billing_period", "user_id", "billing_period"),
        Index("ix_usage_events_billing_period",      "billing_period"),
        Index("ix_usage_events_job_id",              "job_id"),
        # Billing job queries: events not yet billed (billed_at IS NULL).
        Index("ix_usage_events_billed_at",           "billed_at"),
        Index("ix_usage_events_created_at",          "created_at"),
    )


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

class ChatMessage(Base):
    """
    Persisted chat message for a video analysis conversation.

    video_id references the file-based job directory (no FK — jobs live on disk).
    user_id FK ensures messages are deleted if the user is hard-deleted.
    """
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # File-based job id — stored as plain string, no DB FK (jobs live on disk).
    video_id = Column(String(36), nullable=False)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "user" | "assistant"
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="chat_messages")

    __table_args__ = (
        Index("ix_chat_messages_video_id",   "video_id"),
        Index("ix_chat_messages_user_id",    "user_id"),
        Index("ix_chat_messages_created_at", "created_at"),
    )


class TimelineEntry(Base):
    """
    One row per keyframe in a completed job.

    Denormalised with user_id so PowerSync can filter with auth.user_id().
    Populated by the Celery worker after result.json is written.
    id = "{job_id}_{keyframe_index:06d}"
    """
    __tablename__ = "timeline_entries"

    id = Column(String(64), primary_key=True)  # e.g. "vid_abc..._{000001}"
    job_id = Column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    keyframe_index   = Column(Integer, nullable=False)
    timestamp_start  = Column(Float, nullable=False)
    timestamp_end    = Column(Float, nullable=False)
    description      = Column(Text, nullable=True)
    detected_objects = Column(Text, nullable=True)   # JSON array string
    camera_movement  = Column(String(50), nullable=True)
    confidence       = Column(Float, nullable=True)

    user = relationship("User", back_populates="timeline_entries")

    __table_args__ = (
        Index("ix_timeline_entries_job_id",  "job_id"),
        Index("ix_timeline_entries_user_id", "user_id"),
    )


class LibraryMessage(Base):
    """
    Cross-video agent (Mastra) chat history.

    Scoped by user_id.  PowerSync syncs these to all devices in real-time.
    """
    __tablename__ = "library_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role    = Column(String(10), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="library_messages")

    __table_args__ = (
        Index("ix_library_messages_user_id",    "user_id"),
        Index("ix_library_messages_created_at", "created_at"),
    )


class FcmToken(Base):
    """
    FCM device registration tokens for web push notifications.

    One row per (user, device).  Tokens are upserted on every app load
    (FCM can rotate them).  Deleted when the user is hard-deleted via CASCADE.
    """
    __tablename__ = "fcm_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    user = relationship("User", back_populates="fcm_tokens")

    __table_args__ = (
        UniqueConstraint("user_id", "token", name="uq_fcm_tokens_user_token"),
        Index("ix_fcm_tokens_user_id", "user_id"),
    )


class Invoice(Base):
    """
    Monthly invoice rolled up from usage_events.

    One invoice per user per billing_period.  Lifecycle:
      draft  → accumulating usage events for the current month.
      open   → period closed; invoice generated and sent to the customer.
      paid   → Stripe confirmed payment (webhook).
      void   → cancelled or refunded.

    stripe_invoice_id is populated when the invoice is synced to Stripe.
    The UniqueConstraint on (user_id, billing_period) guarantees exactly one
    invoice per user per calendar month.
    """
    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "YYYY-MM" — matches usage_events.billing_period.
    billing_period = Column(String(7), nullable=False)

    # "draft" | "open" | "paid" | "void"
    status = Column(
        String(10), nullable=False,
        default=InvoiceStatus.draft.value, server_default="draft",
    )

    # Pre-discount total; keep both for future coupon/credit support.
    subtotal_usd = Column(Numeric(10, 2), nullable=False, default=0)
    total_usd    = Column(Numeric(10, 2), nullable=False, default=0)

    # Populated when this invoice is synced to Stripe.
    stripe_invoice_id = Column(String(64), nullable=True, unique=True)

    issued_at  = Column(DateTime(timezone=True), nullable=True)
    due_at     = Column(DateTime(timezone=True), nullable=True)
    paid_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    user         = relationship("User",       back_populates="invoices")
    usage_events = relationship("UsageEvent", back_populates="invoice")

    __table_args__ = (
        # One invoice per user per calendar month — enforced at the DB level.
        UniqueConstraint("user_id", "billing_period", name="uq_invoices_user_period"),
        Index("ix_invoices_user_id",        "user_id"),
        Index("ix_invoices_billing_period", "billing_period"),
        Index("ix_invoices_status",         "status"),
    )
