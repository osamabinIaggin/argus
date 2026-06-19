"""
Authentication helpers — API keys, JWTs, refresh tokens, and user management.

Security model
--------------
API keys
  - Raw key format: vi_live_<32 lowercase hex chars>  (128-bit entropy).
  - Only SHA-256(raw_key) is stored. Lookup: SHA-256(bearer_token) → key_hash.

Passwords
  - Hashed with argon2id (argon2-cffi). Never stored or logged in plaintext.

Access tokens (JWT)
  - Short-lived (15 min). Signed with HS256 + JWT_SECRET.
  - Payload: {sub: user_id, type: "access", iat, exp}.
  - No DB lookup per request — signature verification only.

Refresh tokens
  - Long-lived (30 days). SHA-256(raw_token) stored; raw token sent to client once.
  - Token rotation: every use issues a new token and revokes the old one.
  - Token-family theft detection (RFC 6749 Security BCP §2.2.2):
    if a revoked token is presented, all tokens in the family are revoked.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Header, HTTPException
from sqlalchemy.orm import joinedload

from api.config import settings
from api.database import SessionLocal
from api.schema import APIKey, Plan, RefreshToken, User

# ---------------------------------------------------------------------------
# argon2-cffi — optional at import time so the module loads for key-only usage
# ---------------------------------------------------------------------------
try:
    from argon2 import PasswordHasher as _PasswordHasher
    from argon2.exceptions import VerifyMismatchError as _VerifyMismatchError
    _ph = _PasswordHasher()
    _ARGON2_AVAILABLE = True
except ImportError:
    _ARGON2_AVAILABLE = False


# ---------------------------------------------------------------------------
# Low-level cryptographic helpers
# ---------------------------------------------------------------------------

def _hash(value: str) -> str:
    """SHA-256 hex digest — used for API keys, refresh tokens, email tokens."""
    return hashlib.sha256(value.encode()).hexdigest()


def generate_key() -> str:
    """Return a new random API key string (128 bits of entropy, never stored)."""
    return f"vi_live_{secrets.token_hex(16)}"


def hash_password(plain: str) -> str:
    """Hash a plaintext password with argon2id. Raises if argon2-cffi is missing."""
    if not _ARGON2_AVAILABLE:
        raise RuntimeError(
            "argon2-cffi is required for password hashing: pip install argon2-cffi"
        )
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time argon2id verification. Returns False on any failure."""
    if not _ARGON2_AVAILABLE or not hashed:
        return False
    try:
        return _ph.verify(hashed, plain)
    except _VerifyMismatchError:
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT — access tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    """
    Issue a short-lived HS256 JWT for the given user.

    Payload: {sub, type, iat, exp}.
    The 'type' claim prevents refresh tokens from being used as access tokens.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub":  user_id,
        "type": "access",
        "iat":  now,
        "exp":  now + timedelta(minutes=settings.jwt_access_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> Optional[str]:
    """
    Verify and decode an access token.

    Returns the user_id (sub) on success, None on any failure (expired,
    tampered, wrong type, etc.).  Never raises.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

def create_refresh_token(
    user_id: str,
    ip: Optional[str] = None,
    ua: Optional[str] = None,
    family: Optional[str] = None,
) -> tuple[RefreshToken, str]:
    """
    Issue a long-lived refresh token and persist its hash.

    Returns (RefreshToken ORM record, raw_token_string).
    The raw token is returned once and MUST be sent to the client immediately.

    Tokens in the same logical session share a `family` UUID, enabling
    whole-session revocation if theft is detected.
    """
    raw_token  = secrets.token_hex(32)          # 256 bits of entropy
    token_hash = _hash(raw_token)
    token_family = family or str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)

    with SessionLocal() as session:
        rt = RefreshToken(
            user_id    = user_id,
            token_hash = token_hash,
            family     = token_family,
            expires_at = expires_at,
            ip_address = ip,
            user_agent = ua,
        )
        session.add(rt)
        session.commit()
        session.refresh(rt)
        session.expunge(rt)

    return rt, raw_token


