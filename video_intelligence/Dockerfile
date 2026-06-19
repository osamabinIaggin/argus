# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --silent --legacy-peer-deps

COPY web/ .

# VITE_* vars are baked into the frontend bundle at build time by Vite.
# Pass via docker-compose build args (see docker-compose.yml).
ARG VITE_GOOGLE_CLIENT_ID=""
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID

ARG VITE_POWERSYNC_URL=""
ARG VITE_FIREBASE_API_KEY=""
ARG VITE_FIREBASE_AUTH_DOMAIN=""
ARG VITE_FIREBASE_PROJECT_ID=""
ARG VITE_FIREBASE_STORAGE_BUCKET=""
ARG VITE_FIREBASE_MESSAGING_SENDER_ID=""
ARG VITE_FIREBASE_APP_ID=""
ARG VITE_FIREBASE_VAPID_KEY=""

# Write all VITE_* build args into .env.production.local so Vite bakes them
# into the bundle regardless of what .env.local says (production mode takes
# .env.[mode].local as highest priority).
RUN printf '%s\n' \
      "VITE_POWERSYNC_URL=${VITE_POWERSYNC_URL}" \
      "VITE_FIREBASE_API_KEY=${VITE_FIREBASE_API_KEY}" \
      "VITE_FIREBASE_AUTH_DOMAIN=${VITE_FIREBASE_AUTH_DOMAIN}" \
      "VITE_FIREBASE_PROJECT_ID=${VITE_FIREBASE_PROJECT_ID}" \
      "VITE_FIREBASE_STORAGE_BUCKET=${VITE_FIREBASE_STORAGE_BUCKET}" \
      "VITE_FIREBASE_MESSAGING_SENDER_ID=${VITE_FIREBASE_MESSAGING_SENDER_ID}" \
      "VITE_FIREBASE_APP_ID=${VITE_FIREBASE_APP_ID}" \
      "VITE_FIREBASE_VAPID_KEY=${VITE_FIREBASE_VAPID_KEY}" \
    > .env.production.local

RUN npm run build


# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.9-slim AS runtime

# FFmpeg — required for video preprocessing (preprocess stage calls ffmpeg binary).
# libglib2.0-0 + libgl1 — OpenCV runtime shared libraries.
# libgomp1 — OpenMP used by Ultralytics/PyTorch.
# wget — used to fetch YOLO weights at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies in a cached layer (only re-runs when requirements change).
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source.
# Splitting into separate COPY instructions maximises layer caching:
# source changes don't invalidate the pip install layer.
COPY api/      ./api/
COPY pipeline/ ./pipeline/
COPY workers/  ./workers/
COPY prod-ca-2021.crt ./prod-ca-2021.crt
# Firebase credentials — optional, only needed for push notifications.
# Accepts either a service-account JSON or an ADC user-credentials JSON
# (produced by `gcloud auth application-default login`).
# Copy whichever file you have to video_intelligence/ before building:
#   cp ~/.config/gcloud/application_default_credentials.json video_intelligence/gcloud-adc.json
# Then set in .env:  GOOGLE_APPLICATION_CREDENTIALS=/app/gcloud-adc.json
COPY firebase-service-account.json* ./
COPY gcloud-adc.json* ./

# Copy built frontend assets from stage 1.
# FastAPI serves these via StaticFiles at the end of main.py.
COPY --from=frontend-build /build/web/dist ./web/dist

# Download YOLOv8n weights (~6 MB) at build time so the image is self-contained.
# Using the same version tag as ultralytics==8.2.90 in requirements.txt.
RUN wget -q --show-progress -O /app/yolov8n.pt \
    "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"

# Create directories for persistent volumes (overridden by docker compose mounts).
RUN mkdir -p /app/output /app/data

# ── Runtime defaults ───────────────────────────────────────────────────────────
# These can all be overridden by env_file or environment in docker-compose.yml.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OUTPUT_DIR=/app/output \
    DB_SSL_CERT=/app/prod-ca-2021.crt

EXPOSE 8000

# API server — Celery worker overrides this CMD in docker-compose.yml.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
