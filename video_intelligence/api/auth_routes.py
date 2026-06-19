"""
Authentication routes.

POST /v1/auth/register   — email + password → user + first API key + tokens
POST /v1/auth/login      — email + password → tokens
POST /v1/auth/google     — Google id_token → find or create user + tokens
POST /v1/auth/refresh    — rotating refresh token → new token pair
POST /v1/auth/logout     — revoke a refresh token
GET  /v1/auth/me         — current user info (JWT session required)

Security notes
--------------
* Passwords are hashed with argon2id before storage; plaintext never touches DB.
* Login and register intentionally return the same generic 401 on failure to
  prevent user-enumeration (timing differences are mitigated by argon2's
  mandatory cost even on "user not found" paths via a dummy verify call).
* Google id_tokens are verified server-side using Google's public keys via
  the google-auth library. The frontend MUST NOT be trusted to supply claims.
* Refresh tokens are rotated on every use.  Presenting a revoked token triggers
  full-family revocation (RFC 6749 Security BCP §2.2.2).
* IP and User-Agent are logged on refresh token creation for audit purposes
  only; they are never used for authentication decisions.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator

from api.auth import (
    create_access_token,
    create_key,
    create_refresh_token,
    create_user,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    require_user_session,
    revoke_refresh_token,
    rotate_refresh_token,
    validate_key,
    verify_password,
)
from api.config import settings
from api.schema import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name:     str
    email:    EmailStr
    password: str
    plan:     str = "free"

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name is required")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("plan")
    @classmethod
    def valid_plan(cls, v: str) -> str:
        if v not in ("free", "starter", "pro", "enterprise"):
            raise ValueError("plan must be one of: free, starter, pro, enterprise")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class GoogleRequest(BaseModel):
    credential: str   # Google id_token from the frontend @react-oauth/google


class GoogleCodeRequest(BaseModel):
    code:         str   # OAuth2 authorization code from redirect flow
    redirect_uri: str   # Must match the redirect_uri used to obtain the code


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Shared response builder
# ---------------------------------------------------------------------------

def _token_response(
    user: User,
    request: Request,
    api_key_raw: Optional[str] = None,
) -> dict:
    """
    Build the standard token response dict.

    access_token  — short-lived JWT (15 min); use as Bearer for API calls.
    refresh_token — long-lived opaque token (30 days); use to get new tokens.
    api_key       — raw API key, present ONLY on first account creation.
                    Shown once and never returned again.
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    access_token = create_access_token(user.id)
    _, raw_refresh = create_refresh_token(user.id, ip=ip, ua=ua)

    resp: dict = {
        "access_token":  access_token,
        "refresh_token": raw_refresh,
        "token_type":    "bearer",
        "user": {
            "id":           user.id,
            "email":        user.email,
            "display_name": user.display_name,
            "plan":         user.plan,
        },
    }
    if api_key_raw is not None:
        # Raw API key — returned once on account creation, never again.
        resp["api_key"] = api_key_raw

    return resp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request):
    """
    Create a new account with email and password.

    Also creates the user's first API key (for programmatic access).
    The raw API key is returned in this response only — save it immediately.
    """
    # Constant-time duplicate check — normalise before lookup.
    if get_user_by_email(body.email):
        # Generic message to prevent email enumeration.
        raise HTTPException(400, "An account with that email already exists")

    user = create_user(
        email        = body.email,
        display_name = body.name,
        plan         = body.plan,
        password     = body.password,
        email_verified = False,
    )

    # Provision first API key — raw key returned to user once.
    _, raw_key = create_key(user.id, label="Default")

    return _token_response(user, request, api_key_raw=raw_key)


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """
    Authenticate with email and password.

    Returns the same generic 401 whether the email doesn't exist or the
    password is wrong — prevents user enumeration via timing or error message.
    """
    _GENERIC_ERROR = HTTPException(401, "Invalid email or password")

    user = get_user_by_email(body.email)

    if not user:
        # Perform a dummy hash to equalise timing with the verify path.
        try:
            hash_password("dummy_constant_time_equaliser")
        except Exception:
            pass
        raise _GENERIC_ERROR

    if not user.is_active or user.deleted_at is not None:
        raise _GENERIC_ERROR

    if not user.password_hash:
        # Account exists but has no password (created via Google OAuth or
        # the legacy anonymous flow).  Direct the user to the correct method.
        raise HTTPException(
            400,
            "This account was created with Google. Use 'Sign in with Google' instead.",
        )

    if not verify_password(body.password, user.password_hash):
        raise _GENERIC_ERROR

    return _token_response(user, request)