def rotate_refresh_token(
    raw_token: str,
    ip: Optional[str] = None,
    ua: Optional[str] = None,
) -> Optional[tuple[str, str, str]]:
    """
    Validate a refresh token and rotate it.

    On success: revokes the old token, issues new tokens, returns
    (new_access_token, new_raw_refresh_token, user_id).

    Returns None if the token is unknown or expired.

    Token theft detection: if a *revoked* token is presented, the entire
    family is immediately revoked to invalidate all sessions derived from
    the stolen token (RFC 6749 Security BCP §2.2.2).
    """
    token_hash = _hash(raw_token)
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        rt = (
            session.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )

        if not rt:
            return None

        # Stolen token detected — revoke the whole family.
        if rt.revoked_at is not None:
            session.query(RefreshToken).filter(
                RefreshToken.family == rt.family,
                RefreshToken.revoked_at == None,  # noqa: E711
            ).update({"revoked_at": now})
            session.commit()
            return None

        if rt.expires_at.replace(tzinfo=timezone.utc) < now:
            rt.revoked_at = now
            session.commit()
            return None

        user_id = rt.user_id
        family  = rt.family
        rt.revoked_at = now
        session.commit()

    # Issue fresh tokens within the same family (outside the session above).
    new_access  = create_access_token(user_id)
    _, new_raw_refresh = create_refresh_token(user_id, ip, ua, family=family)

    return new_access, new_raw_refresh, user_id


def revoke_refresh_token(raw_token: str) -> bool:
    """Revoke a single refresh token (logout). Returns True if found."""
    token_hash = _hash(raw_token)
    with SessionLocal() as session:
        rt = session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if rt and rt.revoked_at is None:
            rt.revoked_at = datetime.now(timezone.utc)
            session.commit()
            return True
        return False


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: str) -> Optional[User]:
    """Return a detached User by PK, or None."""
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user:
            session.expunge(user)
        return user


def get_user_by_email(email: str) -> Optional[User]:
    """Return a detached User by normalised email, or None."""
    normalised = email.lower().strip()
    with SessionLocal() as session:
        user = session.query(User).filter(User.email == normalised).first()
        if user:
            session.expunge(user)
        return user


def create_user(
    email: str,
    display_name: Optional[str] = None,
    plan: str = Plan.free.value,
    password: Optional[str] = None,
    email_verified: bool = False,
) -> User:
    """
    Create and persist a new User.

    Normalises the email before storage.  Hashes the password with argon2id
    if provided; leaves password_hash null for passwordless (OAuth-only) accounts.
    """
    normalised = email.lower().strip()
    pw_hash = hash_password(password) if password else None
    verified_at = datetime.now(timezone.utc) if email_verified else None

    with SessionLocal() as session:
        user = User(
            email             = normalised,
            display_name      = display_name,
            plan              = plan,
            password_hash     = pw_hash,
            email_verified_at = verified_at,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)

    return user


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------

def create_key(user_id: str, label: str = "Default") -> tuple[APIKey, str]:
    """
    Create and persist a new API key for the given user.

    Returns (APIKey ORM record, raw_key_string).
    The raw key is shown to the user once and never stored.
    """
    raw_key    = generate_key()
    key_hash   = _hash(raw_key)
    key_prefix = raw_key[:16]   # "vi_live_" (8 chars) + first 8 hex chars

    with SessionLocal() as session:
        api_key = APIKey(
            user_id    = user_id,
            key_hash   = key_hash,
            key_prefix = key_prefix,
            label      = label,
        )
        session.add(api_key)
        session.commit()
        session.refresh(api_key)
        user = session.get(User, user_id)
        session.expunge_all()
        api_key.user = user

    return api_key, raw_key


def create_anonymous_user_with_key(
    display_name: str,
    plan: str = "free",
) -> tuple[User, APIKey, str]:
    """
    Create a minimal (no-password) user + first API key in one transaction.

    Backward-compatible path for the unauthenticated POST /v1/keys endpoint.
    The account can be claimed later by setting a password and verifying email.
    """
    if plan not in {p.value for p in Plan}:
        raise ValueError(f"Unknown plan: {plan!r}")

    raw_key    = generate_key()
    key_hash   = _hash(raw_key)
    key_prefix = raw_key[:16]
    placeholder_email = f"anon_{key_prefix}@placeholder.vi"

    with SessionLocal() as session:
        user = User(
            email        = placeholder_email,
            display_name = display_name,
            plan         = plan,
        )
        session.add(user)
        session.flush()

        api_key = APIKey(
            user_id    = user.id,
            key_hash   = key_hash,
            key_prefix = key_prefix,
            label      = "Default",
        )
        session.add(api_key)
        session.commit()
        session.refresh(user)
        session.refresh(api_key)
        _user = user
        session.expunge_all()
        api_key.user = _user

    return _user, api_key, raw_key


