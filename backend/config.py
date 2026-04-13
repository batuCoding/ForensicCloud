import os
import tempfile
from pathlib import Path

# Working directory for session scratch files
WORK_DIR = Path(os.getenv("FORENSICCLOUD_WORK_DIR", tempfile.gettempdir())) / "forensiccloud_sessions"
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Static frontend build (relative to this file)
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

# Max points sent to the browser for visualization (downsampled)
MAX_PREVIEW_POINTS = 2_000_000

# Voxel size used when downsampling the preview (metres)
PREVIEW_VOXEL_SIZE = 0.02

APP_VERSION = "1.0.0"

# Server binding — override via env vars for Docker / remote deployments
HOST = os.getenv("HOST", "127.0.0.1")
try:
    PORT = int(os.getenv("PORT", "8000"))
except ValueError:
    PORT = 8000
OPEN_BROWSER = os.getenv("OPEN_BROWSER", "1") not in ("0", "false", "no")
