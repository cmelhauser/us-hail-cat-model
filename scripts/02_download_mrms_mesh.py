#!/usr/bin/env python3
"""
02_download_mrms_mesh.py — Download Operational MRMS MESH & Build Daily Max Rasters
=====================================================================================
Downloads NOAA operational MRMS MESH (Maximum Expected Size of Hail) data from
AWS S3 for the period October 2020 – present.

For each **convective day** (12 UTC → 12 UTC; label = date at window start):
  1. Lists MESH timesteps from the two UTC calendar S3 prefixes that overlap the window
  2. Streams and decompresses each gzipped GRIB2 file
  3. Extracts the CONUS subset from the full grid
  4. Accumulates the convective-day maximum MESH per native 0.01° pixel
  5. Aggregates to 0.05° via block-maximum (5×5 cells)
  6. Applies physical QA (finite, non-negative, ≤300.0 mm)
  7. Saves a single-band float32 GeoTIFF (MESH in mm)

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
  Single-band float32 GeoTIFF. Value = convective-day max MESH in mm.
  GDAL tag ``CONVECTIVE_WINDOW_UTC`` records the 12Z→12Z interval.
  NoData = 0.0. CRS = EPSG:4326. LZW compressed.
  Same path/naming convention as stage 01 — files interleave seamlessly.

  data/historical/mesh_0.05deg/manifest_stage02_mrms.csv
  Same schema as manifest_stage01_myrorss.csv (source-format columns count GRIB2).

Usage
-----
  python scripts/02_download_mrms_mesh.py                # full run (2020–present)
  python scripts/02_download_mrms_mesh.py --year 2023    # single year
  python scripts/02_download_mrms_mesh.py --year 2023 --month 5
  python scripts/02_download_mrms_mesh.py --validate     # check outputs only
  python scripts/02_download_mrms_mesh.py --dry-run      # count files only
  python scripts/02_download_mrms_mesh.py --manifest-only  # rebuild manifest from S3 + TIFFs
  python scripts/02_download_mrms_mesh.py --workers 16   # more parallel I/O per day

Runtime
-------
  ~3–8 hours for full run (bandwidth-dependent). ~60–100 GB downloaded.
  Resumable: skips days where output GeoTIFF already exists.
"""

from __future__ import annotations

import argparse
import gzip
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import (
        REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN,
        NODATA, MAX_HAIL_MM,
    )
    from _io import (
        classify_mesh_source_day,
        convective_day_window_tag,
        count_plain_and_compressed_sources,
        calendar_days_for_convective_day,
        filter_keys_for_convective_day,
        mesh_manifest_row,
        mesh_path_for_convective_day,
        sanitize_hail_values,
        summarize_mesh_output_raster,
        upsert_mesh_manifest_row,
        write_geotiff,
    )
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import (
        REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN,
        NODATA, MAX_HAIL_MM,
    )
    from scripts._io import (
        classify_mesh_source_day,
        convective_day_window_tag,
        count_plain_and_compressed_sources,
        calendar_days_for_convective_day,
        filter_keys_for_convective_day,
        mesh_manifest_row,
        mesh_path_for_convective_day,
        sanitize_hail_values,
        summarize_mesh_output_raster,
        upsert_mesh_manifest_row,
        write_geotiff,
    )
    from scripts._logging import get_logger

# ── paths ─────────────────────────────────────────────────────────────────────
OUT_DIR   = DATA_ROOT / "historical" / "mesh_0.05deg"   # same as stage 01
MANIFEST_FILE = OUT_DIR / "manifest_stage02_mrms.csv"
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
QA_MAX_HAIL_MM = MAX_HAIL_MM

log = get_logger("02_download_mrms_mesh", LOG_ROOT).info

# cfgrib/eccodes decode is not reliable under concurrent opens from many threads.
_GRIB_DECODE_LOCK = threading.Lock()

# boto3 clients are not documented thread-safe; use one per worker thread.
_thread_local_s3 = threading.local()


def _thread_s3_client():
    client = getattr(_thread_local_s3, "client", None)
    if client is None:
        _thread_local_s3.client = get_s3_client()
    return _thread_local_s3.client


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

def list_mesh_keys(s3, calendar_day: date) -> list:
    """List all MESH GRIB2 file keys for a UTC calendar day (S3 prefix)."""
    prefix = f"{S3_PREFIX}{calendar_day.strftime('%Y%m%d')}/"
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".grib2.gz"):
                keys.append(obj["Key"])
    return keys


def list_mesh_keys_for_convective_day(s3, convective_day: date) -> list:
    """List MRMS keys in the 12 UTC → 12 UTC window labeled ``convective_day``."""
    cal_a, cal_b = calendar_days_for_convective_day(convective_day)
    keys: list[str] = []
    for cal in (cal_a, cal_b):
        keys.extend(list_mesh_keys(s3, cal))
    return filter_keys_for_convective_day(keys, convective_day)

