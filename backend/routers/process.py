"""
Processing router — noise removal, regional cleaning, and preview serving.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

from services.session_manager import session_manager
from services.e57_handler import load_npz, save_npz, build_preview_binary, compute_bbox
from services.noise_removal import (
    auto_clean,
    statistical_outlier_removal,
    radius_outlier_removal,
    color_filter_removal,
    plane_ransac_removal,
    delete_region,
    PRESETS,
)
from services.audit_logger import AuditLogger

router = APIRouter()


# ── Pydantic request models ───────────────────────────────────────────────────

class AutoCleanRequest(BaseModel):
    sor_neighbors:  int   = Field(20,       ge=5,   le=100)
    sor_std:        float = Field(2.0,      ge=0.1, le=10.0)
    ror_points:     int   = Field(10,       ge=3,   le=64)
    ror_radius:     float = Field(0.08,     ge=0.001, le=5.0)
    color_preset:   str   = Field("tape_all")
    run_color:      bool  = True
    run_plane:      bool  = True
    bbox_filter:    Optional[dict] = None

class ManualCleanRequest(BaseModel):
    algorithm:   str
    params:      dict = {}
    bbox_filter: Optional[dict] = None
    notes:       str = ""

class RegionDeleteRequest(BaseModel):
    bbox_min: list[float]
    bbox_max: list[float]
    notes:    str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session_or_404(session_id: str):
    s = session_manager.get(session_id)
    if s is None:
        raise HTTPException(404, f"Session {session_id} not found.")
    return s


def _get_audit(session) -> AuditLogger:
    return AuditLogger(session.audit_db, session.session_id)


def _commit_result(session, result, operation_type: str, region_bbox=None, notes=""):
    """Persist result to disk and update preview."""
    points_before = session.meta["current_point_count"]
    points_after  = len(result.kept_xyz)

    save_npz(result.kept_xyz, result.kept_rgb, session.current_npz)
    session.meta["current_point_count"] = points_after
    session.save_meta()

    preview = build_preview_binary(result.kept_xyz, result.kept_rgb)
    session.preview_curr_bin.write_bytes(preview)

    logger = _get_audit(session)
    entry_id = logger.log(
        result,
        operation_type=operation_type,
        points_before=points_before,
        points_after=points_after,
        region_bbox=region_bbox,
        notes=notes,
    )
    return entry_id, points_before, points_after


def _run_auto_clean(session_id: str, req: AutoCleanRequest):
    session = session_manager.get(session_id)
    if session is None:
        return
    try:
        session.set_status("processing", "Running auto-clean pipeline…", 10)
        xyz, rgb = load_npz(session.current_npz)

        results = auto_clean(
            xyz, rgb,
            bbox_filter   = req.bbox_filter,
            sor_neighbors = req.sor_neighbors,
            sor_std       = req.sor_std,
            ror_points    = req.ror_points,
            ror_radius    = req.ror_radius,
            color_preset  = req.color_preset,
            run_color     = req.run_color,
            run_plane     = req.run_plane,
        )

        n = len(results)
        for i, result in enumerate(results):
            session.set_status("processing", f"Committing stage {i+1}/{n}…", 10 + int(80 * (i + 1) / n))
            _commit_result(session, result, "auto_clean", req.bbox_filter)

        session.set_status("ready", "Auto-clean complete", 100)
    except Exception as exc:
        session.set_status("error", str(exc))
        raise


def _run_manual_clean(session_id: str, req: ManualCleanRequest):
    session = session_manager.get(session_id)
    if session is None:
        return
    try:
        session.set_status("processing", f"Running {req.algorithm}…", 10)
        xyz, rgb = load_npz(session.current_npz)

        algo = req.algorithm
        p    = req.params
        bf   = req.bbox_filter

        if algo == "statistical_outlier":
            result = statistical_outlier_removal(xyz, rgb,
                nb_neighbors=p.get("nb_neighbors", 20),
                std_ratio=p.get("std_ratio", 2.0),
                bbox_filter=bf)
        elif algo == "radius_outlier":
            result = radius_outlier_removal(xyz, rgb,
                nb_points=p.get("nb_points", 16),
                radius=p.get("radius", 0.05),
                bbox_filter=bf)
        elif algo == "color_filter":
            result = color_filter_removal(xyz, rgb,
                preset=p.get("preset", "tape_all"),
                sat_min=p.get("sat_min", 0.35),
                val_min=p.get("val_min", 0.25),
                bbox_filter=bf)
        elif algo == "plane_ransac":
            result = plane_ransac_removal(xyz, rgb,
                distance_threshold=p.get("distance_threshold", 0.02),
                max_planes=p.get("max_planes", 5),
                vertical_only=p.get("vertical_only", True),
                bbox_filter=bf)
        else:
            session.set_status("error", f"Unknown algorithm: {algo}")
            return

        _commit_result(session, result, "manual_clean", bf, req.notes)
        session.set_status("ready", "Operation complete", 100)
    except Exception as exc:
        session.set_status("error", str(exc))
        raise


def _run_region_delete(session_id: str, req: RegionDeleteRequest):
    session = session_manager.get(session_id)
    if session is None:
        return
    try:
        session.set_status("processing", "Deleting region…", 20)
        xyz, rgb = load_npz(session.current_npz)
        bbox = {"min": req.bbox_min, "max": req.bbox_max}
        result = delete_region(xyz, rgb, bbox)
        _commit_result(session, result, "region_delete", bbox, req.notes)
        session.set_status("ready", "Region deleted", 100)
    except Exception as exc:
        session.set_status("error", str(exc))
        raise


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status/{session_id}")
def get_status(session_id: str):
    s = _get_session_or_404(session_id)
    return {
        "status":          s.meta.get("status"),
        "status_message":  s.meta.get("status_message"),
        "progress":        s.meta.get("progress"),
        "original_points": s.meta.get("original_point_count"),
        "current_points":  s.meta.get("current_point_count"),
        "bbox":            s.meta.get("bbox"),
        "center":          s.meta.get("center"),
        "has_colors":      s.meta.get("has_colors"),
        "original_filename": s.meta.get("original_filename"),
        "original_hash":   s.meta.get("original_file_hash"),
        "scan_count":      s.meta.get("scan_count"),
    }


@router.get("/preview/{session_id}/original")
def preview_original(session_id: str):
    s = _get_session_or_404(session_id)
    if not s.preview_orig_bin.exists():
        raise HTTPException(404, "Original preview not yet available.")
    data = s.preview_orig_bin.read_bytes()
    return Response(content=data, media_type="application/octet-stream")


@router.get("/preview/{session_id}/current")
def preview_current(session_id: str):
    s = _get_session_or_404(session_id)
    bin_path = s.preview_curr_bin if s.preview_curr_bin.exists() else s.preview_orig_bin
    if not bin_path.exists():
        raise HTTPException(404, "Current preview not yet available.")
    data = bin_path.read_bytes()
    return Response(content=data, media_type="application/octet-stream")


@router.post("/auto/{session_id}")
async def auto_clean_endpoint(
    session_id: str,
    req: AutoCleanRequest,
    background_tasks: BackgroundTasks,
):
    s = _get_session_or_404(session_id)
    if s.meta.get("status") == "processing":
        raise HTTPException(409, "A processing job is already running.")
    if not s.is_ready:
        raise HTTPException(400, "Session is not yet ready.")

    background_tasks.add_task(
        asyncio.get_running_loop().run_in_executor, None, _run_auto_clean, session_id, req
    )
    return {"started": True}


@router.post("/manual/{session_id}")
async def manual_clean_endpoint(
    session_id: str,
    req: ManualCleanRequest,
    background_tasks: BackgroundTasks,
):
    s = _get_session_or_404(session_id)
    if s.meta.get("status") == "processing":
        raise HTTPException(409, "A processing job is already running.")
    if not s.is_ready:
        raise HTTPException(400, "Session is not yet ready.")

    background_tasks.add_task(
        asyncio.get_running_loop().run_in_executor, None, _run_manual_clean, session_id, req
    )
    return {"started": True}


@router.post("/region-delete/{session_id}")
async def region_delete_endpoint(
    session_id: str,
    req: RegionDeleteRequest,
    background_tasks: BackgroundTasks,
):
    s = _get_session_or_404(session_id)
    if s.meta.get("status") == "processing":
        raise HTTPException(409, "A processing job is already running.")
    if not s.is_ready:
        raise HTTPException(400, "Session is not yet ready.")

    background_tasks.add_task(
        asyncio.get_running_loop().run_in_executor, None, _run_region_delete, session_id, req
    )
    return {"started": True}


@router.get("/presets")
def list_presets():
    return {"presets": list(PRESETS.keys())}
