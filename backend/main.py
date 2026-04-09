"""
ForensicCloud — main FastAPI application.
Serves the React frontend as static files and mounts the API routers.
"""
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


# Serve built React app (production mode)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


def _open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    print("=" * 60)
    print("  ForensicCloud — Forensic Point Cloud Cleaning Platform")
    print(f"  Version {APP_VERSION}")
    print("  Opening at http://localhost:8000")
    print("=" * 60)

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False, log_level="warning")
