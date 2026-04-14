"""
File upload router.
Accepts the E57 file, streams it to disk, then kicks off background parsing.
"""
import asyncio
import shutil
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse

from services.session_manager import session_manager
from services.e57_handler import (
    compute_file_hash,
    read_e57,
    save_npz,
    build_preview_binary,
    compute_bbox,
)

router = APIRouter()

CHUNK = 1024 * 1024  # 1 MB


async def _stream_to_disk(upload: UploadFile, dest: Path):
    async with aiofiles.open(dest, "wb") as f:
        while True:
            chunk = await upload.read(CHUNK)
            if not chunk:
                break
            await f.write(chunk)


def _parse_and_index(session_id: str):
    """Runs in a thread pool — parses E57, builds numpy arrays and preview binary."""
    from services.session_manager import session_manager as sm
    session = sm.get(session_id)
    if session is None:
        return

    try:
        session.set_status("loading", "Computing file hash…", 5)
        file_hash = compute_file_hash(session.original_e57)
        session.meta["original_file_hash"] = file_hash

        session.set_status("loading", "Reading E57 scans…", 15)
        data = read_e57(session.original_e57)

        session.meta["original_point_count"] = data["total_points"]
        session.meta["current_point_count"]  = data["total_points"]
        session.meta["scan_count"]           = data["scan_count"]
        session.meta["has_colors"]           = data["has_colors"]

        bbox = compute_bbox(data["xyz"])
        session.meta["bbox"]   = bbox
        session.meta["center"] = bbox["center"]

        session.set_status("loading", "Saving internal index…", 40)
        save_npz(data["xyz"], data["rgb"], session.original_npz)
        save_npz(data["xyz"], data["rgb"], session.current_npz)  # current = original initially

        session.set_status("loading", "Building preview…", 70)
        preview_bytes = build_preview_binary(data["xyz"], data["rgb"])
        session.preview_orig_bin.write_bytes(preview_bytes)
        session.preview_curr_bin.write_bytes(preview_bytes)

        session.set_status("ready", "File ready", 100)

    except Exception as exc:
        session.set_status("error", str(exc), 0)
        raise


@router.post("")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    if not file.filename.lower().endswith(".e57"):
        raise HTTPException(400, "Only .e57 files are supported.")

    session = session_manager.create()
    session.meta["original_filename"] = file.filename
    session.set_status("uploading", "Uploading…", 2)

    # Stream to disk
    await _stream_to_disk(file, session.original_e57)
    session.meta["original_file_size_bytes"] = session.original_e57.stat().st_size
    session.save_meta()

    # Parse in background thread
    background_tasks.add_task(
        asyncio.get_running_loop().run_in_executor,
        None,
        _parse_and_index,
        session.session_id,
    )

    return {"session_id": session.session_id}
