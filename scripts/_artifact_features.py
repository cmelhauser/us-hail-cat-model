"""
Geometry-aware feature builder for the optional research hail-likelihood classifier.

Feature order is stable for training and inference. The historical
``ARTIFACT_FEATURE_NAMES`` name is retained for model-file compatibility.
"""

from __future__ import annotations

import math

import numpy as np

from scripts._config import NROWS, NCOLS

ARTIFACT_FEATURE_NAMES: tuple[str, ...] = (
    "mesh_mm",
    "log_mesh_mm",
    "local_median_ratio",
    "range_km",
    "azimuth_sin",
    "azimuth_cos",
    "month_sin",
    "month_cos",
    "era_gridrad",
    "era_mrms",
)


def _month_angle(day_of_year: int) -> float:
    doy = max(1, min(366, int(day_of_year)))
    return 2.0 * math.pi * ((doy - 1) / 366.0)


def local_median_3x3(data: np.ndarray) -> np.ndarray:
    from scipy.ndimage import median_filter

    return median_filter(data.astype(np.float32), size=3, mode="nearest")


def era_one_hot(source: str) -> tuple[float, float]:
    src = source.lower()
    if "gridrad" in src:
        return 1.0, 0.0
    if "mrms" in src:
        return 0.0, 1.0
    return 0.0, 0.0


def build_feature_matrix(
    mesh_mm: np.ndarray,
    *,
    range_km: np.ndarray,
    azimuth_deg: np.ndarray,
    day_of_year: int,
    source: str,
    active_mm: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build (n_active, n_features) matrix and boolean mask of active cells.

    Only cells with ``mesh_mm >= active_mm`` are included.
    """
    mesh = mesh_mm.astype(np.float32, copy=False)
    active = mesh >= active_mm
    if not np.any(active):
        return np.empty((0, len(ARTIFACT_FEATURE_NAMES)), dtype=np.float32), active

    med = local_median_3x3(mesh)
    ratio = np.ones_like(mesh, dtype=np.float32)
    pos = med > 0
    ratio[pos] = mesh[pos] / med[pos]
    ratio[~np.isfinite(ratio)] = 1.0

    ma = _month_angle(day_of_year)
    era_g, era_m = era_one_hot(source)
    az_rad = np.radians(azimuth_deg.astype(np.float32))

    rows = np.flatnonzero(active)
    feats = np.column_stack(
        [
            mesh.ravel()[rows],
            np.log1p(mesh.ravel()[rows]),
            ratio.ravel()[rows],
            range_km.ravel()[rows],
            np.sin(az_rad.ravel()[rows]),
            np.cos(az_rad.ravel()[rows]),
            np.full(rows.size, np.sin(ma), dtype=np.float32),
            np.full(rows.size, np.cos(ma), dtype=np.float32),
            np.full(rows.size, era_g, dtype=np.float32),
            np.full(rows.size, era_m, dtype=np.float32),
        ]
    ).astype(np.float32)
    return feats, active


def build_single_cell_features(
    mesh_mm: float,
    range_km_val: float,
    azimuth_deg_val: float,
    local_median_val: float,
    day_of_year: int,
    source: str,
) -> np.ndarray:
    """One-row feature vector for a single grid cell."""
    ma = _month_angle(day_of_year)
    era_g, era_m = era_one_hot(source)
    ratio = mesh_mm / local_median_val if local_median_val > 0 else 1.0
    az_rad = math.radians(float(azimuth_deg_val))
    return np.array(
        [
            mesh_mm,
            math.log1p(max(mesh_mm, 0.0)),
            ratio,
            range_km_val,
            math.sin(az_rad),
            math.cos(az_rad),
            math.sin(ma),
            math.cos(ma),
            era_g,
            era_m,
        ],
        dtype=np.float32,
    )


def apply_hail_likelihood_weights(
    mesh_mm: np.ndarray,
    hail_probabilities: np.ndarray,
    active: np.ndarray,
) -> np.ndarray:
    """Down-weight active cells by estimated hail probability."""
    out = mesh_mm.astype(np.float32, copy=True)
    rows = np.flatnonzero(active)
    if rows.size != hail_probabilities.size:
        raise ValueError("probability length does not match active cell count")
    out.ravel()[rows] *= hail_probabilities.astype(np.float32)
    return out


# Backward-compatible import for existing pickles/tests. Despite the legacy name,
# the probabilities represent likely hail (positive SPC weak labels), not artifacts.
apply_classifier_weights = apply_hail_likelihood_weights
