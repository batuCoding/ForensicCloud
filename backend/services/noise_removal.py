"""
Noise removal algorithms — numpy + scipy with optional GPU/parallel acceleration.
Every function returns a RemovalResult documenting exactly what was removed.

Acceleration tiers (auto-selected at runtime):
  GPU    : CuPy required (cupy-cuda12x) — 20-100x speedup for RANSAC/KDTree
  CPU ‖  : scikit-learn n_jobs=-1 for KNN; ProcessPoolExecutor for RANSAC
  Serial : scipy cKDTree fallback — original behaviour, always available
"""
from __future__ import annotations

import concurrent.futures
import multiprocessing
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree

from services.gpu_utils import (
    CPU_COUNT,
    GPU_AVAILABLE,
    SKLEARN_AVAILABLE,
    free_gpu_bytes,
    to_cpu,
    to_gpu,
    xp,
)


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
# Vectorised RGB → HSV (GPU-accelerated for large arrays)
# ---------------------------------------------------------------------------

def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """(N,3) float32 0-1 → (N,3) where H∈[0,360], S/V∈[0,1]."""
    if GPU_AVAILABLE and len(rgb) > 500_000:
        g = to_gpu(rgb.astype(np.float32))
        r_, g_, b_ = g[:, 0], g[:, 1], g[:, 2]
        cmax  = xp.maximum(xp.maximum(r_, g_), b_)
        cmin  = xp.minimum(xp.minimum(r_, g_), b_)
        delta = cmax - cmin
        h = xp.zeros(len(r_), dtype=xp.float32)
        s = xp.where(cmax > 0, delta / (cmax + 1e-9), 0.0).astype(xp.float32)
        v = cmax.astype(xp.float32)
        m  = delta > 0
        mr = m & (cmax == r_); mg = m & (cmax == g_); mb = m & (cmax == b_)
        h[mr] = (60 * ((g_[mr] - b_[mr]) / (delta[mr] + 1e-9))) % 360
        h[mg] = 60 * ((b_[mg] - r_[mg]) / (delta[mg] + 1e-9) + 2)
        h[mb] = 60 * ((r_[mb] - g_[mb]) / (delta[mb] + 1e-9) + 4)
        return to_cpu(xp.stack([h, s, v], axis=1))

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
# KNN distances helper  (three-tier: GPU → sklearn → scipy)
# ---------------------------------------------------------------------------

def _knn_distances(wx: np.ndarray, k: int) -> np.ndarray:
    """
    Return squared Euclidean distances to k nearest neighbours, shape (N, k).
    Column 0 is the point itself (distance ≈ 0) — callers must skip it.

    Tier 1 — GPU brute-force (CuPy, fastest for N < 5 M)
    Tier 2 — sklearn NearestNeighbors with n_jobs=-1 (multi-core CPU)
    Tier 3 — scipy cKDTree (single-threaded fallback, always available)
    """
    N = len(wx)

    # ── Tier 1: GPU ──────────────────────────────────────────────────────────
    if GPU_AVAILABLE and N < 5_000_000:
        pts  = to_gpu(wx.astype(np.float32))
        free = free_gpu_bytes()
        # each row of the distance matrix is N float32 = N*4 bytes
        # diff(batch,N,3) + d2(batch,N) = 4 floats per cell; size both correctly
        batch = max(1, min(512, int(free * 0.7 / (N * 4 * 4))))
        out   = xp.empty((N, k), dtype=xp.float32)
        for s in range(0, N, batch):
            e    = min(s + batch, N)
            diff = pts[s:e, None, :] - pts[None, :, :]
            d2   = (diff * diff).sum(axis=2)
            pi   = xp.argpartition(d2, kth=k - 1, axis=1)[:, :k]
            pd   = xp.take_along_axis(d2, pi, axis=1)
            so   = xp.argsort(pd, axis=1)
            out[s:e] = xp.take_along_axis(pd, so, axis=1)
        return to_cpu(out)

    # ── Tier 2: sklearn multi-core ───────────────────────────────────────────
    if SKLEARN_AVAILABLE:
        from sklearn.neighbors import NearestNeighbors
        nn = NearestNeighbors(n_neighbors=k, algorithm="ball_tree", n_jobs=-1)
        nn.fit(wx)
        dists, _ = nn.kneighbors(wx)
        return (dists ** 2).astype(np.float32)

    # ── Tier 3: scipy fallback ───────────────────────────────────────────────
    dists, _ = cKDTree(wx).query(wx, k=k)
    return (dists ** 2).astype(np.float32)


