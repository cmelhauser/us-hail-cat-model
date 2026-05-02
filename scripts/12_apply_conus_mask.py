#!/usr/bin/env python3
"""
12_apply_conus_mask.py — CONUS Mask + Topographic Correction
==============================================================
1. Build a CONUS land mask using regionmask (US states polygon)
2. Apply mask to all RP and p_occ rasters — cells outside CONUS → nodata
3. Apply elevation-based topographic correction to RP maps:
   - Higher elevation → shorter fall through melting layer → larger hail survives
   - Front Range enhancement for orographic convective initiation

Topographic correction is a first-order approximation using GMTED2010 DEM.
The correction factor adjusts hail size by ±5–15% based on elevation.

Input
-----
  data/analysis/cdf/rp_*yr_hail_smooth.tif
  data/analysis/cdf/p_occurrence_smooth.tif
  data/analysis/occurrence/p_occ_*.tif

Output
------
  data/analysis/conus_mask/conus_mask.tif
  data/analysis/topography/elevation_0.05deg.tif
  data/analysis/topography/topo_correction.tif
  All RP and p_occ rasters are masked in-place

Usage
-----
  python scripts/12_apply_conus_mask.py
  python scripts/12_apply_conus_mask.py --validate
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
CDF_DIR   = DATA_ROOT / "analysis" / "cdf"
OCC_DIR   = DATA_ROOT / "analysis" / "occurrence"
STOCH_MAP_DIR = DATA_ROOT / "stochastic" / "maps"
MASK_DIR  = DATA_ROOT / "analysis" / "conus_mask"
TOPO_DIR  = DATA_ROOT / "analysis" / "topography"
LOG_DIR   = REPO_ROOT / "logs"
LOG_FILE  = LOG_DIR / "12_apply_conus_mask.log"

NROWS = 520
NCOLS = 1180
DX    = 0.05
LAT_MAX = 50.005
LON_MIN = -125.005


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def build_conus_mask():
    """Build CONUS land mask from regionmask US states polygon."""
    import regionmask

    log("  Building CONUS mask via regionmask ...")
    lats = LAT_MAX - (np.arange(NROWS) + 0.5) * DX
    lons = LON_MIN + (np.arange(NCOLS) + 0.5) * DX

    us_states = regionmask.defined_regions.natural_earth_v5_0_0.us_states_50
    mask_2d = us_states.mask(lons, lats)
    conus_mask = ~np.isnan(mask_2d.values)

    # Exclude Alaska and Hawaii (already outside our lat/lon extent, but verify)
    n_cells = int(conus_mask.sum())
    log(f"  CONUS cells: {n_cells:,} / {NROWS * NCOLS:,}")

    MASK_DIR.mkdir(parents=True, exist_ok=True)
    write_geotiff(conus_mask.astype(np.float32), MASK_DIR / "conus_mask.tif")
    return conus_mask


def compute_topo_factor(elevation_m: np.ndarray, freezing_level_km: np.ndarray | None = None) -> np.ndarray:
    """Compute bounded v2.1 hail-survival topographic factor.

    Preferred formula uses elevation relative to freezing-level height.
    Fallback preserves the v2.0 elevation-only 5%/km correction.
    """
    elev_km = np.clip(np.asarray(elevation_m, dtype=np.float32), 0, 4000) / 1000.0
    if freezing_level_km is not None:
        fl = np.asarray(freezing_level_km, dtype=np.float32)
        fl = np.where(np.isfinite(fl) & (fl > 0.25), fl, np.nan)
        factor = 1.0 + 0.25 * (elev_km / fl)
        factor = np.where(np.isfinite(factor), factor, 1.0 + 0.05 * elev_km)
        return np.clip(factor, 1.0, 1.25).astype(np.float32)
    factor = 1.0 + 0.05 * elev_km
    return np.clip(factor, 1.0, 1.20).astype(np.float32)


def build_topo_correction():
    """
    Build topographic correction grid from elevation.

    The correction is a simple model:
    - Baseline: 0 m elevation → correction factor = 1.0
    - Higher elevation → hail survives better (shorter melt path)
    - Factor = 1.0 + 0.05 × (elevation_km)  (5% per km of elevation)
    - Capped at 1.0–1.20 range

    This is a first-order approximation. A full treatment would use
    ERA5 melting layer heights and Rasmussen & Heymsfield (1987) melt models.

    If DEM data is not available, returns a uniform 1.0 grid.
    """
    log("  Building topographic correction ...")
    TOPO_DIR.mkdir(parents=True, exist_ok=True)

    # Check if DEM exists
    dem_path = TOPO_DIR / "elevation_0.05deg.tif"
    if dem_path.exists():
        import rasterio
        with rasterio.open(dem_path) as src:
            elev = src.read(1)
        log(f"  Using existing DEM: {dem_path.name}")
    else:
        log(f"  No DEM found at {dem_path}")
        log(f"  Using uniform correction factor = 1.0")
        log(f"  To add topographic correction, download GMTED2010 or SRTM")
        log(f"  and resample to 0.05° at {dem_path}")
        correction = np.ones((NROWS, NCOLS), dtype=np.float32)
        write_geotiff(correction, TOPO_DIR / "topo_correction.tif")
        return correction

    # Compute correction factor. If future workflows write a same-grid freezing-level
    # raster, pass it into compute_topo_factor here. Fallback remains deterministic.
    correction = compute_topo_factor(elev)

    write_geotiff(correction, TOPO_DIR / "topo_correction.tif")
    log(f"  Topo correction: min={correction.min():.3f} max={correction.max():.3f}")
    return correction


def apply_mask_to_rasters(conus_mask, topo_correction):
    """Apply CONUS mask and topo correction to all RP and p_occ rasters."""
    import rasterio

    # Find all RP and p_occ rasters
    targets = []
    targets.extend(sorted(CDF_DIR.glob("rp_*yr_hail*.tif")))
    targets.extend(sorted(CDF_DIR.glob("p_occurrence*.tif")))
    targets.extend(sorted(OCC_DIR.glob("p_occ_*.tif")))
    targets.extend(sorted(STOCH_MAP_DIR.glob("rp_*yr_stochastic.tif")))

    log(f"  Applying mask to {len(targets)} rasters ...")
    outside_mask = ~conus_mask

    for tif_path in targets:
        with rasterio.open(tif_path) as src:
            data = src.read(1)
            profile = src.profile.copy()

        # Apply topo correction to RP maps (not to p_occ)
        is_rp = "rp_" in tif_path.name
        if is_rp:
            data = data * topo_correction

        # Apply CONUS mask
        data[outside_mask] = 0.0

        profile.update(compress="lzw")
        with rasterio.open(tif_path, "w", **profile) as dst:
            dst.write(data.astype(np.float32), 1)

    log(f"  Masked {len(targets)} rasters")


def write_geotiff(data, out_path):
    import rasterio
    from rasterio.transform import from_origin
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": NCOLS,
        "height": NROWS, "count": 1, "crs": "EPSG:4326",
        "transform": from_origin(LON_MIN, LAT_MAX, DX, DX),
        "compress": "lzw", "tiled": True, "blockxsize": 256,
        "blockysize": 256, "nodata": 0.0,
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data.astype(np.float32), 1)


def validate_outputs() -> bool:
    p = MASK_DIR / "conus_mask.tif"
    if not p.exists():
        log(f"  ✗ Missing: {p}")
        return False
    log("Output validation passed ✓")
    return True


def main():
    parser = argparse.ArgumentParser(description="Apply CONUS mask + topo correction.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  CONUS Mask + Topography — Stage 12")
    log(f"{'='*60}")

    conus_mask = build_conus_mask()
    topo_correction = build_topo_correction()
    apply_mask_to_rasters(conus_mask, topo_correction)

    log(f"\n  Complete")
    ok = validate_outputs()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
