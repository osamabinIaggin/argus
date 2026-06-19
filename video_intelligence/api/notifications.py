"""
Firebase Cloud Messaging push notification helper.

Credential resolution order (first that works wins):
  1. GOOGLE_APPLICATION_CREDENTIALS env var → service-account JSON file
  2. Application Default Credentials (ADC) — set up via:
       gcloud auth application-default login
     or by mounting ~/.config/gcloud/application_default_credentials.json
     into the container and setting GOOGLE_APPLICATION_CREDENTIALS to that path.

If no credentials are found or firebase-admin is not installed,
all calls are silently skipped so the rest of the app keeps working.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def _ensure_initialized() -> bool:
    """Initialize the Firebase Admin SDK once.  Returns True if ready."""
    global _initialized
    if _initialized:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _initialized = True
            return True

        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if cred_path and os.path.isfile(cred_path):
            # Explicit credentials file — could be a service-account JSON *or*
            # an ADC user-credentials JSON (from `gcloud auth application-default login`).
            cred = credentials.Certificate(cred_path)
        else:
            # No explicit file — fall back to Application Default Credentials.
            # Works on GCP (Cloud Run, GCE) and locally after running:
            #   gcloud auth application-default login
            logger.info("GOOGLE_APPLICATION_CREDENTIALS not set — trying Application Default Credentials")
            cred = credentials.ApplicationDefault()

        firebase_admin.initialize_app(cred)
        _initialized = True
        return True
    except ImportError:
        logger.warning("FCM disabled — firebase-admin is not installed")
        return False
    except Exception as exc:
        logger.warning("FCM init failed: %s", exc)
        return False


def send_push(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    link: str = "/jobs",
) -> None:
    """
    Send a web push notification to every FCM token in *tokens*.

    Silently skips if FCM is not configured or tokens list is empty.
    Stale/invalid tokens are logged but do not raise.
    """
    if not tokens:
        return
    if not _ensure_initialized():
        return

    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon="/favicon.svg",
                    badge="/favicon.svg",
                    require_interaction=False,
                ),
                fcm_options=messaging.WebpushFCMOptions(link=link),
            ),
        )
        response = messaging.send_each_for_multicast(message)
        logger.info(
            "FCM multicast: %d success, %d failure",
            response.success_count,
            response.failure_count,
        )
        # Log individual failures for debugging (but don't raise)
        for i, resp in enumerate(response.responses):
            if not resp.success:
                logger.debug("FCM token[%d] failed: %s", i, resp.exception)
    except Exception as exc:
        logger.warning("FCM send error: %s", exc)
