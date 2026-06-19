"""
API configuration — reads from environment variables or .env file.

Environment variables (all optional except GEMINI_API_KEY):
  GEMINI_API_KEY             Gemini API key (required for pipeline to run)
  REDIS_URL                  Redis connection URL (default: redis://localhost:6379/0)
  OUTPUT_DIR                 Absolute path for job output dirs (default: <project_root>/output)
  MAX_SYNC_DURATION_SECONDS  Max video duration for /v1/analyze/sync (default: 60)
  DEFAULT_FPS                Default processing FPS (default: 5)
  MAX_UPLOAD_BYTES           Max upload/download size in bytes (default: 500 MB)
"""

import os
from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SecretStr prevents the key from appearing in repr(), logs, or tracebacks.
    # Access the value with: settings.gemini_api_key.get_secret_value()
    gemini_api_key: SecretStr = SecretStr("")
    redis_url: str = "redis://localhost:6379/0"
    output_dir: str = ""
    max_sync_duration_seconds: int = 60
    default_fps: int = 5
    max_upload_bytes: int = 500 * 1024 * 1024   # 500 MB

    # JWT — MUST be overridden in production via JWT_SECRET env var.
    # Use: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret: SecretStr = SecretStr("CHANGE_ME_IN_PRODUCTION_USE_JWT_SECRET_ENV_VAR")
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30

    # Google OAuth — set GOOGLE_CLIENT_ID in .env to enable Google sign-in.
    google_client_id: str = ""
    # Required for PWA auth-code exchange flow (redirect-based sign-in).
    google_client_secret: str = ""

    # PowerSync — set both to enable real-time local-first sync on the frontend.
    # POWERSYNC_URL: from PowerSync dashboard (e.g. https://xxx.powersync.journeyapps.com)
    # POWERSYNC_JWT_SECRET: from PowerSync dashboard → Edit Instance → JWT Secret
    powersync_url: str = ""
    powersync_jwt_secret: SecretStr = SecretStr("")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Resolve output_dir to absolute path relative to project root if not set
if not settings.output_dir:
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings.output_dir = os.path.join(_project_root, "output")
