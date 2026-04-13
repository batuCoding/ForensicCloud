#!/bin/bash
# ForensicCloud container entrypoint
# Detects NVIDIA GPU, installs CuPy if needed, then launches the server.
set -euo pipefail

echo "[ForensicCloud] Starting up..."

# ── GPU detection ──────────────────────────────────────────────────────────────
# nvidia-smi is injected by the NVIDIA Container Toolkit when the container is
# started with --gpus all (or equivalent). If it is absent or fails, no GPU
# is available and we continue in CPU-only mode.
GPU_OK=false

if command -v nvidia-smi &>/dev/null 2>&1 && nvidia-smi &>/dev/null 2>&1; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
    echo "[ForensicCloud] NVIDIA GPU detected: ${GPU_NAME}"
    GPU_OK=true
else
    echo "[ForensicCloud] No NVIDIA GPU detected — running in CPU mode."
fi

# ── CUDA / CuPy installation ───────────────────────────────────────────────────
# cupy-cuda12x ships its own CUDA runtime libraries inside the wheel, so no
# CUDA base image is required. It is installed here rather than at build time
# so that GPU-less deployments stay small (the wheel is ~200 MB).
if [ "${GPU_OK}" = true ]; then
    if python3 -c "import cupy; cupy.zeros(1)" &>/dev/null 2>&1; then
        CUPY_VER=$(python3 -c "import cupy; print(cupy.__version__)" 2>/dev/null || echo "?")
        echo "[ForensicCloud] CuPy ${CUPY_VER} already installed — GPU acceleration active."
    else
        echo "[ForensicCloud] Installing cupy-cuda12x (first-run, ~200 MB)..."
        pip3 install --no-cache-dir --quiet "cupy-cuda12x>=13.0.0"
        echo "[ForensicCloud] CuPy installed — GPU acceleration active."
    fi
fi

# ── Launch server ──────────────────────────────────────────────────────────────
exec python3 /app/backend/main.py
