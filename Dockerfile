# ── Stage 1: Build the React frontend ─────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Application ───────────────────────────────────────────────────────
# Using plain Python slim — cupy brings its own CUDA runtime libraries in the
# wheel, so no CUDA base image is needed. GPU access is provided at runtime by
# the NVIDIA Container Toolkit when the container is started with --gpus all.
FROM python:3.11-slim-bookworm

# System libraries needed by pye57 (OpenMP), Pillow (JPEG/OpenJPEG), and scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libgomp1 \
        libjpeg62-turbo \
        libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies.
# cupy is intentionally excluded here — entrypoint.sh installs it at runtime
# only when an NVIDIA GPU is present, keeping the image small for CPU-only use.
COPY backend/requirements.txt ./
RUN grep -vE '^\s*(#|$)' requirements.txt | grep -v 'cupy' | pip install --no-cache-dir -r /dev/stdin

# Backend source
COPY backend/ ./backend/

# Pre-built frontend baked into the image (no volume mount required)
COPY --from=frontend-builder /build/dist ./frontend/dist/

# Entrypoint: GPU probe + conditional cupy install + server launch
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Defaults for Docker operation
ENV HOST=0.0.0.0 \
    OPEN_BROWSER=0 \
    FORENSICCLOUD_WORK_DIR=/data/sessions

EXPOSE 8000

# Session files live here — mount a named volume to persist across restarts
VOLUME ["/data/sessions"]

ENTRYPOINT ["/entrypoint.sh"]
