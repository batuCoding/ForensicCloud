"""
Export router — write the cleaned point cloud back to E57.
"""
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.session_manager import session_manager
from services.e57_handler import load_npz, write_e57, compute_file_hash

router = APIRouter()


class ExportRequest(BaseModel):
    output_path: str = ""   # absolute path chosen by user; empty = default next to original


def _get_session_or_404(session_id: str):
    s = session_manager.get(session_id)
    if s is None:
        raise HTTPException(404, f"Session {session_id} not found.")
    return s


def _do_export(session_id: str, output_path: str):
    s = session_manager.get(session_id)
    if s is None:
        return
    try:
        s.set_status("exporting", "Writing E57…", 50)
        xyz, rgb = load_npz(s.current_npz)

        dest = Path(output_path) if output_path else s.dir / "cleaned_output.e57"
        write_e57(xyz, rgb, dest, s.original_e57, s.meta.get("has_colors", False))

        out_hash = compute_file_hash(dest)
        s.meta["exported_path"]      = str(dest)
        s.meta["exported_file_hash"] = out_hash
        s.meta["exported_point_count"] = len(xyz)
        s.set_status("ready", f"Exported to {dest.name}", 100)
    except Exception as exc:
        s.set_status("error", str(exc))
        raise


@router.post("/{session_id}")
async def export_file(
    session_id: str,
    req: ExportRequest,
    background_tasks: BackgroundTasks,
):
    s = _get_session_or_404(session_id)
    if not s.is_ready:
        raise HTTPException(400, "Session not ready.")
    if s.meta.get("status") == "processing":
        raise HTTPException(409, "A processing job is running.")

    background_tasks.add_task(
        asyncio.get_running_loop().run_in_executor, None, _do_export, session_id, req.output_path
    )
    return {"started": True}


@router.get("/{session_id}/download")
def download_exported(session_id: str):
    s = _get_session_or_404(session_id)
    exported = s.meta.get("exported_path")
    if not exported or not Path(exported).exists():
        # Fall back to generating in session dir
        default = s.dir / "cleaned_output.e57"
        if not default.exists():
            raise HTTPException(404, "No exported file found. Run the export first.")
        exported = str(default)

    return FileResponse(
        path=exported,
        media_type="application/octet-stream",
        filename=Path(exported).name,
    )


@router.get("/{session_id}/info")
def export_info(session_id: str):
    s = _get_session_or_404(session_id)
    return {
        "exported_path":        s.meta.get("exported_path"),
        "exported_file_hash":   s.meta.get("exported_file_hash"),
        "exported_point_count": s.meta.get("exported_point_count"),
    }