def validate_key(raw_key: str) -> Optional[APIKey]:
    """
    Return the active APIKey (with .user eagerly loaded) if raw_key is valid.
    Returns None for unknown, revoked, or expired keys, or deactivated users.
    """
    key_hash = _hash(raw_key)

    with SessionLocal() as session:
        api_key = (
            session.query(APIKey)
            .options(joinedload(APIKey.user))
            .filter(
                APIKey.key_hash   == key_hash,
                APIKey.is_active  == True,
                APIKey.revoked_at == None,  # noqa: E711
            )
            .first()
        )

        if not api_key:
            return None

        if (
            not api_key.user
            or not api_key.user.is_active
            or api_key.user.deleted_at is not None
        ):
            return None

        _user = api_key.user
        session.expunge_all()
        api_key.user = _user

    return api_key


def record_request(api_key_id: str) -> None:
    """Increment total_requests and last_used_at. Best-effort — never raises."""
    try:
        with SessionLocal() as session:
            api_key = session.get(APIKey, api_key_id)
            if api_key:
                api_key.total_requests += 1
                api_key.last_used_at    = datetime.now(timezone.utc)
                session.commit()
    except Exception:
        pass


def revoke_key(raw_key: str) -> bool:
    """Deactivate a key by raw key string. Returns True if found and revoked."""
    key_hash = _hash(raw_key)
    with SessionLocal() as session:
        api_key = session.query(APIKey).filter(APIKey.key_hash == key_hash).first()
        if api_key:
            api_key.is_active  = False
            api_key.revoked_at = datetime.now(timezone.utc)
            session.commit()
            return True
        return False


def list_keys(user_id: str) -> list[APIKey]:
    """Return all API keys for a user, ordered by creation date (detached)."""
    with SessionLocal() as session:
        keys = (
            session.query(APIKey)
            .filter(APIKey.user_id == user_id)
            .order_by(APIKey.created_at)
            .all()
        )
        for k in keys:
            session.expunge(k)
        return keys


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def require_api_key(
    authorization: Optional[str] = Header(None, alias="authorization"),
) -> APIKey:
    """
    Validates a vi_live_... Bearer token and returns the APIKey with User loaded.
    Used by programmatic API routes that accept only API keys.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Pass your API key: Authorization: Bearer vi_live_...",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header. Expected: Bearer vi_live_...",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raw_key = authorization[7:].strip()
    api_key = validate_key(raw_key)
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    record_request(api_key.id)
    return api_key


async def require_user_session(
    authorization: Optional[str] = Header(None, alias="authorization"),
) -> User:
    """
    Validates a JWT Bearer token and returns the User.
    Used by web-UI routes that require a logged-in session (not an API key).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Login required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user_by_id(user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="Account not found or deactivated")
    return user


async def require_auth(
    authorization: Optional[str] = Header(None, alias="authorization"),
) -> tuple[User, Optional[APIKey]]:
    """
    Unified auth dependency — accepts either a JWT (web UI) or an API key
    (programmatic access) and returns (User, APIKey | None).

    Decision: if the Bearer token starts with 'vi_live_' treat it as an API
    key; otherwise treat it as a JWT.  This lets the same endpoints serve
    both the web dashboard and external API consumers without duplication.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()

    if token.startswith("vi_live_"):
        # --- API key path ---
        api_key = validate_key(token)
        if not api_key:
            raise HTTPException(status_code=401, detail="Invalid or inactive API key",
                                headers={"WWW-Authenticate": "Bearer"})
        record_request(api_key.id)
        return api_key.user, api_key
    else:
        # --- JWT path ---
        user_id = decode_access_token(token)
        if not user_id:
            raise HTTPException(status_code=401,
                                detail="Invalid or expired session. Please log in again.",
                                headers={"WWW-Authenticate": "Bearer"})
        user = get_user_by_id(user_id)
        if not user or not user.is_active or user.deleted_at is not None:
            raise HTTPException(status_code=401, detail="Account not found or deactivated")
        return user, None
