"""
E57 file reading, writing, and preview generation.
Uses pye57 for E57 I/O and pure numpy for downsampling — no open3d needed.
"""
import hashlib
from pathlib import Path

import numpy as np
import pye57

from config import MAX_PREVIEW_POINTS, PREVIEW_VOXEL_SIZE


# ---------------------------------------------------------------------------
# File hash
# ---------------------------------------------------------------------------

def compute_file_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# E57 → NumPy
# ---------------------------------------------------------------------------

def read_e57(file_path: Path) -> dict:
    """
    Read all scans from an E57 file.

    Returns dict with keys:
        xyz          : float64 (N, 3)
        rgb          : float32 (N, 3) values 0-1
        scan_count   : int
        total_points : int
        has_colors   : bool
    """
    e57 = pye57.E57(str(file_path))
    scan_count = e57.scan_count

    all_xyz       = []
    all_rgb       = []
    all_intensity = []
    has_colors    = False

    for i in range(scan_count):
        data = e57.read_scan(i, intensity=True, colors=True, row_column=False)

        x = np.asarray(data.get("cartesianX", []), dtype=np.float64)
        y = np.asarray(data.get("cartesianY", []), dtype=np.float64)
        z = np.asarray(data.get("cartesianZ", []), dtype=np.float64)
        if len(x) == 0:
            continue

        all_xyz.append(np.column_stack([x, y, z]))

        if "colorRed" in data and "colorGreen" in data and "colorBlue" in data:
            has_colors = True
            r = np.asarray(data["colorRed"],   dtype=np.float32) / 255.0
            g = np.asarray(data["colorGreen"], dtype=np.float32) / 255.0
            b = np.asarray(data["colorBlue"],  dtype=np.float32) / 255.0
            all_rgb.append(np.column_stack([r, g, b]))
        else:
            all_rgb.append(None)

        if "intensity" in data:
            all_intensity.append(np.asarray(data["intensity"], dtype=np.float32))
        else:
            all_intensity.append(None)

    xyz = np.vstack(all_xyz) if all_xyz else np.zeros((0, 3), dtype=np.float64)

    if has_colors and all(r is not None for r in all_rgb):
        rgb = np.vstack(all_rgb).astype(np.float32)
    else:
        # Fall back to intensity or Z-height gradient
        flat_intensity = [i for i in all_intensity if i is not None]
        if flat_intensity:
            inten = np.concatenate(flat_intensity)
            t = (inten - inten.min()) / (inten.ptp() + 1e-8)
            rgb = np.column_stack([t, t, np.ones_like(t)]).astype(np.float32)
        elif len(xyz) > 0:
            t = ((xyz[:, 2] - xyz[:, 2].min()) / (xyz[:, 2].ptp() + 1e-8)).astype(np.float32)
            rgb = np.column_stack([t, 1 - t, np.zeros(len(xyz), np.float32)])
        else:
            rgb = np.zeros((0, 3), dtype=np.float32)

    return {
        "xyz":          xyz,
        "rgb":          rgb,
        "scan_count":   scan_count,
        "total_points": len(xyz),
        "has_colors":   has_colors,
    }


# ---------------------------------------------------------------------------
# NumPy ↔ disk
# ---------------------------------------------------------------------------

def save_npz(xyz: np.ndarray, rgb: np.ndarray, path: Path):
    np.savez_compressed(str(path), xyz=xyz.astype(np.float64), rgb=rgb.astype(np.float32))


def load_npz(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.load(str(path))
    return data["xyz"], data["rgb"]


# ---------------------------------------------------------------------------
# Voxel downsampling — pure numpy
# ---------------------------------------------------------------------------

def _voxel_downsample(xyz: np.ndarray, rgb: np.ndarray, voxel_size: float):
    """Return one representative point per voxel (the first encountered)."""
    if len(xyz) == 0:
        return xyz, rgb

    vox = np.floor(xyz / voxel_size).astype(np.int64)

    # Build a structured array so np.unique can treat each row as a key
    dt = np.dtype([("x", np.int64), ("y", np.int64), ("z", np.int64)])
    keys = np.empty(len(vox), dtype=dt)
    keys["x"] = vox[:, 0]
    keys["y"] = vox[:, 1]
    keys["z"] = vox[:, 2]

    _, unique_idx = np.unique(keys, return_index=True)
    return xyz[unique_idx], rgb[unique_idx]


# ---------------------------------------------------------------------------
# Preview binary (downsampled, sent to browser)
# ---------------------------------------------------------------------------

def build_preview_binary(xyz: np.ndarray, rgb: np.ndarray) -> bytes:
    """
    Downsample and serialise as raw float32 binary.
    Format: interleaved [x,y,z,r,g,b, ...] — 6 float32 per point.
    """
    n = len(xyz)

    if n > MAX_PREVIEW_POINTS:
        xyz_d, rgb_d = _voxel_downsample(xyz, rgb, PREVIEW_VOXEL_SIZE)

        # Still too many? random subsample
        if len(xyz_d) > MAX_PREVIEW_POINTS:
            idx = np.random.choice(len(xyz_d), MAX_PREVIEW_POINTS, replace=False)
            xyz_d, rgb_d = xyz_d[idx], rgb_d[idx]
    else:
        xyz_d = xyz.astype(np.float32)
        rgb_d = rgb.astype(np.float32)

    combined = np.hstack([xyz_d.astype(np.float32), rgb_d.astype(np.float32)])
    return combined.tobytes()


def compute_bbox(xyz: np.ndarray) -> dict:
    if len(xyz) == 0:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0], "center": [0.0, 0.0, 0.0]}
    mn     = xyz.min(axis=0).tolist()
    mx     = xyz.max(axis=0).tolist()
    center = ((xyz.min(axis=0) + xyz.max(axis=0)) / 2).tolist()
    return {"min": mn, "max": mx, "center": center}


# ---------------------------------------------------------------------------
# E57 writer
# ---------------------------------------------------------------------------

def write_e57(
    xyz: np.ndarray,
    rgb: np.ndarray,
    output_path: Path,
    original_e57_path: Path,
    has_colors: bool,
):
    original = pye57.E57(str(original_e57_path))

    raw: dict = {
        "cartesianX": xyz[:, 0].astype(np.float64),
        "cartesianY": xyz[:, 1].astype(np.float64),
        "cartesianZ": xyz[:, 2].astype(np.float64),
    }

    if has_colors:
        raw["colorRed"]   = np.clip(rgb[:, 0] * 255, 0, 255).astype(np.uint8)
        raw["colorGreen"] = np.clip(rgb[:, 1] * 255, 0, 255).astype(np.uint8)
        raw["colorBlue"]  = np.clip(rgb[:, 2] * 255, 0, 255).astype(np.uint8)

    header = original.get_header(0) if original.scan_count > 0 else None
    e57_out = pye57.E57(str(output_path), mode="w")
    e57_out.write_scan_raw(raw, header=header)
    e57_out.close()
    original.close()
