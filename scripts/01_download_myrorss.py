#!/usr/bin/env python3
"""
01_download_myrorss.py — Download MYRORSS MESH & Build Daily Max Rasters
=========================================================================
Downloads NOAA MYRORSS MESH (Maximum Expected Size of Hail) data from
AWS S3 for the period April 1998 – December 2011.

For each day:
  1. Lists all ~296 MESH timestep files (5-min cadence) from S3
  2. Streams and decompresses each gzipped NetCDF
  3. Parses sparse-grid data (pixel_x, pixel_y, MESH values in mm)
  4. Accumulates the daily maximum MESH per native 0.01° pixel
  5. Aggregates to 0.05° via block-maximum (5×5 cells)
  6. Saves a single-band float32 GeoTIFF (MESH in mm)

This avoids storing ~1.5 million small files. One output file per day.

Data Source
-----------
  AWS S3: s3://noaa-oar-myrorss-pds/YYYY/MM/DD/MESH/00.25/YYYYMMDD-HHMMSS.netcdf.gz
  No AWS account required (public bucket, unsigned requests).
  Reference: Ortega et al. (2022), Bull. Amer. Meteor. Soc., 103, E732–E749.

Grid Specification
------------------
  Native MYRORSS: 0.01° × 0.01°, origin lat=55.005°N, lon=−130.005°W
                  3501 rows × 7001 cols (full domain including Canada/Mexico)
  CONUS subset:   lat [24.005, 50.005], lon [−125.005, −66.005]
                  rows 500–3099, cols 500–6399 (2600 × 5900 native pixels)
  Output grid:    0.05° × 0.05°, 520 rows × 1180 cols = 613,600 cells
  Aggregation:    Block-maximum (5×5 native cells → 1 output cell)

Output
------
  data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif
  Single-band float32 GeoTIFF. Value = daily max MESH in mm.
  NoData = 0.0 (no MESH signal). CRS = EPSG:4326. LZW compressed.

Usage
-----
  python scripts/01_download_myrorss.py                  # full run (1998–2011)
  python scripts/01_download_myrorss.py --year 2005      # single year
  python scripts/01_download_myrorss.py --year 2005 --month 5   # single month
  python scripts/01_download_myrorss.py --validate       # check outputs only
  python scripts/01_download_myrorss.py --dry-run        # count files without downloading

Runtime
-------
  ~2–6 hours for full run (bandwidth-dependent). ~10–20 GB downloaded.
  Resumable: skips days where output GeoTIFF already exists.
"""

import argparse
import gzip
import io
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
OUT_DIR   = DATA_ROOT / "historical" / "mesh_0.05deg"
LOG_DIR   = REPO_ROOT / "logs"
LOG_FILE  = LOG_DIR / "01_download_myrorss.log"

# ── MYRORSS native grid ──────────────────────────────────────────────────────
NATIVE_LAT_ORIGIN = 55.005      # northernmost latitude (row 0)
NATIVE_LON_ORIGIN = -130.005    # westernmost longitude (col 0)
NATIVE_DX         = 0.01        # degrees per pixel
NATIVE_NROWS      = 3501
NATIVE_NCOLS      = 7001

# ── CONUS subset (rows/cols in native grid) ───────────────────────────────────
#    lat [24.005, 50.005], lon [−125.005, −66.005]
CONUS_ROW_START = 500           # row for lat ~50.005
CONUS_ROW_END   = 3100          # row for lat ~24.005 (exclusive)
CONUS_COL_START = 500           # col for lon ~-125.005
CONUS_COL_END   = 6400          # col for lon ~-66.005 (exclusive)
CONUS_NROWS     = CONUS_ROW_END - CONUS_ROW_START   # 2600
CONUS_NCOLS     = CONUS_COL_END - CONUS_COL_START    # 5900