# ---------------------------------------------------------------------------
# 1. Statistical Outlier Removal
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
    wx = xyz[in_region]

    if len(wx) < nb_neighbors + 2:
        return RemovalResult("Statistical Outlier Removal",
                             {"nb_neighbors": nb_neighbors, "std_ratio": std_ratio},
                             xyz, rgb, 0, _bbox(np.zeros((0, 3))), np.zeros((0, 3)))

    dists_sq   = _knn_distances(wx, nb_neighbors + 1)
    mean_dists = np.sqrt(dists_sq[:, 1:]).mean(axis=1)

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
# 2. Radius Outlier Removal
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
    wx = xyz[in_region]

    if len(wx) == 0:
        return RemovalResult("Radius Outlier Removal",
                             {"nb_points": nb_points, "radius": radius},
                             xyz, rgb, 0, _bbox(np.zeros((0, 3))), np.zeros((0, 3)))

    k = min(nb_points + 1, len(wx))
    dists_sq   = _knn_distances(wx, k)
    keep_local = np.sqrt(dists_sq[:, -1]) <= radius      # k-th neighbour within radius

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
# 3. Color Filter  (vectorised HSV, GPU-accelerated for large arrays)
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
# 4. Plane RANSAC  (GPU-batched / CPU-parallel / serial)
# ---------------------------------------------------------------------------

# ── Module-level worker — must be top-level for Windows spawn pickling ──────

def _ransac_worker(args: tuple) -> tuple:
    """
    ProcessPoolExecutor worker. Runs a subset of RANSAC iterations and returns
    the best plane found as (normal_list, d_float, inlier_count).
    Returns inlier COUNT (not indices) to minimise IPC data transfer.
    The main process recomputes inlier indices from the winning normal.
    """
    import numpy as _np  # local import — each spawned process reimports
    xyz_bytes, shape, dtype_str, dist_thresh, n_iters, seed = args
    _np.random.seed(seed)
    xyz = _np.frombuffer(xyz_bytes, dtype=_np.dtype(dtype_str)).reshape(shape)
    n   = len(xyz)

    best_count  = 0
    best_normal = _np.array([0.0, 0.0, 1.0])
    best_d      = 0.0

    for _ in range(n_iters):
        idx = _np.random.choice(n, 3, replace=False)
        p0, p1, p2 = xyz[idx]
        normal = _np.cross(p1 - p0, p2 - p0)
        nl = _np.linalg.norm(normal)
        if nl < 1e-9:
            continue
        normal /= nl
        d     = -float(normal @ p0)
        count = int((_np.abs(xyz @ normal + d) <= dist_thresh).sum())
        if count > best_count:
            best_count  = count
            best_normal = normal.copy()
            best_d      = d

    return (best_normal.tolist(), best_d, best_count)


# ── GPU RANSAC ───────────────────────────────────────────────────────────────

