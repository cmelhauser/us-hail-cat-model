#!/usr/bin/env python3
"""
02_download_mrms_mesh.py — Download Operational MRMS MESH & Build Daily Max Rasters
=====================================================================================
Downloads NOAA operational MRMS MESH (Maximum Expected Size of Hail) data from
AWS S3 for the period October 2020 – present.

For each day:
  1. Lists all MESH timestep files (~720 per day, 2-min cadence) from S3
  2. Streams and decompresses each gzipped GRIB2 file
  3. Extracts the CONUS subset from the full grid
  4. Accumulates the daily maximum MESH per native 0.01° pixel
  5. Aggregates to 0.05° via block-maximum (5×5 cells)
  6. Saves a single-band float32 GeoTIFF (MESH in mm)

Output files are identical in format to stage 01 (MYRORSS) — same grid,
same CRS, same units — so downstream stages treat them interchangeably.

Data Source
-----------
  AWS S3: s3://noaa-mrms-pds/CONUS/MESH_00.50/YYYYMMDD/
          MRMS_MESH_00.50_YYYYMMDD-HHMMSS.grib2.gz
  No AWS account required (public bucket, unsigned requests).
  Data available from October 14, 2020 onward.

  Reference: Smith et al. (2016), Bull. Amer. Meteor. Soc., 97, 1617–1630.

Data Availability Note
----------------------
  Publicly archived MRMS MESH on AWS begins October 14, 2020.
  This creates a gap between MYRORSS (ends Dec 2011) and operational MRMS.
  The model currently covers: 1998–2011 (MYRORSS) + 2020–present (MRMS).
  Future work: request historical MRMS (2012–2019) from NSSL/NCEI, or
  compute MESH from archived NEXRAD Level-II data.

Grid Specification
------------------
  Native MRMS: 0.01° × 0.01°, 3500 rows × 7000 cols
               lat [20.005, 54.995] (south-to-north), lon [230.005, 299.995] (0–360°)
  CONUS subset: lat [24.005, 50.005], lon [235.005, 293.995]
                rows 400–2999, cols 500–6399 (2600 × 5900 native pixels)
  Output grid:  0.05° × 0.05°, 520 rows × 1180 cols = 613,600 cells
                Matches stage 01 output exactly.

Output
------
  data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif
  Single-band float32 GeoTIFF. Value = daily max MESH in mm.
  NoData = 0.0. CRS = EPSG:4326. LZW compressed.
  Same path/naming convention as stage 01 — files interleave seamlessly.

Usage
-----
  python scripts/02_download_mrms_mesh.py                # full run (2020–present)
  python scripts/02_download_mrms_mesh.py --year 2023    # single year
  python scripts/02_download_mrms_mesh.py --year 2023 --month 5
  python scripts/02_download_mrms_mesh.py --validate     # check outputs only
  python scripts/02_download_mrms_mesh.py --dry-run      # count files only

Runtime
-------
  ~3–8 hours for full run (bandwidth-dependent). ~60–100 GB downloaded.
  Resumable: skips days where output GeoTIFF already exists.
"""

import argparse
import gzip
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, NODATA
    from _io import write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, NODATA
    from scripts._io import write_geotiff
    from scripts._logging import get_logger

# ── paths ─────────────────────────────────────────────────────────────────────
OUT_DIR   = DATA_ROOT / "historical" / "mesh_0.05deg"   # same as stage 01
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "02_download_mrms_mesh.log"

# ── MRMS native grid ─────────────────────────────────────────────────────────
#    Unlike MYRORSS, MRMS GRIB2 uses 0–360° longitude and south-to-north lat
NATIVE_DX    = 0.01
NATIVE_NROWS = 3500
NATIVE_NCOLS = 7000
NATIVE_LAT_START = 20.005    # southernmost (row 0)
NATIVE_LON_START = 230.005   # westernmost in 0–360° (= -129.995°)

