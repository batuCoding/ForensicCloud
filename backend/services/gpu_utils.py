"""
GPU/parallel acceleration utilities — probed once at import time.

Exports
-------
GPU_AVAILABLE   : bool
xp              : cupy if GPU available, else numpy
GPU_INFO        : dict
to_gpu(arr)     : move ndarray to device (no-op when no GPU)
to_cpu(arr)     : move device array to host ndarray
free_gpu_bytes(): current free VRAM in bytes (0 when no GPU)
SKLEARN_AVAILABLE : bool
CPU_COUNT       : int
"""
from __future__ import annotations

import os
import numpy as np

# ---------------------------------------------------------------------------
# GPU probe
# ---------------------------------------------------------------------------

try:
    import cupy as cp
    _dummy = cp.zeros(1)                          # trigger CUDA context init
    _dev   = cp.cuda.Device(0)
    _mem   = _dev.mem_info                        # (free_bytes, total_bytes)
    _props = cp.cuda.runtime.getDeviceProperties(0)

    GPU_AVAILABLE = True
    xp = cp
    GPU_INFO: dict = {
        "available":       True,
        "device_name":     _props["name"].decode(),
        "total_memory_mb": _mem[1] // (1024 ** 2),
        "free_memory_mb":  _mem[0] // (1024 ** 2),
        "driver_version":  cp.cuda.runtime.driverGetVersion(),
        "cuda_version":    cp.cuda.runtime.runtimeGetVersion(),
        "cupy_version":    cp.__version__,
    }
except Exception as _gpu_err:
    GPU_AVAILABLE = False
    xp = np
    GPU_INFO: dict = {"available": False, "reason": str(_gpu_err)}

# ---------------------------------------------------------------------------
# sklearn probe
# ---------------------------------------------------------------------------

try:
    from sklearn.neighbors import NearestNeighbors as _NearestNeighbors  # noqa: F401
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# ---------------------------------------------------------------------------
# CPU info
# ---------------------------------------------------------------------------

CPU_COUNT: int = os.cpu_count() or 1

# ---------------------------------------------------------------------------
# Array helpers
# ---------------------------------------------------------------------------

def to_gpu(arr: np.ndarray):
    """Upload array to GPU device. No-op (returns arr) when GPU unavailable."""
    if GPU_AVAILABLE:
        return cp.asarray(arr)
    return arr


def to_cpu(arr) -> np.ndarray:
    """Bring a device array to host. Safe to call on plain ndarrays."""
    if GPU_AVAILABLE and isinstance(arr, cp.ndarray):
        return cp.asnumpy(arr)
    return np.asarray(arr)


def free_gpu_bytes() -> int:
    """Current free VRAM in bytes, or 0 if no GPU."""
    if not GPU_AVAILABLE:
        return 0
    return cp.cuda.Device(0).mem_info[0]
