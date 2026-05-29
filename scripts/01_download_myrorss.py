#!/usr/bin/env python3
"""
01_download_myrorss.py — Download MYRORSS MESH & Build Daily Max Rasters
=========================================================================
Downloads NOAA MYRORSS MESH (Maximum Expected Size of Hail) data from
AWS S3 for the period April 1998 – December 2011.

For each **convective day** (12 UTC → 12 UTC; label = date at window start):
  1. Lists MESH timestep files from the two UTC calendar S3 prefixes that overlap the window
  2. Streams each plain or gzipped NetCDF
  3. Parses sparse-grid data (pixel_x, pixel_y, MESH values in mm)
  4. Accumulates the convective-day maximum MESH per native 0.01° pixel
  5. Aggregates to 0.05° via block-maximum (5×5 cells)
  6. Saves a single-band float32 GeoTIFF (MESH in mm)
  7. Runs a physical QA pass over written rasters
  8. Records source/file/output status in a daily manifest

This avoids storing ~1.5 million small files. One output file per day.

Data Source
-----------
  AWS S3: s3://noaa-oar-myrorss-pds/YYYY/MM/DD/MESH/00.25/YYYYMMDD-HHMMSS.netcdf[.gz]
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
  Single-band float32 GeoTIFF. Value = convective-day max MESH in mm.
  GDAL tag ``CONVECTIVE_WINDOW_UTC`` records the 12Z→12Z interval.
  NoData = 0.0 (no MESH signal). CRS = EPSG:4326. LZW compressed.

  data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv
  One row per day distinguishing missing source files from available source
  files that produced no hail pixels.

Usage
-----
  python scripts/01_download_myrorss.py                  # full run (1998–2011)
  python scripts/01_download_myrorss.py --year 2005      # single year
  python scripts/01_download_myrorss.py --year 2005 --month 5   # single month
  python scripts/01_download_myrorss.py --validate       # check outputs only
  python scripts/01_download_myrorss.py --qa-only        # repair existing rasters + manifest
  python scripts/01_download_myrorss.py --manifest-only  # rebuild manifest from S3 + GeoTIFFs
  python scripts/01_download_myrorss.py --dry-run        # count files without downloading

Runtime
-------
  ~2–6 hours for full run (bandwidth-dependent). ~10–20 GB downloaded.
  Resumable: skips days where output GeoTIFF already exists.
  Parallel ``--workers N`` uses N S3/decode threads; NetCDF parsing is lock-serialized
  because the netCDF4/HDF5 stack is not thread-safe on macOS/Linux.
"""

from __future__ import annotations

import argparse
import gzip
import io
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import (
        REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN,
        NODATA, MAX_HAIL_IN, MAX_HAIL_MM,
    )
    from _io import (
        MESH_SOURCE_MANIFEST_FIELDS,
        calendar_days_for_convective_day,
        classify_mesh_source_day,
        convective_day_window_tag,
        count_plain_and_compressed_sources,
        filter_keys_for_convective_day,
        mesh_manifest_row,
        mesh_path_for_convective_day,
        read_mesh_manifest_rows_by_date,
        sanitize_hail_values,
        summarize_mesh_output_raster,
        upsert_mesh_manifest_row,
        write_geotiff,
        write_mesh_manifest_rows,
    )
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import (
        REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN,
        NODATA, MAX_HAIL_IN, MAX_HAIL_MM,
    )
    from scripts._io import (
        MESH_SOURCE_MANIFEST_FIELDS,
        calendar_days_for_convective_day,
        classify_mesh_source_day,
        convective_day_window_tag,
        count_plain_and_compressed_sources,
        filter_keys_for_convective_day,
        mesh_manifest_row,
        mesh_path_for_convective_day,
        read_mesh_manifest_rows_by_date,
        sanitize_hail_values,
        summarize_mesh_output_raster,
        upsert_mesh_manifest_row,
        write_geotiff,
        write_mesh_manifest_rows,
    )
    from scripts._logging import get_logger

