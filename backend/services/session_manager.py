import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from config import WORK_DIR


class Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.dir = WORK_DIR / session_id
        self.dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.original_e57: Path = self.dir / "original.e57"
        self.current_e57: Path = self.dir / "current.e57"
        self.original_npz: Path = self.dir / "original.npz"
        self.current_npz: Path = self.dir / "current.npz"
        self.preview_orig_bin: Path = self.dir / "preview_orig.bin"
        self.preview_curr_bin: Path = self.dir / "preview_curr.bin"
        self.audit_db: Path = self.dir / "audit.db"
        self.meta_file: Path = self.dir / "meta.json"

        self.meta: dict = {
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_filename": "",
            "original_file_size_bytes": 0,
            "original_file_hash": "",
            "original_point_count": 0,
            "current_point_count": 0,
            "scan_count": 0,
            "bbox": {"min": [0, 0, 0], "max": [0, 0, 0]},
            "center": [0, 0, 0],
            "status": "idle",
            "status_message": "",
            "progress": 0,
            "has_colors": False,
        }

    def save_meta(self):
        with open(self.meta_file, "w") as f:
            json.dump(self.meta, f, indent=2)

    def load_meta(self):
        if self.meta_file.exists():
            with open(self.meta_file, "r") as f:
                self.meta = json.load(f)

    def set_status(self, status: str, message: str = "", progress: int = 0):
        self.meta["status"] = status
        self.meta["status_message"] = message
        self.meta["progress"] = progress
        self.save_meta()

    @property
    def is_ready(self) -> bool:
        return self.original_npz.exists()

    @property
    def has_current(self) -> bool:
        return self.current_npz.exists()


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(session_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        if session_id not in self._sessions:
            session_dir = WORK_DIR / session_id
            if session_dir.exists():
                session = Session(session_id)
                session.load_meta()
                self._sessions[session_id] = session
                return session
            return None
        return self._sessions[session_id]

    def delete(self, session_id: str):
        session = self._sessions.pop(session_id, None)
        if session:
            shutil.rmtree(session.dir, ignore_errors=True)


session_manager = SessionManager()
