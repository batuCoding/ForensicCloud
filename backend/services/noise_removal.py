"""
Noise removal algorithms — pure numpy + scipy, no open3d required.
Every function returns a RemovalResult documenting exactly what was removed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RemovalResult:
    algorithm: str
    params: dict
    kept_xyz: np.ndarray
    kept_rgb: np.ndarray
    removed_count: int
    removed_bbox: dict           # {"min":[x,y,z], "max":[x,y,z]}
    removed_sample: np.ndarray   # up to 5000 removed XYZ points for viz


def _bbox(xyz: np.ndarray) -> dict:
    if len(xyz) == 0:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
    return {"min": xyz.min(axis=0).tolist(), "max": xyz.max(axis=0).tolist()}


def _sample(xyz: np.ndarray, n: int = 5000) -> np.ndarray:
    if len(xyz) <= n:
        return xyz
    return xyz[np.random.choice(len(xyz), n, replace=False)]


def _apply_bbox_mask(xyz: np.ndarray, bbox_filter: Optional[dict]):
    """Return (in_region_mask, out_region_mask)."""
    if bbox_filter is None:
        return np.ones(len(xyz), dtype=bool), np.zeros(len(xyz), dtype=bool)
    mn = np.array(bbox_filter["min"], dtype=np.float64)
    mx = np.array(bbox_filter["max"], dtype=np.float64)
    inside = np.all((xyz >= mn) & (xyz <= mx), axis=1)
    return inside, ~inside


# ---------------------------------------------------------------------------
# Vectorised RGB → HSV (no external deps)
# ---------------------------------------------------------------------------

def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """(N,3) float32 0-1 → (N,3) where H∈[0,360], S/V∈[0,1]."""
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    cmax  = np.maximum(np.maximum(r, g), b)
    cmin  = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    h = np.zeros(len(r), dtype=np.float32)
    s = np.where(cmax > 0, delta / (cmax + 1e-9), 0.0).astype(np.float32)
    v = cmax.astype(np.float32)

    m  = delta > 0
    mr = m & (cmax == r)
    mg = m & (cmax == g)
    mb = m & (cmax == b)
    h[mr] = (60 * ((g[mr] - b[mr]) / (delta[mr] + 1e-9))) % 360
    h[mg] = 60 * ((b[mg] - r[mg]) / (delta[mg] + 1e-9) + 2)
    h[mb] = 60 * ((r[mb] - g[mb]) / (delta[mb] + 1e-9) + 4)

    return np.stack([h, s, v], axis=1)


# ---------------------------------------------------------------------------
# 1. Statistical Outlier Removal  (scipy cKDTree)
# ---------------------------------------------------------------------------

def statistical_outlier_removal(
    xyz: np.ndarray,
    rgb: np.ndarray,
    nb_neighbors: int = 20,
    std_ratio: float = 2.0,
    bbox_filter: Optional[dict] = None,
) -> RemovalResult:
    """Remove points whose mean kNN distance is > mean + std_ratio * std."""
    in_region, out_region = _apply_bbox_mask(xyz, bbox_filter)
    wx, wr = xyz[in_region], rgb[in_region]

    if len(wx) < nb_neighbors + 2:
        return RemovalResult("Statistical Outlier Removal",
                             {"nb_neighbors": nb_neighbors, "std_ratio": std_ratio},
                             xyz, rgb, 0, _bbox(np.zeros((0, 3))), np.zeros((0, 3)))

    tree  = cKDTree(wx)
    dists, _ = tree.query(wx, k=nb_neighbors + 1)  # col 0 = self (dist 0)
    mean_dists = dists[:, 1:].mean(axis=1)

    threshold  = mean_dists.mean() + std_ratio * mean_dists.std()
    keep_local = mean_dists <= threshold

    removed_xyz = wx[~keep_local]
    region_idx  = np.where(in_region)[0]

    kept_mask = np.zeros(len(xyz), dtype=bool)
    kept_mask[region_idx[keep_local]] = True
    kept_mask[out_region] = True

    return RemovalResult(
        algorithm="Statistical Outlier Removal",
        params={"nb_neighbors": nb_neighbors, "std_ratio": std_ratio},
        kept_xyz=xyz[kept_mask], kept_rgb=rgb[kept_mask],
        removed_count=int((~keep_local).sum()),
        removed_bbox=_bbox(removed_xyz),
        removed_sample=_sample(removed_xyz),
    )


# ---------------------------------------------------------------------------
# 2. Radius Outlier Removal  (scipy cKDTree)
# ---------------------------------------------------------------------------

def radius_outlier_removal(
    xyz: np.ndarray,
    rgb: np.ndarray,
    nb_points: int = 16,
    radius: float = 0.05,
    bbox_filter: Optional[dict] = None,
) -> RemovalResult:
    """Remove points that have fewer than nb_points neighbours within radius."""
    in_region, out_region = _apply_bbox_mask(xyz, bbox_filter)
    wx, wr = xyz[in_region], rgb[in_region]

    if len(wx) == 0:
        return RemovalResult("Radius Outlier Removal",
                             {"nb_points": nb_points, "radius": radius},
                             xyz, rgb, 0, _bbox(np.zeros((0, 3))), np.zeros((0, 3)))

    # Query the nb_points-th nearest neighbour distance.
    # If that distance <= radius, the point has at least nb_points neighbours within radius.
    k = min(nb_points + 1, len(wx))
    dists, _ = cKDTree(wx).query(wx, k=k)
    keep_local = dists[:, -1] <= radius   # k-th neighbour within radius

    removed_xyz = wx[~keep_local]
    region_idx  = np.where(in_region)[0]

    kept_mask = np.zeros(len(xyz), dtype=bool)
    kept_mask[region_idx[keep_local]] = True
    kept_mask[out_region] = True

    return RemovalResult(
        algorithm="Radius Outlier Removal",
        params={"nb_points": nb_points, "radius": radius},
        kept_xyz=xyz[kept_mask], kept_rgb=rgb[kept_mask],
        removed_count=int((~keep_local).sum()),
        removed_bbox=_bbox(removed_xyz),
        removed_sample=_sample(removed_xyz),
    )


# ---------------------------------------------------------------------------
# 3. Color Filter  (vectorised HSV, no deps)
# ---------------------------------------------------------------------------

PRESETS: dict[str, list[list[float]]] = {
    "tape_yellow": [[40.0, 80.0]],
    "tape_red":    [[0.0, 15.0], [345.0, 360.0]],
    "cone_orange": [[15.0, 40.0]],
    "tape_all":    [[0.0, 15.0], [40.0, 80.0], [345.0, 360.0]],
}


def color_filter_removal(
    xyz: np.ndarray,
    rgb: np.ndarray,
    preset: str = "tape_all",
    hue_ranges: Optional[list] = None,
    sat_min: float = 0.35,
    val_min: float = 0.25,
    bbox_filter: Optional[dict] = None,
) -> RemovalResult:
    ranges = hue_ranges if hue_ranges is not None else PRESETS.get(preset, PRESETS["tape_all"])

    in_region, _ = _apply_bbox_mask(xyz, bbox_filter)
    wx, wr = xyz[in_region], rgb[in_region]

    if len(wx) == 0:
        return RemovalResult("Color Filter Removal",
                             {"preset": preset, "hue_ranges": ranges, "sat_min": sat_min, "val_min": val_min},
                             xyz, rgb, 0, _bbox(np.zeros((0, 3))), np.zeros((0, 3)))

    hsv = _rgb_to_hsv(wr)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]

    match = np.zeros(len(wx), dtype=bool)
    for lo, hi in ranges:
        match |= (h >= lo) & (h <= hi)
    match &= (s >= sat_min) & (v >= val_min)

    removed_xyz = wx[match]
    region_idx  = np.where(in_region)[0]

    kept_mask = np.ones(len(xyz), dtype=bool)
    kept_mask[region_idx[match]] = False

    return RemovalResult(
        algorithm="Color Filter Removal",
        params={"preset": preset, "hue_ranges": ranges, "sat_min": sat_min, "val_min": val_min},
        kept_xyz=xyz[kept_mask], kept_rgb=rgb[kept_mask],
        removed_count=int(match.sum()),
        removed_bbox=_bbox(removed_xyz),
        removed_sample=_sample(removed_xyz),
    )


# ---------------------------------------------------------------------------
# 4. Plane RANSAC  (pure numpy — removes windows / glass walls)
# ---------------------------------------------------------------------------

def _fit_plane_ransac(
    xyz: np.ndarray,
    distance_threshold: float,
    num_iterations: int,
) -> tuple[np.ndarray, float, np.ndarray]:
    """Return (normal, d, inlier_indices) for best plane found."""
    n = len(xyz)
    best_inliers: np.ndarray = np.array([], dtype=int)
    best_normal  = np.array([0.0, 0.0, 1.0])
    best_d       = 0.0

    for _ in range(num_iterations):
        idx = np.random.choice(n, 3, replace=False)
        p0, p1, p2 = xyz[idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-9:
            continue
        normal /= norm_len
        d = -float(normal @ p0)

        dists = np.abs(xyz @ normal + d)
        inliers = np.where(dists <= distance_threshold)[0]

        if len(inliers) > len(best_inliers):
            best_inliers = inliers
            best_normal  = normal
            best_d       = d

    return best_normal, best_d, best_inliers


def plane_ransac_removal(
    xyz: np.ndarray,
    rgb: np.ndarray,
    distance_threshold: float = 0.02,
    num_iterations: int = 500,
    min_plane_points: int = 500,
    max_planes: int = 5,
    vertical_only: bool = True,
    bbox_filter: Optional[dict] = None,
) -> RemovalResult:
    """Iteratively detect and remove large planar surfaces (windows, glass)."""
    in_region, out_region = _apply_bbox_mask(xyz, bbox_filter)
    wx = xyz[in_region]
    region_idx = np.where(in_region)[0]

    if len(wx) < min_plane_points:
        return RemovalResult(
            "Planar Surface Removal (RANSAC)",
            {"distance_threshold": distance_threshold, "max_planes": max_planes, "vertical_only": vertical_only},
            xyz, rgb, 0, _bbox(np.zeros((0, 3))), np.zeros((0, 3)))

    keep_local = np.ones(len(wx), dtype=bool)

    for _ in range(max_planes):
        remaining = np.where(keep_local)[0]
        if len(remaining) < min_plane_points:
            break

        normal, d, local_inliers = _fit_plane_ransac(
            wx[remaining], distance_threshold, num_iterations)

        if len(local_inliers) < min_plane_points:
            break

        if vertical_only:
            # Vertical wall → normal is horizontal → |normal[2]| ≈ 0
            if abs(normal[2]) > 0.4:
                continue

        global_removed = remaining[local_inliers]
        keep_local[global_removed] = False

    removed_xyz = wx[~keep_local]
    kept_mask   = np.ones(len(xyz), dtype=bool)
    kept_mask[region_idx[~keep_local]] = False

    return RemovalResult(
        algorithm="Planar Surface Removal (RANSAC)",
        params={"distance_threshold": distance_threshold, "max_planes": max_planes,
                "vertical_only": vertical_only, "min_plane_points": min_plane_points},
        kept_xyz=xyz[kept_mask], kept_rgb=rgb[kept_mask],
        removed_count=int((~keep_local).sum()),
        removed_bbox=_bbox(removed_xyz),
        removed_sample=_sample(removed_xyz),
    )


# ---------------------------------------------------------------------------
# 5. Delete selected region entirely
# ---------------------------------------------------------------------------

def delete_region(
    xyz: np.ndarray,
    rgb: np.ndarray,
    bbox_filter: dict,
) -> RemovalResult:
    in_region, out_region = _apply_bbox_mask(xyz, bbox_filter)
    removed_xyz = xyz[in_region]
    return RemovalResult(
        algorithm="Manual Region Deletion",
        params={"bbox_min": bbox_filter["min"], "bbox_max": bbox_filter["max"]},
        kept_xyz=xyz[out_region], kept_rgb=rgb[out_region],
        removed_count=int(in_region.sum()),
        removed_bbox=_bbox(removed_xyz),
        removed_sample=_sample(removed_xyz),
    )


# ---------------------------------------------------------------------------
# 6. Auto-clean pipeline
# ---------------------------------------------------------------------------

def auto_clean(
    xyz: np.ndarray,
    rgb: np.ndarray,
    bbox_filter: Optional[dict] = None,
    sor_neighbors: int = 20,
    sor_std: float = 2.0,
    ror_points: int = 10,
    ror_radius: float = 0.08,
    color_preset: str = "tape_all",
    run_color: bool = True,
    run_plane: bool = True,
) -> list[RemovalResult]:
    results: list[RemovalResult] = []
    cx, cr = xyz, rgb

    r = statistical_outlier_removal(cx, cr, sor_neighbors, sor_std, bbox_filter)
    results.append(r); cx, cr = r.kept_xyz, r.kept_rgb

    if run_color and len(cx) > 0:
        r = color_filter_removal(cx, cr, preset=color_preset, bbox_filter=bbox_filter)
        results.append(r); cx, cr = r.kept_xyz, r.kept_rgb

    if run_plane and len(cx) > 0:
        r = plane_ransac_removal(cx, cr, bbox_filter=bbox_filter)
        results.append(r); cx, cr = r.kept_xyz, r.kept_rgb

    if len(cx) > 0:
        r = radius_outlier_removal(cx, cr, ror_points, ror_radius, bbox_filter)
        results.append(r)

    return results