# ── paths ─────────────────────────────────────────────────────────────────────
OUT_DIR   = DATA_ROOT / "historical" / "mesh_0.05deg"
MANIFEST_FILE = OUT_DIR / "manifest_stage01_myrorss.csv"
LOG_DIR   = LOG_ROOT
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
OUT_DX      = DX
OUT_NROWS   = NROWS
OUT_NCOLS   = NCOLS
OUT_LAT_MAX = LAT_MAX
OUT_LON_MIN = LON_MIN

# ── physical QA ───────────────────────────────────────────────────────────────
# NOAA/NSSL lists the U.S. record hailstone as the 8 inch Vivian, South Dakota
# stone from 23 June 2010. Stage 01 uses a conservative 300 mm ceiling above
# that observed record and treats larger/non-finite values as invalid source
# artifacts before downstream bias correction and tail fitting.
QA_MAX_HAIL_IN = MAX_HAIL_IN
QA_MAX_HAIL_MM = MAX_HAIL_MM

# ── S3 config ────────────────────────────────────────────────────────────────
S3_BUCKET   = "noaa-oar-myrorss-pds"
S3_REGION   = "us-east-1"
MESH_PREFIX = "MESH/00.25/"      # within each YYYY/MM/DD/

# ── date range ────────────────────────────────────────────────────────────────
START_DATE = date(1998, 4, 1)    # MYRORSS begins April 1998
END_DATE   = date(2011, 12, 31)  # MYRORSS ends December 2011

# ── nodata ────────────────────────────────────────────────────────────────────
MYRORSS_NODATA = -99900.0
OUT_NODATA     = NODATA

MANIFEST_FIELDS = MESH_SOURCE_MANIFEST_FIELDS

log = get_logger("01_download_myrorss", LOG_ROOT).info

# netCDF4/HDF5 C library is not thread-safe for concurrent Dataset open/close.
# S3 fetch stays parallel; only the NetCDF parse is serialized.
_NETCDF_LOCK = threading.Lock()

# boto3 clients are not documented thread-safe; use one per worker thread.
_thread_local_s3 = threading.local()


def _thread_s3_client():
    client = getattr(_thread_local_s3, "client", None)
    if client is None:
        _thread_local_s3.client = get_s3_client()
    return _thread_local_s3.client


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

def list_mesh_keys(s3, calendar_day: date) -> list:
    """List all MESH file keys for a UTC calendar day (S3 prefix)."""
    prefix = f"{calendar_day.year}/{calendar_day.month:02d}/{calendar_day.day:02d}/{MESH_PREFIX}"
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".netcdf") or key.endswith(".netcdf.gz"):
                keys.append(key)
    return sorted(keys)


def list_mesh_keys_for_convective_day(s3, convective_day: date) -> list:
    """List MYRORSS keys in the 12 UTC → 12 UTC window labeled ``convective_day``."""
    cal_a, cal_b = calendar_days_for_convective_day(convective_day)
    keys: list[str] = []
    for cal in (cal_a, cal_b):
        keys.extend(list_mesh_keys(s3, cal))
    return filter_keys_for_convective_day(keys, convective_day)

def summarize_key_formats(keys: list) -> tuple[int, int]:
    """Return counts of plain and gzipped MYRORSS NetCDF keys."""
    return count_plain_and_compressed_sources(keys)

def decode_netcdf_object(key: str, payload: bytes) -> bytes:
    """Return NetCDF bytes for either plain .netcdf or gzipped .netcdf.gz objects."""
    if key.endswith(".gz"):
        return gzip.decompress(payload)
    return payload