def timestep_conus_mesh_from_grib_bytes(grib_bytes: bytes) -> tuple[np.ndarray, int]:
    """
    Decode one MRMS MESH GRIB2 timestep into CONUS north-to-south float32 grid.

    Returns
    -------
    conus : np.ndarray
        Shape (CONUS_NROWS, CONUS_NCOLS), float32; hail mm or 0.
    valid_count : int
        Count of CONUS pixels with MESH > 0 after QA.
    """
    import tempfile
    import os

    fd, tmp = tempfile.mkstemp(suffix=".grib2")
    try:
        os.write(fd, grib_bytes)
        os.close(fd)

        import xarray as xr

        with _GRIB_DECODE_LOCK:
            ds = xr.open_dataset(tmp, engine="cfgrib")
            try:
                # The variable name may be 'unknown' or 'MESH' depending on cfgrib version
                var_name = list(ds.data_vars)[0]
                data = ds[var_name].values  # shape: (3500, 7000), south-to-north
            finally:
                ds.close()
    finally:
        os.unlink(tmp)

    # Extract CONUS subset (still south-to-north at this point)
    conus = data[CONUS_ROW_START:CONUS_ROW_END, CONUS_COL_START:CONUS_COL_END]

    # Flip to north-to-south (row 0 = northernmost lat) to match stage 01
    conus = conus[::-1, :].copy()

    # Replace NaN and negative values with 0
    conus = np.where(
        np.isfinite(conus) & (conus > 0) & (conus <= QA_MAX_HAIL_MM),
        conus,
        0.0,
    ).astype(np.float32)

    valid_count = int(np.count_nonzero(conus > 0))
    return conus, valid_count


def parse_grib2_mesh(grib_bytes: bytes, daily_max: np.ndarray) -> int:
    """Sequential helper: merge one timestep into ``daily_max``. Returns pixel count."""
    conus, n_px = timestep_conus_mesh_from_grib_bytes(grib_bytes)
    np.maximum(daily_max, conus, out=daily_max)
    return n_px


def _fetch_and_decode_timestep(key: str) -> tuple[str, np.ndarray | None, int, Exception | None]:
    """
    Download one gzipped GRIB2 object and decode it (runs in a worker thread).

    Returns (key, conus_array_or_none, pixel_count_on_success, exception_or_none).
    """
    try:
        s3 = _thread_s3_client()
        resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
        gz_data = resp["Body"].read()
        grib_data = gzip.decompress(gz_data)
        conus, n_px = timestep_conus_mesh_from_grib_bytes(grib_data)
        return key, conus, n_px, None
    except Exception as e:
        return key, None, 0, e

def summarize_mrms_key_formats(keys: list) -> tuple[int, int]:
    """Return plain vs gzipped GRIB2 key counts (uses manifest plain/gz columns)."""
    return count_plain_and_compressed_sources(
        keys,
        plain_suffixes=(".grib2",),
        compressed_suffixes=(".grib2.gz",),
    )


def upsert_manifest_row(row: dict) -> None:
    upsert_mesh_manifest_row(MANIFEST_FILE, row)


def manifest_row(
    day: date,
    out_path: Path,
    keys: list,
    source_pixels: int | None,
    active_cells: int,
    max_mesh_mm: float,
    status: str,
    *,
    skipped: bool = False,
    read_errors: int | None = None,
) -> dict:
    plain_count, gz_count = summarize_mrms_key_formats(keys)
    return mesh_manifest_row(
        day,
        out_path,
        REPO_ROOT,
        source_files=len(keys),
        plain_count=plain_count,
        gz_count=gz_count,
        source_pixels=source_pixels,
        active_cells=active_cells,
        max_mesh_mm=max_mesh_mm,
        status=status,
        skipped=skipped,
        read_errors=read_errors,
    )


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


