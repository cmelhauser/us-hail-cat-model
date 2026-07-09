"""
GridRad-native reflectivity QC for Stage 04c (Murillo et al. / Bowman & Homeyer 2017).

Implements literature-aligned ``GRIDRAD_FILTER`` (echo-frequency) and a practical
``GRIDRAD_REMOVE_CLUTTER`` analogue on dense (altitude, lat, lon) reflectivity before
SHI integration. Deterministic; no optional ML artifacts.
"""

from __future__ import annotations

import numpy as np

# GridRad v3.1 recommendation: Necho/Nobs < 0.6 when Nobs >= 3 → missing.
FILTER_MIN_ECHO_FREQ = 0.6
FILTER_MIN_NRADOBS = 3

# Clutter removal: minimum 3×3×3 neighborhood echo coverage (32%).
CLUTTER_MIN_COVERAGE = 0.32
CLUTTER_Z_THRESHOLD_DBZ = 5.0


def gridrad_filter_reflectivity(
    reflectivity: np.ndarray,
    nradobs: np.ndarray,
    nradecho: np.ndarray,
    *,
    min_freq: float = FILTER_MIN_ECHO_FREQ,
    min_nobs: int = FILTER_MIN_NRADOBS,
) -> np.ndarray:
    """
    Remove low-confidence GridRad reflectivity using Necho/Nobs echo frequency.

    ``reflectivity``, ``nradobs``, and ``nradecho`` must share shape (alt, lat, lon).
    """
    out = reflectivity.astype(np.float32, copy=True)
    nobs = nradobs.astype(np.float32)
    necho = nradecho.astype(np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        freq = necho / np.maximum(nobs, 1.0)
    low_conf = (nobs >= float(min_nobs)) & np.isfinite(freq) & (freq < min_freq)
    out[low_conf] = np.nan
    return out


def gridrad_remove_clutter(
    reflectivity: np.ndarray,
    *,
    z_threshold: float = CLUTTER_Z_THRESHOLD_DBZ,
    min_coverage: float = CLUTTER_MIN_COVERAGE,
    skip_weak_shallow_echo: bool = True,
) -> np.ndarray:
    """
  4-step GridRad clutter removal analogue on dense reflectivity.

    Steps 1 and 4: 3×3×3 neighborhood echo coverage below ``min_coverage``.
    Step 2: optional removal of weak echo confined to lowest altitude levels (off for hail).
    Step 3: remove boundary-layer echo below a mid-level anvil gap.
    """
    from scipy.ndimage import uniform_filter

    out = reflectivity.astype(np.float32, copy=True)
    echo = np.isfinite(out) & (out >= z_threshold)

    def _coverage_pass(echo_mask: np.ndarray) -> np.ndarray:
        cov = uniform_filter(echo_mask.astype(np.float32), size=3, mode="constant", cval=0.0)
        return echo_mask & (cov < min_coverage)

    remove = _coverage_pass(echo)
    if not skip_weak_shallow_echo and out.shape[0] >= 3:
        low = out[0]
        weak_shallow = np.isfinite(low) & (low >= z_threshold) & (low < 20.0)
        for k in range(1, out.shape[0]):
            weak_shallow &= ~(np.isfinite(out[k]) & (out[k] >= z_threshold))
        remove[0] |= weak_shallow

    if out.shape[0] >= 4:
        # Below-anvil: echo aloft, clear mid-layer, echo below ~4 km (lowest few levels).
        mid_k = max(1, out.shape[0] // 3)
        high_k = min(out.shape[0] - 1, (2 * out.shape[0]) // 3)
        aloft = np.any(
            np.isfinite(out[high_k:]) & (out[high_k:] >= z_threshold),
            axis=0,
        )
        mid_clear = ~np.any(
            np.isfinite(out[mid_k:high_k]) & (out[mid_k:high_k] >= z_threshold),
            axis=0,
        )
        below = np.any(
            np.isfinite(out[:mid_k]) & (out[:mid_k] >= z_threshold),
            axis=0,
        )
        below_anvil = aloft & mid_clear & below
        for k in range(mid_k):
            remove[k] |= below_anvil

    echo_after = echo & ~remove
    remove |= _coverage_pass(echo_after)
    out[remove] = np.nan
    return out


def apply_gridrad_native_qc(
    reflectivity: np.ndarray,
    nradobs: np.ndarray | None,
    nradecho: np.ndarray | None,
    *,
    skip_weak_shallow_echo: bool = True,
) -> np.ndarray:
    """Apply filter (when obs/echo present) then clutter removal."""
    out = reflectivity
    if nradobs is not None and nradecho is not None and nradobs.shape == out.shape:
        out = gridrad_filter_reflectivity(out, nradobs, nradecho)
    return gridrad_remove_clutter(out, skip_weak_shallow_echo=skip_weak_shallow_echo)