# ── output grid (0.05°) ──────────────────────────────────────────────────────
AGG_FACTOR  = 5                  # 5×5 native cells → 1 output cell
OUT_DX      = NATIVE_DX * AGG_FACTOR   # 0.05°
OUT_NROWS   = CONUS_NROWS // AGG_FACTOR  # 520
OUT_NCOLS   = CONUS_NCOLS // AGG_FACTOR  # 1180
OUT_LAT_MAX = NATIVE_LAT_ORIGIN - CONUS_ROW_START * NATIVE_DX  # 50.005
OUT_LON_MIN = NATIVE_LON_ORIGIN + CONUS_COL_START * NATIVE_DX  # -125.005

# ── S3 config ────────────────────────────────────────────────────────────────
S3_BUCKET   = "noaa-oar-myrorss-pds"
S3_REGION   = "us-east-1"
MESH_PREFIX = "MESH/00.25/"      # within each YYYY/MM/DD/

# ── date range ────────────────────────────────────────────────────────────────
START_DATE = date(1998, 4, 1)    # MYRORSS begins April 1998
END_DATE   = date(2011, 12, 31)  # MYRORSS ends December 2011

# ── nodata ────────────────────────────────────────────────────────────────────
MYRORSS_NODATA = -99900.0
OUT_NODATA     = 0.0


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_s3_client():
    """Create an unsigned S3 client (no AWS credentials needed)."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    return boto3.client(
        "s3",
        config=Config(signature_version=UNSIGNED),
        region_name=S3_REGION,
    )


def list_mesh_keys(s3, day: date) -> list:
    """List all MESH file keys for a given day."""
    prefix = f"{day.year}/{day.month:02d}/{day.day:02d}/{MESH_PREFIX}"
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".netcdf.gz"):
                keys.append(obj["Key"])
    return keys


def parse_sparse_mesh(nc_bytes: bytes, daily_max: np.ndarray) -> int:
    """
    Parse a sparse-grid MYRORSS MESH NetCDF and update daily_max in place.

    The NetCDF uses sparse storage: pixel_x (column), pixel_y (row), and
    MESH value arrays. We map these into CONUS subset coordinates and
    take the element-wise maximum with the running daily_max array.

    Parameters
    ----------
    nc_bytes : bytes
        Decompressed NetCDF file content.
    daily_max : np.ndarray
        Shape (CONUS_NROWS, CONUS_NCOLS), float32. Updated in place.

    Returns
    -------
    int
        Number of valid CONUS pixels in this timestep.
    """
    import netCDF4
    import tempfile
    import os

    # netCDF4 needs a file path — write to a temp file
    fd, tmp = tempfile.mkstemp(suffix=".nc")
    try:
        os.write(fd, nc_bytes)
        os.close(fd)

        ds = netCDF4.Dataset(tmp, "r")
        try:
            mesh_vals = ds.variables["MESH"][:]
            px = ds.variables["pixel_x"][:]
            py = ds.variables["pixel_y"][:]
        finally:
            ds.close()
    finally:
        os.unlink(tmp)

    # Filter to CONUS subset and valid values
    # pixel_y = row in full grid, pixel_x = col in full grid
    row = py.astype(np.int32)
    col = px.astype(np.int32)
    vals = mesh_vals.astype(np.float32)

    # Mask: within CONUS bounds and valid MESH
    mask = (
        (row >= CONUS_ROW_START) & (row < CONUS_ROW_END) &
        (col >= CONUS_COL_START) & (col < CONUS_COL_END) &
        (vals > 0) & (vals != MYRORSS_NODATA)
    )

    if not np.any(mask):
        return 0

    r = row[mask] - CONUS_ROW_START
    c = col[mask] - CONUS_COL_START
    v = vals[mask]

    # Update daily max
    np.maximum.at(daily_max, (r, c), v)
    return int(mask.sum())


def block_max(data: np.ndarray, factor: int) -> np.ndarray:
    """
    Aggregate 2D array via block-maximum.

    Unlike block-sum (used for counts), MESH is a size estimate —
    the physically meaningful aggregation is the maximum hail size
    observed anywhere within each output cell.

    Parameters
    ----------
    data : np.ndarray
        Shape (rows, cols) where rows and cols are divisible by factor.
    factor : int
        Block size (e.g., 5 for 0.01° → 0.05°).

    Returns
    -------
    np.ndarray
        Shape (rows // factor, cols // factor).
    """
    r, c = data.shape
    r2, c2 = r // factor, c // factor
    return (
        data[:r2 * factor, :c2 * factor]
        .reshape(r2, factor, c2, factor)
        .max(axis=(1, 3))
    )


def write_geotiff(data: np.ndarray, out_path: Path):
    """Write a single-band float32 GeoTIFF at 0.05° CONUS grid."""
    import rasterio
    from rasterio.transform import from_origin

    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver":    "GTiff",
        "dtype":     "float32",
        "width":     OUT_NCOLS,
        "height":    OUT_NROWS,
        "count":     1,
        "crs":       "EPSG:4326",
        "transform": from_origin(OUT_LON_MIN, OUT_LAT_MAX, OUT_DX, OUT_DX),
        "compress":  "lzw",
        "tiled":     True,
        "blockxsize": 256,
        "blockysize": 256,
        "nodata":    OUT_NODATA,
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data.astype(np.float32), 1)


def process_day(s3, day: date, dry_run: bool = False) -> dict:
    """
    Download all MESH timesteps for one day, compute daily max,
    aggregate to 0.05°, and write GeoTIFF.

    Returns dict with stats: {files, pixels, max_mesh_mm, skipped, error}.
    """
    out_path = OUT_DIR / f"{day.year}" / f"mesh_{day.strftime('%Y%m%d')}.tif"

    if out_path.exists():
        return {"skipped": True}

    keys = list_mesh_keys(s3, day)

    if dry_run:
        return {"files": len(keys), "dry_run": True}

    if not keys:
        # No MESH data for this day — write an all-zero file
        data = np.zeros((OUT_NROWS, OUT_NCOLS), dtype=np.float32)
        write_geotiff(data, out_path)
        return {"files": 0, "pixels": 0, "max_mesh_mm": 0.0}

    # Accumulate daily max at native resolution
    daily_max = np.zeros((CONUS_NROWS, CONUS_NCOLS), dtype=np.float32)
    total_pixels = 0
    errors = 0

    for key in keys:
        try:
            resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
            gz_data = resp["Body"].read()
            nc_data = gzip.decompress(gz_data)
            n_pixels = parse_sparse_mesh(nc_data, daily_max)
            total_pixels += n_pixels
        except Exception as e:
            errors += 1
            if errors <= 3:
                log(f"    WARN: failed to read {key}: {e}")

    # Aggregate to 0.05° via block-max
    out_data = block_max(daily_max, AGG_FACTOR)

    # Replace zeros with nodata (no MESH signal)
    # (zeros are genuinely "no hail detected", which is our nodata)

    write_geotiff(out_data, out_path)

    peak = float(daily_max.max())
    return {
        "files":       len(keys),
        "pixels":      total_pixels,
        "max_mesh_mm": round(peak, 1),
        "errors":      errors,
    }


def iter_dates(start: date, end: date):
    """Yield each date from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def validate_outputs() -> bool:
    """Validate all outputs produced by this stage."""
    import rasterio
    import random

    errors = []

    if not OUT_DIR.exists():
        errors.append(f"Missing directory: {OUT_DIR}")
    else:
        tifs = sorted(OUT_DIR.rglob("mesh_????????.tif"))
        # MYRORSS covers Apr 1998 – Dec 2011: ~5,000 days
        if len(tifs) < 4000:
            errors.append(f"Too few TIFFs: {len(tifs)} (expected ≥4000)")
        else:
            log(f"  Found {len(tifs):,} daily MESH GeoTIFFs")

        # Spot-check a random sample
        sample = random.sample(tifs, min(20, len(tifs)))
        for p in sample:
            try:
                with rasterio.open(p) as src:
                    if src.crs.to_epsg() != 4326:
                        errors.append(f"Wrong CRS in {p.name}: {src.crs}")
                    if src.width != OUT_NCOLS or src.height != OUT_NROWS:
                        errors.append(f"Wrong shape in {p.name}: {src.width}×{src.height}")
                    data = src.read(1)
                    if data.dtype != np.float32:
                        errors.append(f"Wrong dtype in {p.name}: {data.dtype}")
            except Exception as e:
                errors.append(f"Cannot read {p.name}: {e}")

    if errors:
        log("CRITICAL: Output validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Download MYRORSS MESH and build daily max 0.05° rasters.")
    parser.add_argument("--year", type=int, default=None,
                        help="Process a single year (e.g., 2005)")
    parser.add_argument("--month", type=int, default=None,
                        help="Process a single month (requires --year)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count S3 files without downloading")
    parser.add_argument("--validate", action="store_true",
                        help="Check outputs only, no downloading")
    args = parser.parse_args()

    if args.validate:
        ok = validate_outputs()
        sys.exit(0 if ok else 1)

    log(f"\n{'='*60}")
    log(f"  MYRORSS MESH Download — Stage 01")
    log(f"{'='*60}")
    log(f"  Source:    s3://{S3_BUCKET}/")
    log(f"  Output:    {OUT_DIR}")
    log(f"  Grid:      {OUT_NROWS} × {OUT_NCOLS} @ {OUT_DX}°")
    log(f"  Agg:       block-max {AGG_FACTOR}×{AGG_FACTOR} (0.01° → 0.05°)")

    # Determine date range
    if args.year and args.month:
        import calendar
        d_start = date(args.year, args.month, 1)
        d_end = date(args.year, args.month,
                     calendar.monthrange(args.year, args.month)[1])
        d_start = max(d_start, START_DATE)
        d_end = min(d_end, END_DATE)
    elif args.year:
        d_start = max(date(args.year, 1, 1), START_DATE)
        d_end = min(date(args.year, 12, 31), END_DATE)
    else:
        d_start = START_DATE
        d_end = END_DATE

    log(f"  Period:    {d_start} → {d_end}")

    if args.dry_run:
        log(f"  Mode:      DRY RUN (count files only)")

    # Create S3 client
    s3 = get_s3_client()

    # Process each day
    all_days = list(iter_dates(d_start, d_end))
    total_days = len(all_days)
    done = skipped = zero_days = total_files = 0
    peak_mesh = 0.0
    t0 = time.time()

    log(f"\n  Processing {total_days:,} days ...\n")

    for i, day in enumerate(all_days):
        result = process_day(s3, day, dry_run=args.dry_run)

        if result.get("skipped"):
            skipped += 1
            continue

        if result.get("dry_run"):
            total_files += result.get("files", 0)
            done += 1
            if done % 100 == 0:
                log(f"  [{day}] counted {done:,}/{total_days:,} days, "
                    f"{total_files:,} S3 files so far")
            continue

        done += 1
        n_files = result.get("files", 0)
        total_files += n_files
        max_mm = result.get("max_mesh_mm", 0.0)
        peak_mesh = max(peak_mesh, max_mm)

        if n_files == 0:
            zero_days += 1

        # Progress log every 50 days or on active days
        if done % 50 == 0 or max_mm > 50:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta_sec = (total_days - done - skipped) / rate if rate > 0 else 0
            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_sec))
            log(f"  [{day}] done={done:,}  skipped={skipped:,}  "
                f"files={n_files}  max={max_mm:.0f}mm  "
                f"ETA={eta_str}")

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/3600:.1f} hours")
    log(f"  Days processed: {done:,}")
    log(f"  Days skipped (existing): {skipped:,}")
    log(f"  Days with no MESH data: {zero_days:,}")
    log(f"  Total S3 files read: {total_files:,}")
    log(f"  Peak MESH observed: {peak_mesh:.1f} mm ({peak_mesh/25.4:.1f} inches)")
    log(f"{'='*60}\n")

    # Validate
    if not args.dry_run:
        ok = validate_outputs()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