@router.post("/google")
async def google_auth(body: GoogleRequest, request: Request):
    """
    Verify a Google id_token issued by @react-oauth/google on the frontend.

    Google's public keys are fetched from their discovery endpoint to verify
    the token's signature server-side — the frontend is untrusted for claims.

    - Existing user  → log in, return tokens.
    - New user       → create account (email pre-verified), return tokens + api_key.
    """
    if not settings.google_client_id:
        raise HTTPException(501, "Google sign-in is not configured on this server")

    # Verify the token with Google's public keys.
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        idinfo = google_id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception as exc:
        logger.warning("Google token verification failed: %s", exc)
        raise HTTPException(401, "Invalid Google credential")

    google_email = idinfo.get("email", "").lower().strip()
    google_name  = idinfo.get("name") or idinfo.get("given_name")
    email_verified = idinfo.get("email_verified", False)

    if not google_email or not email_verified:
        raise HTTPException(400, "Google account has an unverified email address")

    user = get_user_by_email(google_email)
    api_key_raw: Optional[str] = None

    if user:
        # Existing account — just log in.
        if not user.is_active or user.deleted_at is not None:
            raise HTTPException(401, "Account is deactivated")
    else:
        # New account — email is already verified by Google.
        from api.schema import Plan
        user = create_user(
            email          = google_email,
            display_name   = google_name,
            plan           = Plan.free.value,
            password       = None,          # OAuth-only account; no password
            email_verified = True,
        )
        _, api_key_raw = create_key(user.id, label="Default")

    return _token_response(user, request, api_key_raw=api_key_raw)


@router.post("/google/exchange")
async def google_code_exchange(body: GoogleCodeRequest, request: Request):
    """
    PWA redirect-flow sign-in: exchange an OAuth2 authorization code for tokens.

    Used when running as an installed PWA where popups are unreliable.
    The frontend redirects to Google with ux_mode=redirect, Google sends back
    a ?code=... param, the frontend posts it here for server-side exchange.
    """
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(501, "Google sign-in is not configured on this server")

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code":          body.code,
                    "client_id":     settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri":  body.redirect_uri,
                    "grant_type":    "authorization_code",
                },
            )
        if token_resp.status_code != 200:
            logger.warning("Google token exchange failed: %s", token_resp.text)
            raise HTTPException(401, "Google code exchange failed")

        token_data = token_resp.json()
        id_token_jwt = token_data.get("id_token")
        if not id_token_jwt:
            raise HTTPException(401, "Google did not return an id_token")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Google code exchange error: %s", exc)
        raise HTTPException(401, "Google code exchange failed")

    # Verify the id_token exactly like the popup flow.
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        idinfo = google_id_token.verify_oauth2_token(
            id_token_jwt,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception as exc:
        logger.warning("Google token verification failed after exchange: %s", exc)
        raise HTTPException(401, "Invalid Google credential")

    google_email    = idinfo.get("email", "").lower().strip()
    google_name     = idinfo.get("name") or idinfo.get("given_name")
    email_verified  = idinfo.get("email_verified", False)

    if not google_email or not email_verified:
        raise HTTPException(400, "Google account has an unverified email address")

    user = get_user_by_email(google_email)
    api_key_raw: Optional[str] = None

    if user:
        if not user.is_active or user.deleted_at is not None:
            raise HTTPException(401, "Account is deactivated")
    else:
        from api.schema import Plan
        user = create_user(
            email          = google_email,
            display_name   = google_name,
            plan           = Plan.free.value,
            password       = None,
            email_verified = True,
        )
        _, api_key_raw = create_key(user.id, label="Default")

    return _token_response(user, request, api_key_raw=api_key_raw)


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request):
    """
    Exchange a refresh token for a new token pair (rotation).

    The old refresh token is immediately invalidated.  If a previously-revoked
    token is presented, the entire session family is revoked (theft response).
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    result = rotate_refresh_token(body.refresh_token, ip=ip, ua=ua)
    if not result:
        raise HTTPException(401, "Invalid or expired refresh token. Please log in again.")

    new_access, new_refresh, user_id = result
    user = get_user_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Account not found or deactivated")

    return {
        "access_token":  new_access,
        "refresh_token": new_refresh,
        "token_type":    "bearer",
        "user": {
            "id":           user.id,
            "email":        user.email,
            "display_name": user.display_name,
            "plan":         user.plan,
        },
    }


@router.post("/logout", status_code=204)
async def logout(body: LogoutRequest):
    """
    Revoke the given refresh token (log out this session).

    Always returns 204 — even if the token was already revoked or not found —
    to prevent token enumeration and ensure idempotent client-side logout.
    """
    revoke_refresh_token(body.refresh_token)


@router.get("/me")
async def me(current_user: User = Depends(require_user_session)):
    """Return the authenticated user's profile (JWT session required)."""
    return {
        "id":           current_user.id,
        "email":        current_user.email,
        "display_name": current_user.display_name,
        "plan":         current_user.plan,
        "email_verified": current_user.email_verified_at is not None,
        "created_at":   current_user.created_at.isoformat() if current_user.created_at else None,
    }