def process_day(s3, day: date, dry_run: bool = False, workers: int = 8) -> dict:
    """
    Download MESH timesteps for one convective day (12 UTC → 12 UTC), compute max,
    aggregate to 0.05°, and write GeoTIFF. ``day`` is the convective-day label.
    """
    out_path = mesh_path_for_convective_day(OUT_DIR, day)
    keys = list_mesh_keys_for_convective_day(s3, day)

    if dry_run:
        return {"files": len(keys), "dry_run": True}

    if out_path.exists():
        active_cells, max_mesh_mm = summarize_mesh_output_raster(
            out_path, max_hail_mm=QA_MAX_HAIL_MM
        )
        status = classify_mesh_source_day(len(keys), active_cells)
        upsert_manifest_row(manifest_row(
            day, out_path, keys, None, active_cells, max_mesh_mm,
            status, skipped=True, read_errors=None,
        ))
        return {
            "skipped": True,
            "files": len(keys),
            "active_cells": active_cells,
            "max_mesh_mm": max_mesh_mm,
            "status": status,
        }

    if not keys:
        # No data for this day — write an all-zero file
        data = np.zeros((OUT_NROWS, OUT_NCOLS), dtype=np.float32)
        write_geotiff(
            data,
            out_path,
            tags={"CONVECTIVE_WINDOW_UTC": convective_day_window_tag(day)},
        )
        status = classify_mesh_source_day(0, 0)
        upsert_manifest_row(manifest_row(
            day, out_path, keys, 0, 0, 0.0, status, read_errors=0,
        ))
        return {
            "files": 0,
            "pixels": 0,
            "active_cells": 0,
            "max_mesh_mm": 0.0,
            "status": status,
        }

    # Accumulate daily max at native resolution (north-to-south)
    daily_max = np.zeros((CONUS_NROWS, CONUS_NCOLS), dtype=np.float32)
    total_pixels = 0
    errors = 0
    w = max(1, int(workers))

    if w == 1:
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
    else:
        with ThreadPoolExecutor(max_workers=w) as ex:
            for key, conus, n_px, err in ex.map(_fetch_and_decode_timestep, keys):
                if err is not None:
                    errors += 1
                    if errors <= 3:
                        log(f"    WARN: failed to read {key.split('/')[-1]}: {err}")
                    continue
                np.maximum(daily_max, conus, out=daily_max)
                total_pixels += n_px

    # Aggregate to 0.05° and apply the shared physical QA cap.
    out_data, n_repaired = sanitize_hail_values(
        block_max(daily_max, AGG_FACTOR),
        max_hail_mm=QA_MAX_HAIL_MM,
        nodata=OUT_NODATA,
    )
    if n_repaired:
        log(f"    WARN: removed {n_repaired:,} non-finite/out-of-bound cells for {day}")
    write_geotiff(
        out_data,
        out_path,
        tags={"CONVECTIVE_WINDOW_UTC": convective_day_window_tag(day)},
    )

    active = out_data[(out_data > 0) & np.isfinite(out_data)]
    active_cells = int(active.size)
    max_mesh_mm = round(float(active.max()), 1) if active.size else 0.0
    status = classify_mesh_source_day(len(keys), active_cells, errors)
    upsert_manifest_row(manifest_row(
        day, out_path, keys, total_pixels, active_cells, max_mesh_mm,
        status, read_errors=errors,
    ))
    return {
        "files": len(keys),
        "pixels": total_pixels,
        "active_cells": active_cells,
        "max_mesh_mm": max_mesh_mm,
        "errors": errors,
        "status": status,
    }


def rebuild_manifest_from_outputs(s3, d_start: date, d_end: date) -> int:
    """Upsert manifest rows from S3 listings and existing GeoTIFFs (no download)."""
    n = 0
    for day in iter_dates(d_start, d_end):
        keys = list_mesh_keys_for_convective_day(s3, day)
        out_path = mesh_path_for_convective_day(OUT_DIR, day)
        if out_path.exists():
            active_cells, max_mesh_mm = summarize_mesh_output_raster(
                out_path, max_hail_mm=QA_MAX_HAIL_MM
            )
            status = classify_mesh_source_day(len(keys), active_cells)
            upsert_manifest_row(manifest_row(
                day, out_path, keys, None, active_cells, max_mesh_mm,
                status, skipped=True, read_errors=None,
            ))
        elif not keys:
            upsert_manifest_row(manifest_row(
                day, out_path, keys, 0, 0, 0.0,
                classify_mesh_source_day(0, 0), read_errors=0,
            ))
        else:
            continue
        n += 1
    return n

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

        for p in tifs:
            try:
                with rasterio.open(p) as src:
                    data = src.read(1)
                invalid = (~np.isfinite(data)) | (data < 0) | (data > QA_MAX_HAIL_MM)
                if np.any(invalid):
                    errors.append(
                        f"Invalid MRMS MESH values in {p.name}: "
                        f"{int(np.count_nonzero(invalid)):,} cells outside "
                        f"[0, {QA_MAX_HAIL_MM:.1f}] mm"
                    )
            except Exception as e:
                errors.append(f"Cannot read {p.name}: {e}")

    if errors:
        log("CRITICAL: Output validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True


def build_arg_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Rebuild manifest_stage02_mrms.csv from S3 + existing GeoTIFFs",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        metavar="N",
        help="Parallel S3 + decode threads per day (default: 8; use 1 for fully sequential)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.validate:
        ok = validate_outputs()
        sys.exit(0 if ok else 1)

    if args.manifest_only:
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
        s3 = get_s3_client()
        n = rebuild_manifest_from_outputs(s3, d_start, d_end)
        log(f"  Manifest rows upserted: {n:,} → {MANIFEST_FILE}")
        sys.exit(0)

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
    log(f"  Workers:   {args.workers} thread(s) per day (S3 + GRIB decode)")
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
        result = process_day(s3, day, dry_run=args.dry_run, workers=args.workers)

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
