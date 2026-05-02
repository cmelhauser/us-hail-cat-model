#!/usr/bin/env python3
"""
07_build_hail_climo.py — Build Daily MESH75 Climatology
========================================================
Computes 366 daily climatology rasters from the bias-corrected MESH75
record (data/historical/mesh_0.05deg_corrected/).

For each calendar day (DOY 001–366):
  - Collects all corrected MESH75 rasters for that calendar day across all years
  - Computes the mean MESH75 value at each cell (including zeros)
  - Writes a single-band float32 GeoTIFF

The climatology captures the seasonal and spatial patterns of hail
occurrence and intensity. It serves two purposes:
  1. Diagnostic reference for model validation
  2. DOY weighting for the stochastic catalog (stage 13)

Input
-----
  data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif

Output
------
  data/historical/mesh_0.05deg_climo/climo_DOY.tif  (366 files, DOY = 001–366)

Usage
-----
  python scripts/07_build_hail_climo.py
  python scripts/07_build_hail_climo.py --validate
"""

import argparse
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
IN_DIR    = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
OUT_DIR   = DATA_ROOT / "historical" / "mesh_0.05deg_climo"
FIG_DIR   = REPO_ROOT / "docs" / "figures" / "historical"
LOG_DIR   = REPO_ROOT / "logs"
LOG_FILE  = LOG_DIR / "07_build_hail_climo.log"

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


def build_doy_index() -> dict:
    """Map each DOY (1–366) to a list of corrected MESH75 raster paths."""
    doy_files = defaultdict(list)
    for tif in sorted(IN_DIR.rglob("mesh_????????.tif")):
        datestr = tif.stem.replace("mesh_", "")
        try:
            dt = date(int(datestr[:4]), int(datestr[4:6]), int(datestr[6:8]))
            doy = dt.timetuple().tm_yday
            doy_files[doy].append(tif)
        except ValueError:
            continue
    return doy_files


def write_geotiff(data: np.ndarray, out_path: Path):
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


def build_climatology():
    import rasterio

    log("\n  Building DOY index ...")
    doy_files = build_doy_index()
    total_files = sum(len(v) for v in doy_files.values())
    log(f"  Found {total_files:,} corrected MESH75 rasters across {len(doy_files)} DOYs")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # Also track seasonal mean for summary
    annual_mean = np.zeros((NROWS, NCOLS), dtype=np.float64)
    annual_p_occ = np.zeros((NROWS, NCOLS), dtype=np.float64)

    for doy in range(1, 367):
        out_path = OUT_DIR / f"climo_{doy:03d}.tif"
        files = doy_files.get(doy, [])

        if not files:
            write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), out_path)
            continue

        # Accumulate mean
        total = np.zeros((NROWS, NCOLS), dtype=np.float64)
        count = np.zeros((NROWS, NCOLS), dtype=np.float64)
        n_years = len(files)

        for fpath in files:
            try:
                with rasterio.open(fpath) as src:
                    data = src.read(1).astype(np.float64)
                total += data
                count += (data > 0).astype(np.float64)
            except Exception:
                n_years -= 1

        if n_years > 0:
            climo_mean = (total / n_years).astype(np.float32)
        else:
            climo_mean = np.zeros((NROWS, NCOLS), dtype=np.float32)

        write_geotiff(climo_mean, out_path)
        annual_mean += total
        annual_p_occ += count

        if doy % 50 == 0:
            elapsed = time.time() - t0
            log(f"    DOY {doy}/366  ({elapsed:.0f}s)")

    # Write annual summary stats
    total_years = len(set(int(f.parent.name) for f in IN_DIR.rglob("mesh_????????.tif")))
    if total_years > 0:
        ann_mean = (annual_mean / total_years).astype(np.float32)
        ann_pocc = (annual_p_occ / total_years).astype(np.float32)
        write_geotiff(ann_mean, OUT_DIR / "annual_mean_mesh75.tif")
        write_geotiff(ann_pocc, OUT_DIR / "annual_hail_days.tif")
        log(f"  Annual mean MESH75: peak = {ann_mean.max():.1f} mm")
        log(f"  Annual hail days: max = {ann_pocc.max():.1f} days/yr")

    elapsed = time.time() - t0
    log(f"  Climatology complete in {elapsed:.0f}s")


def make_seasonal_figure():
    """Generate a seasonal hail activity summary figure."""
    import rasterio
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    # Monthly sums
    monthly_activity = []
    for m in range(1, 13):
        # DOY range for this month (approximate)
        from calendar import monthrange
        d_start = date(2000, m, 1).timetuple().tm_yday
        d_end = date(2000, m, monthrange(2000, m)[1]).timetuple().tm_yday
        total = 0.0
        for doy in range(d_start, d_end + 1):
            p = OUT_DIR / f"climo_{doy:03d}.tif"
            if p.exists():
                with rasterio.open(p) as src:
                    total += src.read(1).sum()
        monthly_activity.append(total)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ax.bar(months, monthly_activity, color="#2196F3")
    ax.set_ylabel("Total MESH75 Activity (sum of daily climatology, mm)")
    ax.set_title("Monthly Hail Activity — MESH75 Climatology")
    fig.savefig(FIG_DIR / "seasonal_hail_activity.png", dpi=150, bbox_inches="tight")
    plt.close()
    log(f"  Seasonal figure saved to {FIG_DIR}")


def validate_outputs() -> bool:
    import rasterio
    errors = []
    if not OUT_DIR.exists():
        errors.append(f"Missing: {OUT_DIR}")
    else:
        tifs = sorted(OUT_DIR.glob("climo_???.tif"))
        if len(tifs) != 366:
            errors.append(f"Expected 366 climo TIFFs, found {len(tifs)}")
        for p in tifs[:5]:
            try:
                with rasterio.open(p) as src:
                    if src.width != NCOLS or src.height != NROWS:
                        errors.append(f"Wrong shape: {p.name}")
            except Exception as e:
                errors.append(f"Cannot read {p.name}: {e}")
    if errors:
        log("Validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log(f"Output validation passed ✓ ({len(list(OUT_DIR.glob('climo_???.tif')))} files)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Build daily MESH75 climatology.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  Daily Climatology — Stage 07")
    log(f"{'='*60}")
    log(f"  Input:  {IN_DIR}")
    log(f"  Output: {OUT_DIR}")

    build_climatology()
    make_seasonal_figure()

    ok = validate_outputs()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
