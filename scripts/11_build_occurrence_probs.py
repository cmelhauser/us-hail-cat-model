#!/usr/bin/env python3
"""
11_build_occurrence_probs.py — Annual Occurrence Probability Rasters
=====================================================================
Computes the annual probability that hail exceeds each of 8 thresholds
at every grid cell, directly from the corrected MESH75 annual max series.

Thresholds: 0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00 inches
(converted to mm: 6.35, 12.7, 25.4, 38.1, 50.8, 76.2, 101.6, 127.0)

p_occ(threshold) = (years with annual max ≥ threshold) / total years

Input:  data/historical/mesh_0.05deg_corrected/
Output: data/analysis/occurrence/p_occ_Xp00in.tif (8 files)

Usage:
  python scripts/11_build_occurrence_probs.py
  python scripts/11_build_occurrence_probs.py --validate
"""

import argparse
import sys
import time
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
MESH_DIR  = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
OUT_DIR   = DATA_ROOT / "analysis" / "occurrence"
LOG_DIR   = REPO_ROOT / "logs"
LOG_FILE  = LOG_DIR / "11_build_occurrence_probs.log"

NROWS = 520
NCOLS = 1180
DX    = 0.05
LAT_MAX = 50.005
LON_MIN = -125.005

THRESHOLDS_IN = [0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00]
MM_PER_IN = 25.4


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def write_geotiff(data, out_path):
    import rasterio
    from rasterio.transform import from_origin
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": NCOLS,
        "height": NROWS, "count": 1, "crs": "EPSG:4326",
        "transform": from_origin(LON_MIN, LAT_MAX, DX, DX),
        "compress": "lzw", "tiled": True, "blockxsize": 256,
        "blockysize": 256, "nodata": -1.0,
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data.astype(np.float32), 1)


def validate_outputs() -> bool:
    errors = []
    for t in THRESHOLDS_IN:
        tag = f"{t:.2f}".replace(".", "p")
        p = OUT_DIR / f"p_occ_{tag}in.tif"
        if not p.exists():
            errors.append(f"Missing: {p.name}")
    if errors:
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log(f"Output validation passed ✓ ({len(THRESHOLDS_IN)} files)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Build occurrence probability rasters.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  Occurrence Probabilities — Stage 11")
    log(f"{'='*60}")

    import rasterio

    # Build annual max
    year_dirs = sorted(d for d in MESH_DIR.iterdir() if d.is_dir() and d.name.isdigit())
    years = [int(d.name) for d in year_dirs]
    n_years = len(years)
    log(f"  Years: {years[0]}–{years[-1]} ({n_years})")

    annual_max = np.zeros((n_years, NROWS, NCOLS), dtype=np.float32)
    for yi, ydir in enumerate(year_dirs):
        for fpath in ydir.glob("mesh_????????.tif"):
            with rasterio.open(fpath) as src:
                data = src.read(1)
            np.maximum(annual_max[yi], data, out=annual_max[yi])

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for thresh_in in THRESHOLDS_IN:
        thresh_mm = thresh_in * MM_PER_IN
        exceeds = (annual_max >= thresh_mm).sum(axis=0)
        p_occ = (exceeds / n_years).astype(np.float32)

        tag = f"{thresh_in:.2f}".replace(".", "p")
        path = OUT_DIR / f"p_occ_{tag}in.tif"
        write_geotiff(p_occ, path)

        n_active = int((p_occ > 0).sum())
        peak = float(p_occ.max())
        log(f"  p_occ ≥ {thresh_in:.2f}\": {n_active:,} cells, max = {peak:.3f}")

    log(f"\n  Complete")
    ok = validate_outputs()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
