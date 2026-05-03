#!/usr/bin/env python3
"""
10_build_smooth_cdf.py — Spatially-Pooled CDF Rebuild
=======================================================
Rebuilds return period maps using spatially-pooled CDF fitting.

Instead of relying solely on per-cell fits from stage 09 (which can be
noisy at the cell level despite regional ξ pooling), this stage pools
annual maximum observations from all cells within a 150 km radius using
an exponential decay kernel: w(d) = exp(-d / 75km).

For each active cell:
  1. Gather weighted annual max observations from nearby cells
  2. Fit lognormal body (weighted L-moments) + GPD tail
  3. Compute return periods from the smoothed composite CDF
  4. Overwrite the stage 09 return period rasters with smoothed versions

This produces smooth, spatially coherent return period maps while
preserving the regional GPD ξ from stage 09.

Input
-----
  data/historical/mesh_0.05deg_corrected/ (annual max computation)
  data/analysis/cdf/cdf_parameters.npz   (regional ξ from stage 09)

Output
------
  data/analysis/cdf/rp_*yr_hail_smooth.tif (smoothed RP GeoTIFFs)
  data/analysis/cdf/p_occurrence_smooth.tif

Usage
-----
  python scripts/10_build_smooth_cdf.py
  python scripts/10_build_smooth_cdf.py --validate
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, RP_YEARS, POOL_RADIUS_KM, DECAY_KM, NODATA
    from _io import haversine_km, write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, RP_YEARS, POOL_RADIUS_KM, DECAY_KM, NODATA
    from scripts._io import haversine_km, write_geotiff
    from scripts._logging import get_logger

MESH_DIR  = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
CDF_DIR   = DATA_ROOT / "analysis" / "cdf"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "10_build_smooth_cdf.log"

# POOL_RADIUS_KM imported from _config
# DECAY_KM imported from _config
MIN_OBS        = 10
GPD_THRESH_MM  = 50.8   # 2.0 inches default
RP_YEARS = list(RP_YEARS)  # mutable copy for legacy call sites

log = get_logger("10_build_smooth_cdf", LOG_ROOT).info


def build_annual_max():
    """Build annual max array from corrected rasters."""
    import rasterio
    year_dirs = sorted(d for d in MESH_DIR.iterdir() if d.is_dir() and d.name.isdigit())
    years = [int(d.name) for d in year_dirs]
    annual_max = np.zeros((len(years), NROWS, NCOLS), dtype=np.float32)

    for yi, ydir in enumerate(year_dirs):
        for fpath in ydir.glob("mesh_????????.tif"):
            with rasterio.open(fpath) as src:
                data = src.read(1)
            np.maximum(annual_max[yi], data, out=annual_max[yi])

    log(f"  Annual max: {annual_max.shape} ({years[0]}–{years[-1]})")
    return annual_max, years

def return_period_value(rp, mu, sigma, xi_gpd, sigma_gpd, thresh, p_occ):
    from scipy import stats
    """Compute hail size at a given return period from composite CDF."""
    if p_occ <= 0:
        return 0.0
    target_p = 1.0 / rp
    cond_exceed = target_p / p_occ
    if cond_exceed >= 1.0:
        return 0.0
    cond_ne = 1.0 - cond_exceed

    p_below_u = stats.lognorm.cdf(thresh, sigma, scale=np.exp(mu))

    if cond_ne <= p_below_u:
        return float(stats.lognorm.ppf(cond_ne, sigma, scale=np.exp(mu)))
    else:
        p_gpd = (cond_ne - p_below_u) / max(1.0 - p_below_u, 1e-10)
        p_gpd = min(p_gpd, 0.9999)
        if abs(xi_gpd) < 1e-6:
            return float(thresh + sigma_gpd * (-np.log(1 - p_gpd)))
        else:
            return float(thresh + (sigma_gpd / xi_gpd) * ((1 - p_gpd)**(-xi_gpd) - 1))

def main():
    parser = argparse.ArgumentParser(description="Spatially-pooled CDF rebuild.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        errors = []
        for rp in RP_YEARS:
            p = CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif"
            if not p.exists():
                errors.append(f"Missing: {p.name}")
        if errors:
            for e in errors:
                log(f"  ✗ {e}")
            sys.exit(1)
        log("Output validation passed ✓")
        sys.exit(0)

    log(f"\n{'='*60}")
    log(f"  Spatially-Pooled CDF Rebuild — Stage 10")
    log(f"{'='*60}")
    log(f"  Pool radius: {POOL_RADIUS_KM} km, decay: {DECAY_KM} km")

    # Load regional ξ from stage 09
    cdf_params = np.load(CDF_DIR / "cdf_parameters.npz")
    region_map = cdf_params["region_map"]
    region_xi = cdf_params["region_xi"]

    # Build annual max
    log("\n[1/3] Building annual max series")
    annual_max, years = build_annual_max()
    n_years = len(years)

    # Coordinate grids
    lats = LAT_MAX - (np.arange(NROWS) + 0.5) * DX
    lons = LON_MIN + (np.arange(NCOLS) + 0.5) * DX

    # Active cells
    p_occ_raw = (annual_max > 0).sum(axis=0) / n_years
    active = p_occ_raw > 0
    active_idx = np.argwhere(active)
    n_active = len(active_idx)
    log(f"  Active cells: {n_active:,}")

    # Initialize output arrays
    rp_arrays = {rp: np.zeros((NROWS, NCOLS), dtype=np.float32) for rp in RP_YEARS}
    p_occ_smooth = np.zeros((NROWS, NCOLS), dtype=np.float32)

    # Pre-compute pool radius in cell units for fast neighbor search
    radius_cells = int(np.ceil(POOL_RADIUS_KM / (DX * 111.0))) + 1

    log(f"\n[2/3] Fitting smoothed CDFs ({n_active:,} cells)")
    t0 = time.time()
    n_fitted = 0

    for idx_i, (ri, ci) in enumerate(active_idx):
        lat0 = lats[ri]
        lon0 = lons[ci]

        # Get regional ξ for this cell
        reg = region_map[ri, ci]
        if reg >= 0 and reg < len(region_xi):
            xi_gpd = float(region_xi[reg])
        else:
            xi_gpd = 0.0

        # Gather neighbors within pool radius
        r_lo = max(0, ri - radius_cells)
        r_hi = min(NROWS, ri + radius_cells + 1)
        c_lo = max(0, ci - radius_cells)
        c_hi = min(NCOLS, ci + radius_cells + 1)

        pool_obs = []
        pool_wts = []

        for pr in range(r_lo, r_hi):
            for pc in range(c_lo, c_hi):
                if not active[pr, pc]:
                    continue
                d = haversine_km(lat0, lon0, lats[pr], lons[pc])
                if d > POOL_RADIUS_KM:
                    continue
                w = np.exp(-d / DECAY_KM)
                ann = annual_max[:, pr, pc]
                pool_obs.extend(ann.tolist())
                pool_wts.extend([w] * n_years)

        pool_obs = np.array(pool_obs, dtype=np.float32)
        pool_wts = np.array(pool_wts, dtype=np.float32)

        nz_mask = pool_obs > 0
        nz_obs = pool_obs[nz_mask]
        nz_wts = pool_wts[nz_mask]

        if len(nz_obs) < MIN_OBS:
            continue

        # Weighted lognormal fit
        total_wt = pool_wts.sum()
        p_occ_rate = float(nz_wts.sum() / total_wt) if total_wt > 0 else 0
        p_occ_smooth[ri, ci] = p_occ_rate

        log_x = np.log(nz_obs)
        w_norm = nz_wts / nz_wts.sum()
        mu_w = float(np.dot(w_norm, log_x))
        var_w = float(np.dot(w_norm, (log_x - mu_w)**2))
        sigma_w = float(np.sqrt(max(var_w, 1e-6)))

        # GPD scale from exceedances
        exc = nz_obs[nz_obs > GPD_THRESH_MM] - GPD_THRESH_MM
        if len(exc) >= 5 and xi_gpd < 1.0:
            sigma_gpd = float(exc.mean()) * (1.0 - xi_gpd)
        else:
            sigma_gpd = float(max(nz_obs.std(), 1.0))

        # Compute return period values
        for rp in RP_YEARS:
            val = return_period_value(rp, mu_w, sigma_w, xi_gpd, sigma_gpd,
                                      GPD_THRESH_MM, p_occ_rate)
            if val is not None and np.isfinite(val) and val >= 0:
                rp_arrays[rp][ri, ci] = float(np.clip(val, 0, 300))

        n_fitted += 1

        if idx_i > 0 and idx_i % 2000 == 0:
            elapsed = time.time() - t0
            rate = idx_i / elapsed
            eta = (n_active - idx_i) / rate
            log(f"    {idx_i:,}/{n_active:,} ({100*idx_i/n_active:.1f}%)  "
                f"ETA {eta/60:.0f} min")

    log(f"  Fitted {n_fitted:,} cells in {(time.time()-t0)/60:.1f} min")

    # Write outputs
    log("\n[3/3] Writing smoothed rasters")
    for rp in RP_YEARS:
        path = CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif"
        write_geotiff(rp_arrays[rp], path)
        peak = float(rp_arrays[rp].max())
        log(f"  {path.name}: peak = {peak:.1f} mm ({peak/25.4:.2f} in)")

    write_geotiff(p_occ_smooth, CDF_DIR / "p_occurrence_smooth.tif")

    log(f"\n{'='*60}")
    log(f"  Complete")
    log(f"{'='*60}\n")

if __name__ == "__main__":
    main()
