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
from pathlib import Path
import numpy as np

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, OCC_THRESHOLDS_INCH, NODATA
    from _io import write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, OCC_THRESHOLDS_INCH, NODATA
    from scripts._io import write_geotiff
    from scripts._logging import get_logger

MESH_DIR  = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
OUT_DIR   = DATA_ROOT / "analysis" / "occurrence"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "11_build_occurrence_probs.log"

THRESHOLDS_IN = list(OCC_THRESHOLDS_INCH)
MM_PER_IN = 25.4

log = get_logger("11_build_occurrence_probs", LOG_ROOT).info


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