# ── CONUS subset (rows/cols in native grid) ───────────────────────────────────
#    lat [24.005, 50.005], lon [235.005, 293.995] (= [-124.995, -66.005])
CONUS_ROW_START = 400        # row for lat 24.005
CONUS_ROW_END   = 3000       # row for lat 50.005 (exclusive)
CONUS_COL_START = 500        # col for lon 235.005 (= -124.995)
CONUS_COL_END   = 6400       # col for lon 293.995 (= -66.005) (exclusive)
CONUS_NROWS     = CONUS_ROW_END - CONUS_ROW_START  # 2600
CONUS_NCOLS     = CONUS_COL_END - CONUS_COL_START   # 5900

# ── output grid (0.05°) ──────────────────────────────────────────────────────
AGG_FACTOR = 5
OUT_DX     = DX
OUT_NROWS  = NROWS
OUT_NCOLS  = NCOLS
# Output in standard -180/+180 convention, north-to-south (matches stage 01)
OUT_LAT_MAX = LAT_MAX
OUT_LON_MIN = LON_MIN

# ── S3 config ────────────────────────────────────────────────────────────────
S3_BUCKET  = "noaa-mrms-pds"
S3_REGION  = "us-east-1"
S3_PREFIX  = "CONUS/MESH_00.50/"

# ── date range ────────────────────────────────────────────────────────────────
START_DATE = date(2020, 10, 14)   # earliest data on AWS
END_DATE   = date.today()         # up to today

# ── nodata / thresholds ──────────────────────────────────────────────────────
OUT_NODATA = NODATA

log = get_logger("02_download_mrms_mesh", LOG_ROOT).info