def _fit_plane_ransac_gpu(
    xyz: np.ndarray,
    dist_thresh: float,
    n_iters: int,
) -> tuple[np.ndarray, float, np.ndarray]:
    """
    Batched GPU RANSAC.
    Processes iterations in chunks sized to available VRAM so we never
    materialise more than ~70 % of free memory at once.
    """
    N       = len(xyz)
    xyz_gpu = to_gpu(xyz.astype(np.float32))

    free  = free_gpu_bytes()
    batch = max(1, min(50, int(free * 0.7 / (N * 4))))

    best_count  = 0
    best_normal = np.array([0.0, 0.0, 1.0])
    best_d      = 0.0
    best_mask_gpu = None   # boolean mask kept on GPU; transferred once after loop

    i = 0
    while i < n_iters:
        cur = min(batch, n_iters - i)

        idx       = np.random.randint(0, N, (cur, 3))
        pts_batch = to_gpu(xyz[idx].astype(np.float32))   # (cur, 3, 3) — one transfer
        p0, p1, p2 = pts_batch[:, 0, :], pts_batch[:, 1, :], pts_batch[:, 2, :]

        normals = xp.cross(p1 - p0, p2 - p0)
        nlen    = xp.linalg.norm(normals, axis=1, keepdims=True)
        valid   = to_cpu(nlen[:, 0] > 1e-9)
        normals = normals / (nlen + 1e-12)
        d_vals  = -xp.sum(normals * p0, axis=1)

        dist_mat   = xp.abs(xyz_gpu @ normals.T + d_vals[None, :])
        counts_gpu = (dist_mat <= dist_thresh).sum(axis=0)
        counts_cpu = to_cpu(counts_gpu)
        counts_cpu[~valid] = 0

        bi = int(np.argmax(counts_cpu))
        if counts_cpu[bi] > best_count:
            best_count    = counts_cpu[bi]
            best_normal   = to_cpu(normals[bi])
            best_d        = float(to_cpu(d_vals[bi]))
            best_mask_gpu = dist_mat[:, bi] <= dist_thresh   # stay on GPU

        i += cur

    best_inliers = (
        np.where(to_cpu(best_mask_gpu))[0]
        if best_mask_gpu is not None
        else np.array([], dtype=int)
    )
    return best_normal, best_d, best_inliers


# ── CPU-parallel RANSAC ──────────────────────────────────────────────────────

def _fit_plane_ransac_cpu_parallel(
    xyz: np.ndarray,
    dist_thresh: float,
    n_iters: int,
) -> tuple[np.ndarray, float, np.ndarray]:
    """
    Distribute RANSAC iterations across ProcessPoolExecutor workers (spawn).
    Each worker runs a subset and returns its best plane.
    Main process picks the global winner, then recomputes inlier indices.
    """
    n_workers  = min(CPU_COUNT, n_iters, 16)
    base_iters = n_iters // n_workers
    extra      = n_iters % n_workers

    xyz_f32   = xyz.astype(np.float32)
    raw       = xyz_f32.tobytes()          # serialise once for all workers
    shape     = xyz_f32.shape
    dtype_str = str(xyz_f32.dtype)

    rng   = np.random.default_rng()
    tasks = [
        (raw, shape, dtype_str, dist_thresh,
         base_iters + (1 if i < extra else 0),
         int(rng.integers(0, 2 ** 31)))
        for i in range(n_workers)
    ]

    ctx = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=n_workers, mp_context=ctx
    ) as pool:
        futures = [pool.submit(_ransac_worker, t) for t in tasks]
        results = [f.result() for f in futures]

    best_count  = 0
    best_normal = np.array([0.0, 0.0, 1.0])
    best_d      = 0.0
    for normal_list, d, cnt in results:
        if cnt > best_count:
            best_count  = cnt
            best_normal = np.array(normal_list)
            best_d      = d

    # Recompute inliers from winning plane (cheap single-pass on CPU)
    dists = np.abs(xyz @ best_normal + best_d)
    return best_normal, best_d, np.where(dists <= dist_thresh)[0]


# ── Serial RANSAC (original algorithm, always-available fallback) ────────────

def _fit_plane_ransac_serial(
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

        dists   = np.abs(xyz @ normal + d)
        inliers = np.where(dists <= distance_threshold)[0]

        if len(inliers) > len(best_inliers):
            best_inliers = inliers
            best_normal  = normal
            best_d       = d

    return best_normal, best_d, best_inliers


# ── Dispatch: selects the best available implementation ──────────────────────

def _fit_plane_ransac(
    xyz: np.ndarray,
    distance_threshold: float,
    num_iterations: int,
) -> tuple[np.ndarray, float, np.ndarray]:
    """Route to GPU / CPU-parallel / serial based on available hardware."""
    N = len(xyz)
    if GPU_AVAILABLE:
        return _fit_plane_ransac_gpu(xyz, distance_threshold, num_iterations)
    if CPU_COUNT > 1 and N > 50_000:
        return _fit_plane_ransac_cpu_parallel(xyz, distance_threshold, num_iterations)
    return _fit_plane_ransac_serial(xyz, distance_threshold, num_iterations)


# ── Public RANSAC removal function (unchanged API) ───────────────────────────

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
