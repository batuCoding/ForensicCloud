"""
ForensicCloud — main FastAPI application.
Serves the React frontend as static files and mounts the API routers.
"""
import os
import webbrowser
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import FRONTEND_DIST, APP_VERSION
from routers import upload, process, export, audit

app = FastAPI(
    title="ForensicCloud",
    description="Forensic E57 Point Cloud Cleaning Platform",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Allow the Vite dev server during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(upload.router,  prefix="/api/upload",  tags=["upload"])
app.include_router(process.router, prefix="/api/process", tags=["process"])
app.include_router(export.router,  prefix="/api/export",  tags=["export"])
app.include_router(audit.router,   prefix="/api/audit",   tags=["audit"])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/gpu-info")
def gpu_info():
    from services.gpu_utils import GPU_INFO, GPU_AVAILABLE, SKLEARN_AVAILABLE, CPU_COUNT
    return {
        "gpu": GPU_INFO,
        "cpu_count": CPU_COUNT,
        "sklearn_available": SKLEARN_AVAILABLE,
        "acceleration": {
            "ransac":       "gpu_batched"    if GPU_AVAILABLE else ("cpu_parallel" if CPU_COUNT > 1 else "cpu_serial"),
            "sor_ror":      "gpu_brute_knn"  if GPU_AVAILABLE else ("sklearn_parallel" if SKLEARN_AVAILABLE else "scipy_kdtree"),
            "voxel":        "gpu_lexsort"    if GPU_AVAILABLE else "numpy_unique",
            "color_filter": "gpu_vectorized" if GPU_AVAILABLE else "numpy_vectorized",
        },
    }


# Serve built React app (production mode)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


def _open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))

    print("=" * 60)
    print("  ForensicCloud — Forensic Point Cloud Cleaning Platform")
    print(f"  Version {APP_VERSION}")
    print(f"  Listening on http://{host}:{port}")
    print("=" * 60)

    if os.getenv("OPEN_BROWSER", "1") != "0":
        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run("main:app", host=host, port=port, reload=False, log_level="warning")