def sparse_updates_from_netcdf_bytes(
    nc_bytes: bytes,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """
    Parse a sparse-grid MYRORSS MESH NetCDF into CONUS updates.

    Returns CONUS-subset (row, col, val) arrays so callers can merge with:
        np.maximum.at(daily_max, (row, col), val)
    """
    import netCDF4
    import tempfile
    import os

    fd, tmp = tempfile.mkstemp(suffix=".nc")
    try:
        os.write(fd, nc_bytes)
        os.close(fd)

        with _NETCDF_LOCK:
            ds = netCDF4.Dataset(tmp, "r")
            try:
                mesh_vals = ds.variables["MESH"][:]
                px = ds.variables["pixel_x"][:]
                py = ds.variables["pixel_y"][:]
            finally:
                ds.close()
    finally:
        os.unlink(tmp)

    row = py.astype(np.int32)
    col = px.astype(np.int32)
    vals = mesh_vals.astype(np.float32)

    mask = (
        (row >= CONUS_ROW_START) & (row < CONUS_ROW_END) &
        (col >= CONUS_COL_START) & (col < CONUS_COL_END) &
        np.isfinite(vals) &
        (vals > 0) & (vals <= QA_MAX_HAIL_MM) &
        (vals != MYRORSS_NODATA)
    )
    if not np.any(mask):
        empty_i = np.array([], dtype=np.int32)
        empty_v = np.array([], dtype=np.float32)
        return empty_i, empty_i, empty_v, 0

    r = row[mask] - CONUS_ROW_START
    c = col[mask] - CONUS_COL_START
    v = vals[mask]
    return r, c, v, int(mask.sum())

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
    r, c, v, n = sparse_updates_from_netcdf_bytes(nc_bytes)
    if n:
        np.maximum.at(daily_max, (r, c), v)
    return n


def _fetch_decode_sparse(
    key: str,
) -> tuple[str, np.ndarray, np.ndarray, np.ndarray, int, Exception | None]:
    """Download one MYRORSS object and return sparse CONUS updates."""
    try:
        s3 = _thread_s3_client()
        resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
        raw_data = resp["Body"].read()
        nc_data = decode_netcdf_object(key, raw_data)
        r, c, v, n = sparse_updates_from_netcdf_bytes(nc_data)
        return key, r, c, v, n, None
    except Exception as e:
        empty_i = np.array([], dtype=np.int32)
        empty_v = np.array([], dtype=np.float32)
        return key, empty_i, empty_i, empty_v, 0, e


def sanitize_mesh_array(data: np.ndarray) -> tuple[np.ndarray, int]:
    """Return a float32 array with invalid or implausible hail values zeroed.

    Stage 01 uses 0.0 as the no-signal/nodata sentinel. Values that are
    non-finite, negative, or above the physical QA cap are treated as invalid
    radar artifacts and set to 0.0 before GeoTIFF write or repair.
    """
    return sanitize_hail_values(data, max_hail_mm=QA_MAX_HAIL_MM, nodata=OUT_NODATA)

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


def summarize_output_raster(path: Path) -> tuple[int, float]:
    """Return active 0.05° cells and max MESH from an output GeoTIFF."""
    return summarize_mesh_output_raster(path, max_hail_mm=QA_MAX_HAIL_MM)


def read_manifest_rows_by_date() -> dict:
    """Read the Stage 01 manifest keyed by ISO date."""
    return read_mesh_manifest_rows_by_date(MANIFEST_FILE)


def iter_stage01_tifs() -> list[Path]:
    """Return Stage 01 GeoTIFFs only, excluding Stage 02/04b files in OUT_DIR."""
    paths = []
    for path in sorted(OUT_DIR.rglob("mesh_????????.tif")):
        try:
            day = datetime.strptime(path.stem.replace("mesh_", ""), "%Y%m%d").date()
        except ValueError:
            continue
        if START_DATE <= day <= END_DATE:
            paths.append(path)
    return paths

def manifest_row(day: date, out_path: Path, keys: list, source_pixels,
                 active_cells: int, max_mesh_mm: float, status: str,
                 skipped: bool = False, read_errors=0) -> dict:
    """Build one Stage 01 manifest row."""
    plain_count, gz_count = summarize_key_formats(keys)
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


def upsert_manifest_row(row: dict) -> None:
    """Write or replace a manifest row by date."""
    upsert_mesh_manifest_row(MANIFEST_FILE, row)


def write_manifest_rows(rows: dict) -> None:
    """Write a complete Stage 01 manifest dictionary keyed by date."""
    write_mesh_manifest_rows(MANIFEST_FILE, rows)

def process_day(s3, day: date, dry_run: bool = False, workers: int = 8) -> dict:
    """
    Download MESH timesteps for one convective day (12 UTC → 12 UTC), compute max,
    aggregate to 0.05°, and write GeoTIFF. ``day`` is the convective-day label.

    Returns dict with stats: {files, pixels, active_cells, max_mesh_mm, skipped, error}.
    """
    out_path = mesh_path_for_convective_day(OUT_DIR, day)

    keys = list_mesh_keys_for_convective_day(s3, day)

    if dry_run:
        return {"files": len(keys), "dry_run": True}

    if out_path.exists():
        active_cells, max_mesh_mm = summarize_output_raster(out_path)
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
        # No MESH data for this day — write an all-zero file
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

    # Accumulate daily max at native resolution
    daily_max = np.zeros((CONUS_NROWS, CONUS_NCOLS), dtype=np.float32)
    total_pixels = 0
    errors = 0

    w = max(1, int(workers))

    if w == 1:
        for key in keys:
            try:
                resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
                raw_data = resp["Body"].read()
                nc_data = decode_netcdf_object(key, raw_data)
                n_pixels = parse_sparse_mesh(nc_data, daily_max)
                total_pixels += n_pixels
            except Exception as e:
                errors += 1
                if errors <= 3:
                    log(f"    WARN: failed to read {key}: {e}")
    else:
        with ThreadPoolExecutor(max_workers=w) as ex:
            for key, r, c, v, n_pixels, err in ex.map(_fetch_decode_sparse, keys):
                if err is not None:
                    errors += 1
                    if errors <= 3:
                        log(f"    WARN: failed to read {key}: {err}")
                    continue
                if n_pixels:
                    np.maximum.at(daily_max, (r, c), v)
                    total_pixels += n_pixels

    # Aggregate to 0.05° via block-max and apply the physical QA cap.
    out_data, qa_native_removed = sanitize_mesh_array(block_max(daily_max, AGG_FACTOR))
    if qa_native_removed:
        log(f"    WARN: removed {qa_native_removed:,} non-finite/out-of-bound cells for {day}")

    # Replace zeros with nodata (no MESH signal)
    # (zeros are genuinely "no hail detected", which is our nodata)

    write_geotiff(
        out_data,
        out_path,
        tags={"CONVECTIVE_WINDOW_UTC": convective_day_window_tag(day)},
    )

    active_cells, max_mesh_mm = summarize_output_raster(out_path)
    peak = max_mesh_mm
    status = classify_mesh_source_day(len(keys), active_cells, errors)
    upsert_manifest_row(manifest_row(
        day, out_path, keys, total_pixels, active_cells, max_mesh_mm,
        status, read_errors=errors,
    ))
    return {
        "files":       len(keys),
        "pixels":      total_pixels,
        "active_cells": active_cells,
        "max_mesh_mm": max_mesh_mm,
        "errors":      errors,
        "status":      status,
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
        tifs = iter_stage01_tifs()
        # MYRORSS covers Apr 1998 – Dec 2011: ~5,000 days
        if len(tifs) < 4000:
            errors.append(f"Too few TIFFs: {len(tifs)} (expected ≥4000)")
        else:
            log(f"  Found {len(tifs):,} daily MESH GeoTIFFs")

        # Spot-check metadata, then scan every raster for value QA. The full
        # value scan is deliberately cheap relative to download time and keeps
        # non-finite or physically implausible cells out of downstream stages.
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

        for p in tifs:
            try:
                with rasterio.open(p) as src:
                    data = src.read(1)
                invalid = (~np.isfinite(data)) | (data < 0) | (data > QA_MAX_HAIL_MM)
                if np.any(invalid):
                    n_invalid = int(np.count_nonzero(invalid))
                    errors.append(
                        f"Invalid Stage 01 values in {p.name}: {n_invalid:,} cells "
                        f"outside [0, {QA_MAX_HAIL_MM:.1f}] mm"
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


def rebuild_manifest_from_outputs(s3, d_start: date, d_end: date) -> int:
    """Upsert manifest rows from S3 listings and existing GeoTIFFs (no download)."""
    n = 0
    for day in iter_dates(d_start, d_end):
        keys = list_mesh_keys_for_convective_day(s3, day)
        out_path = mesh_path_for_convective_day(OUT_DIR, day)
        if out_path.exists():
            active_cells, max_mesh_mm = summarize_output_raster(out_path)
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


def qa_repair_existing_outputs() -> dict:
    """Scan Stage 01 GeoTIFFs, repair invalid values, and refresh manifest stats."""
    import rasterio

    manifest_rows = read_manifest_rows_by_date()
    tifs = iter_stage01_tifs()
    repaired_files = 0
    repaired_cells = 0
    active_files = 0
    above_cap_files = 0
    nonfinite_files = 0

    log(f"\n  Stage 01 QA: physical cap = {QA_MAX_HAIL_MM:.1f} mm ({QA_MAX_HAIL_IN:.1f} in)")
    log(f"  Stage 01 QA: scanning {len(tifs):,} GeoTIFFs ...")

    for path in tifs:
        try:
            day = datetime.strptime(path.stem.replace("mesh_", ""), "%Y%m%d").date()
        except ValueError:
            log(f"    WARN: skipping unrecognized Stage 01 filename: {path}")
            continue

        with rasterio.open(path) as src:
            data = src.read(1)

        bad_nonfinite = (~np.isfinite(data)) & (data != OUT_NODATA)
        bad_above_cap = np.isfinite(data) & (data > QA_MAX_HAIL_MM)
        if np.any(bad_nonfinite):
            nonfinite_files += 1
        if np.any(bad_above_cap):
            above_cap_files += 1

        repaired, n_bad = sanitize_mesh_array(data)
        if n_bad:
            write_geotiff(repaired, path)
            repaired_files += 1
            repaired_cells += n_bad

        active_cells, max_mesh_mm = summarize_output_raster(path)
        if active_cells > 0:
            active_files += 1

        row = manifest_rows.get(day.isoformat())
        if row:
            try:
                source_files = int(row.get("source_files") or 0)
            except ValueError:
                source_files = 0
            try:
                read_errors = int(row.get("read_errors") or 0)
            except ValueError:
                read_errors = 0
            row["active_cells_0p05"] = active_cells
            row["max_mesh_mm"] = max_mesh_mm
            row["status"] = classify_mesh_source_day(
                source_files, active_cells, read_errors
            )
            manifest_rows[day.isoformat()] = {
                field: row.get(field, "") for field in MANIFEST_FIELDS
            }

    if manifest_rows:
        write_manifest_rows(manifest_rows)

    log("  Stage 01 QA complete:")
    log(f"    Files repaired:       {repaired_files:,}")
    log(f"    Cells repaired:       {repaired_cells:,}")
    log(f"    Files with nonfinite: {nonfinite_files:,}")
    log(f"    Files above cap:      {above_cap_files:,}")
    log(f"    Files with signal:    {active_files:,}")
    return {
        "files_scanned": len(tifs),
        "files_repaired": repaired_files,
        "cells_repaired": repaired_cells,
        "files_with_nonfinite": nonfinite_files,
        "files_above_cap": above_cap_files,
        "files_with_signal": active_files,
    }

def build_arg_parser() -> argparse.ArgumentParser:
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
    parser.add_argument("--qa-only", action="store_true",
                        help="Repair existing Stage 01 rasters and refresh manifest stats")
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Rebuild manifest_stage01_myrorss.csv from S3 + existing GeoTIFFs",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        metavar="N",
        help="Parallel S3 + NetCDF decode threads per day (default: 8; use 1 for sequential)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.qa_only:
        qa_repair_existing_outputs()
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
    log(f"  Workers:   {args.workers} thread(s) per day (S3 + NetCDF decode)")

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
        qa_repair_existing_outputs()
        ok = validate_outputs()
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