def get_s3_client():
    """Create an unsigned S3 client."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    return boto3.client(
        "s3",
        config=Config(signature_version=UNSIGNED),
        region_name=S3_REGION,
    )

def list_mesh_keys(s3, day: date) -> list:
    """List all MESH GRIB2 file keys for a given day."""
    prefix = f"{S3_PREFIX}{day.strftime('%Y%m%d')}/"
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".grib2.gz"):
                keys.append(obj["Key"])
    return keys

def parse_grib2_mesh(grib_bytes: bytes, daily_max: np.ndarray) -> int:
    """
    Parse a GRIB2 MRMS MESH file and update daily_max in place.

    Operational MRMS MESH arrives as a full 3500×7000 grid (south-to-north,
    0–360° lon). We extract the CONUS subset, flip to north-to-south
    orientation, and take element-wise maximum with the running daily_max.

    Parameters
    ----------
    grib_bytes : bytes
        Raw GRIB2 file content (decompressed).
    daily_max : np.ndarray
        Shape (CONUS_NROWS, CONUS_NCOLS), float32. Updated in place.
        Oriented north-to-south to match output convention.

    Returns
    -------
    int
        Number of valid CONUS pixels with MESH > 0 in this timestep.
    """
    import tempfile
    import os

    fd, tmp = tempfile.mkstemp(suffix=".grib2")
    try:
        os.write(fd, grib_bytes)
        os.close(fd)

        import xarray as xr
        ds = xr.open_dataset(tmp, engine="cfgrib")

        # The variable name may be 'unknown' or 'MESH' depending on cfgrib version
        var_name = list(ds.data_vars)[0]
        data = ds[var_name].values  # shape: (3500, 7000), south-to-north
        ds.close()
    finally:
        os.unlink(tmp)

    # Extract CONUS subset (still south-to-north at this point)
    conus = data[CONUS_ROW_START:CONUS_ROW_END, CONUS_COL_START:CONUS_COL_END]

    # Flip to north-to-south (row 0 = northernmost lat) to match stage 01
    conus = conus[::-1, :].copy()

    # Replace NaN and negative values with 0
    conus = np.where(np.isfinite(conus) & (conus > 0), conus, 0.0).astype(np.float32)

    # Update daily max
    valid_count = int(np.count_nonzero(conus > 0))
    np.maximum(daily_max, conus, out=daily_max)

    return valid_count

def block_max(data: np.ndarray, factor: int) -> np.ndarray:
    """
    Aggregate 2D array via block-maximum.

    MESH is a hail size estimate — the meaningful aggregation is the
    maximum hail size observed anywhere within each output cell.
    """
    r, c = data.shape
    r2, c2 = r // factor, c // factor
    return (
        data[:r2 * factor, :c2 * factor]
        .reshape(r2, factor, c2, factor)
        .max(axis=(1, 3))
    )


def process_day(s3, day: date, dry_run: bool = False) -> dict:
    """
    Download all MESH timesteps for one day, compute daily max,
    aggregate to 0.05°, and write GeoTIFF.
    """
    out_path = OUT_DIR / f"{day.year}" / f"mesh_{day.strftime('%Y%m%d')}.tif"

    if out_path.exists():
        return {"skipped": True}

    keys = list_mesh_keys(s3, day)

    if dry_run:
        return {"files": len(keys), "dry_run": True}

    if not keys:
        # No data for this day — write an all-zero file
        data = np.zeros((OUT_NROWS, OUT_NCOLS), dtype=np.float32)
        write_geotiff(data, out_path)
        return {"files": 0, "pixels": 0, "max_mesh_mm": 0.0}

    # Accumulate daily max at native resolution (north-to-south)
    daily_max = np.zeros((CONUS_NROWS, CONUS_NCOLS), dtype=np.float32)
    total_pixels = 0
    errors = 0

    for key in keys:
        try:
            resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
            gz_data = resp["Body"].read()
            grib_data = gzip.decompress(gz_data)
            n_px = parse_grib2_mesh(grib_data, daily_max)
            total_pixels += n_px
        except Exception as e:
            errors += 1
            if errors <= 3:
                log(f"    WARN: failed to read {key.split('/')[-1]}: {e}")

    # Aggregate to 0.05°
    out_data = block_max(daily_max, AGG_FACTOR)
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
        # Count files from 2020 onward (stage 02 territory)
        tifs = sorted(p for p in OUT_DIR.rglob("mesh_????????.tif")
                      if p.stem >= "mesh_20201014")
        if len(tifs) < 1000:
            errors.append(f"Too few MRMS TIFFs: {len(tifs)} (expected ≥1000)")
        else:
            log(f"  Found {len(tifs):,} MRMS daily MESH GeoTIFFs")

        # Spot-check
        sample = random.sample(tifs, min(20, len(tifs)))
        for p in sample:
            try:
                with rasterio.open(p) as src:
                    if src.crs.to_epsg() != 4326:
                        errors.append(f"Wrong CRS in {p.name}: {src.crs}")
                    if src.width != OUT_NCOLS or src.height != OUT_NROWS:
                        errors.append(f"Wrong shape in {p.name}: {src.width}×{src.height}")
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
        description="Download operational MRMS MESH and build daily max 0.05° rasters.")
    parser.add_argument("--year", type=int, default=None,
                        help="Process a single year")
    parser.add_argument("--month", type=int, default=None,
                        help="Process a single month (requires --year)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count S3 files without downloading")
    parser.add_argument("--validate", action="store_true",
                        help="Check outputs only")
    args = parser.parse_args()

    if args.validate:
        ok = validate_outputs()
        sys.exit(0 if ok else 1)

    log(f"\n{'='*60}")
    log(f"  Operational MRMS MESH Download — Stage 02")
    log(f"{'='*60}")
    log(f"  Source:    s3://{S3_BUCKET}/{S3_PREFIX}")
    log(f"  Output:    {OUT_DIR}")
    log(f"  Grid:      {OUT_NROWS} × {OUT_NCOLS} @ {OUT_DX}°")

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
    log(f"  NOTE:      Gap exists from 2012-01-01 to 2020-10-13 (no public MRMS MESH archive)")

    if args.dry_run:
        log(f"  Mode:      DRY RUN")

    s3 = get_s3_client()

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

        if done % 30 == 0 or max_mm > 50:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta_sec = (total_days - done - skipped) / rate if rate > 0 else 0
            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_sec))
            log(f"  [{day}] done={done:,}  skipped={skipped:,}  "
                f"files={n_files}  max={max_mm:.0f}mm  ETA={eta_str}")

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/3600:.1f} hours")
    log(f"  Days processed: {done:,}")
    log(f"  Days skipped (existing): {skipped:,}")
    log(f"  Days with no MESH data: {zero_days:,}")
    log(f"  Total S3 files read: {total_files:,}")
    log(f"  Peak MESH: {peak_mesh:.1f} mm ({peak_mesh/25.4:.1f} in)")
    log(f"{'='*60}\n")

    if not args.dry_run:
        ok = validate_outputs()
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
