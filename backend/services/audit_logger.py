"""
Forensic audit logger.
Every cleaning operation is persisted to a per-session SQLite database.
The log is immutable — entries are inserted, never updated or deleted.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.noise_removal import RemovalResult


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS operations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL,
    timestamp      TEXT    NOT NULL,
    operation_type TEXT    NOT NULL,
    algorithm      TEXT    NOT NULL,
    params         TEXT    NOT NULL,
    points_before  INTEGER NOT NULL,
    points_removed INTEGER NOT NULL,
    points_after   INTEGER NOT NULL,
    removed_bbox   TEXT    NOT NULL,
    region_bbox    TEXT,
    operator_notes TEXT    DEFAULT ''
);
"""


class AuditLogger:
    def __init__(self, db_path: Path, session_id: str):
        self.db_path = db_path
        self.session_id = session_id
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(CREATE_SQL)

    def log(
        self,
        result: RemovalResult,
        operation_type: str,
        points_before: int,
        points_after: int,
        region_bbox: Optional[dict] = None,
        notes: str = "",
    ) -> int:
        row = {
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation_type": operation_type,
            "algorithm": result.algorithm,
            "params": json.dumps(result.params),
            "points_before": points_before,
            "points_removed": result.removed_count,
            "points_after": points_after,
            "removed_bbox": json.dumps(result.removed_bbox),
            "region_bbox": json.dumps(region_bbox) if region_bbox else None,
            "operator_notes": notes,
        }
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO operations
                   (session_id, timestamp, operation_type, algorithm, params,
                    points_before, points_removed, points_after,
                    removed_bbox, region_bbox, operator_notes)
                   VALUES
                   (:session_id, :timestamp, :operation_type, :algorithm, :params,
                    :points_before, :points_removed, :points_after,
                    :removed_bbox, :region_bbox, :operator_notes)""",
                row,
            )
            return cur.lastrowid

    def get_all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operations WHERE session_id=? ORDER BY id", (self.session_id,)
            ).fetchall()
        entries = []
        for row in rows:
            d = dict(row)
            d["params"] = json.loads(d["params"])
            d["removed_bbox"] = json.loads(d["removed_bbox"])
            if d["region_bbox"]:
                d["region_bbox"] = json.loads(d["region_bbox"])
            entries.append(d)
        return entries

    def add_notes(self, entry_id: int, notes: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE operations SET operator_notes=? WHERE id=? AND session_id=?",
                (notes, entry_id, self.session_id),
            )
