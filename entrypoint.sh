#!/bin/bash
# ForensicCloud container entrypoint
# Detects NVIDIA GPU, installs CuPy if needed, then launches the server.
set -euo pipefail

echo "[ForensicCloud] Starting up..."

# nvidia-smi is injected by the NVIDIA Container Toolkit when the container is
# started with --gpus all. If absent or failing, no GPU is available.
GPU_OK=false
if nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
    echo "[ForensicCloud] NVIDIA GPU detected: ${GPU_NAME}"
    GPU_OK=true
else
    echo "[ForensicCloud] No NVIDIA GPU detected — running in CPU mode."
fi

# cupy-cuda12x ships its own CUDA runtime libraries inside the wheel, so no
# CUDA base image is required. Installed here (not at build time) so GPU-less
# deployments stay small (~200 MB saved).
if [ "${GPU_OK}" = true ]; then
    if CUPY_VER=$(python3 -c "import cupy; print(cupy.__version__)" 2>/dev/null); then
        echo "[ForensicCloud] CuPy ${CUPY_VER} already installed — GPU acceleration active."
    else
        echo "[ForensicCloud] Installing cupy-cuda12x (first-run, ~200 MB)..."
        pip3 install --no-cache-dir --quiet "cupy-cuda12x>=13.0.0"
        echo "[ForensicCloud] CuPy installed — GPU acceleration active."
    fi
fi

exec python3 /app/backend/main.py
