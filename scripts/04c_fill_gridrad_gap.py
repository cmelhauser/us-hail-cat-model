#!/usr/bin/env python3
"""
04c_fill_gridrad_gap.py — Compute MESH75 from GridRad 3D reflectivity (2012–2020-10-13)
========================================================================================
Fills the MYRORSS–MRMS gap using GridRad NEXRAD composite reflectivity (dBZ).
Uses sparse Reflectivity(Index) + index; Nradecho is not used for SHI.

Inputs are read from:

- `data/historical/gridrad/`
- `data/historical/gridrad_severe/`

**Convective day (v2.2):** each ``mesh_YYYYMMDD.tif`` is the cell-wise maximum MESH75
over **12 UTC → 12 UTC** (label = date at window start). Timesteps from two UTC
calendar archives may contribute (e.g. label ``20160721`` uses 2016-07-21 12:00Z
through 2016-07-22 12:00Z).

**Default run shape (memory / disk):** days are processed **sequentially** (``--workers 1``).
After each convective day finishes (written, skipped, no-data, or error), staged GridRad
NetCDF trees for that day are removed unless you pass ``--keep-gridrad-inputs``.

**Single-pass pipeline:** ``--with-04b-download`` runs Stage 04b’s per-day download
immediately before processing each day, then deletes the staged NetCDFs (unless
``--keep-gridrad-inputs``). Downloads use a **severe-first** policy: GridRad-Severe
(5-min) is fetched when the catalog lists it for the convective window; regular
hourly GridRad is skipped unless severe is unavailable or does not cover the full
12 UTC → 12 UTC window (hourly then fills gaps: **d841000** V3.1, then **d841001**
V4.2 warm-season hourly for Apr–Aug 2018+ when V3.1 is empty). With ``--workers 1`` this is
strictly sequential. With ``--workers N`` and ``N > 1``, up to ``N`` convective days
run in parallel worker processes (04b is loaded once per worker; each day uses a
fresh HTTP session); tune ``--04b-download-workers`` so ``N × download_workers``
stays within NCAR throttling guidance.

Stage 04a (``era5_monthly_isotherms_conus.nc``) must exist before SHI computation.

Output manifest (same schema as Stage 01):

  data/historical/mesh_0.05deg/manifest_stage04c_gridrad.csv
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta
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
        convective_window_coverage_ok,
        count_plain_and_compressed_sources,
        mesh_manifest_row,
        mesh_path_for_convective_day,
        observation_in_convective_day,
        observation_times_from_paths,
        observation_utc_to_convective_day,
        parse_observation_utc_from_name,
        sanitize_hail_values,
        staged_nc_files_for_convective_day,
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
        convective_window_coverage_ok,
        count_plain_and_compressed_sources,
        mesh_manifest_row,
        mesh_path_for_convective_day,
        observation_in_convective_day,
        observation_times_from_paths,
        observation_utc_to_convective_day,
        parse_observation_utc_from_name,
        sanitize_hail_values,
        staged_nc_files_for_convective_day,
        summarize_mesh_output_raster,
        upsert_mesh_manifest_row,
        write_geotiff,
    )
    from scripts._logging import get_logger

GRIDRAD_DIR = DATA_ROOT / "historical" / "gridrad"
GRIDRAD_SEV = DATA_ROOT / "historical" / "gridrad_severe"
ERA5_FILE   = DATA_ROOT / "historical" / "era5" / "era5_monthly_isotherms_conus.nc"
OUT_DIR     = DATA_ROOT / "historical" / "mesh_0.05deg"
MANIFEST_FILE = OUT_DIR / "manifest_stage04c_gridrad.csv"
LOG_DIR     = LOG_ROOT
LOG_FILE    = LOG_DIR / "04c_fill_gridrad_gap.log"

# Output grid (must match stages 01–02)
OUT_DX      = DX
OUT_NROWS = NROWS
OUT_NCOLS = NCOLS
OUT_LAT_MAX = LAT_MAX
OUT_LON_MIN = LON_MIN
OUT_NODATA  = NODATA
QA_MAX_HAIL_MM = MAX_HAIL_MM

# MESH75 coefficients (corrected 2021 corrigendum)
MESH75_A = 15.096
MESH75_B = 0.206

# SHI constants
Z_THRESHOLD = 40.0     # dBZ minimum
E_COEFF     = 5e-6
E_EXPONENT  = 0.084

# Date range
GAP_START = date(2012, 1, 1)
GAP_END   = date(2020, 10, 13)

# ERA5 isotherm cache (loaded once)
_era5_h0c = None
_era5_hm20c = None
_era5_lats = None
_era5_lons = None

log = get_logger("04c_fill_gridrad_gap", LOG_ROOT).info

# Populated in ProcessPool worker processes when using --with-04b-download with --workers > 1.
_worker_04b_mod = None


def load_era5_isotherms():
    """Load ERA5 monthly isotherm heights. Cached globally."""
    global _era5_h0c, _era5_hm20c, _era5_lats, _era5_lons

    if _era5_h0c is not None:
        return

    if not ERA5_FILE.exists():
        log(f"  WARNING: ERA5 isotherm file not found: {ERA5_FILE}")
        log("  Run stage 04a first, or using climatological fallback.")
        return

    import xarray as xr
    ds = xr.open_dataset(ERA5_FILE)
    _era5_h0c   = ds["h_0C_km"].values       # (12, lat, lon)
    _era5_hm20c = ds["h_m20C_km"].values
    _era5_lats  = ds["latitude"].values
    _era5_lons  = ds["longitude"].values
    ds.close()
    log(f"  Loaded ERA5 isotherms: {_era5_h0c.shape}")


def get_freezing_levels_era5(lat: float, lon: float, month: int) -> tuple:
    """Get 0°C and -20°C heights from ERA5 gridded data."""
    if _era5_h0c is None:
        # Fallback to simple climatological estimate
        return _get_freezing_levels_climo(lat, month)

    # Find nearest ERA5 grid cell
    j = np.argmin(np.abs(_era5_lats - lat))
    k = np.argmin(np.abs(_era5_lons - lon))
    m = month - 1  # 0-indexed

    h0c  = float(_era5_h0c[m, j, k])
    hm20 = float(_era5_hm20c[m, j, k])

    # Sanity bounds
    h0c  = max(0.5, min(7.0, h0c))
    hm20 = max(h0c + 1.0, min(12.0, hm20))

    return h0c, hm20


def _get_freezing_levels_climo(lat: float, month: int) -> tuple:
    """Climatological fallback (same as original stage 04)."""
    CLIMO = {
        1: {(24,32):(2.8,5.5),(32,38):(2.0,4.8),(38,44):(1.5,4.2),(44,51):(1.0,3.8)},
        2: {(24,32):(3.0,5.6),(32,38):(2.2,5.0),(38,44):(1.6,4.3),(44,51):(1.1,3.9)},
        3: {(24,32):(3.5,6.0),(32,38):(2.8,5.5),(38,44):(2.2,4.8),(44,51):(1.7,4.3)},
        4: {(24,32):(4.0,6.5),(32,38):(3.3,6.0),(38,44):(2.8,5.5),(44,51):(2.3,4.8)},
        5: {(24,32):(4.5,7.0),(32,38):(3.8,6.5),(38,44):(3.3,6.0),(44,51):(2.8,5.5)},
        6: {(24,32):(4.8,7.3),(32,38):(4.2,7.0),(38,44):(3.8,6.5),(44,51):(3.3,6.0)},
        7: {(24,32):(5.0,7.5),(32,38):(4.5,7.2),(38,44):(4.0,6.8),(44,51):(3.5,6.3)},
        8: {(24,32):(5.0,7.5),(32,38):(4.5,7.2),(38,44):(4.0,6.8),(44,51):(3.5,6.3)},
        9: {(24,32):(4.8,7.3),(32,38):(4.0,6.8),(38,44):(3.5,6.3),(44,51):(3.0,5.8)},
        10:{(24,32):(4.2,6.8),(32,38):(3.5,6.2),(38,44):(2.8,5.5),(44,51):(2.2,5.0)},
        11:{(24,32):(3.5,6.2),(32,38):(2.8,5.5),(38,44):(2.0,4.8),(44,51):(1.5,4.2)},
        12:{(24,32):(3.0,5.7),(32,38):(2.2,5.0),(38,44):(1.6,4.3),(44,51):(1.1,3.9)},
    }
    bands = CLIMO.get(month, CLIMO[6])
    for (lo, hi), (h0, hm20) in bands.items():
        if lo <= lat < hi:
            return h0, hm20
    return 3.5, 6.0


def _convective_stage_dir(base: Path, convective_day: date) -> Path:
    return base / "by_convective_day" / convective_day.strftime("%Y%m%d")


def delete_gridrad_inputs_for_day(convective_day: date) -> None:
    """Remove staged GridRad inputs for one convective day (12Z–12Z window)."""
    for base in (GRIDRAD_DIR, GRIDRAD_SEV):
        d = _convective_stage_dir(base, convective_day)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def compute_shi_column(z_profile, heights_km, h_0c, h_m20c):
    """Compute SHI for a single vertical column (Witt et al. 1998)."""
    shi = 0.0
    dh = 1000.0  # 1 km vertical step in meters

    for z_dbz, h_km in zip(z_profile, heights_km):
        if np.isnan(z_dbz) or z_dbz < Z_THRESHOLD or h_km < h_0c:
            continue

        wt = 1.0 if h_km >= h_m20c else max(0.0, (h_km - h_0c) / max(h_m20c - h_0c, 0.1))
        e = E_COEFF * (10.0 ** (E_EXPONENT * z_dbz)) * wt
        shi += wt * e * dh

    return 0.1 * shi


def _hourly_fill_for_severe_gaps(
    hourly_files: list[Path],
    severe_times: list,
    convective_day: date,
    *,
    proximity_minutes: float = 3.0,
) -> list[Path]:
    """Hourly timesteps not already represented by nearby severe (5-min) observations."""
    if not hourly_files:
        return []
    prox = proximity_minutes * 60.0
    fill: list[Path] = []
    for path in hourly_files:
        obs = parse_observation_utc_from_name(path.name)
        if obs is None or not observation_in_convective_day(obs, convective_day):
            continue
        covered = any(abs((obs - st).total_seconds()) <= prox for st in severe_times)
        if not covered:
            fill.append(path)
    return fill


def _hourly_source_label(hr_files: list[Path]) -> str:
    """Provenance tag for staged hourly GridRad NetCDFs."""
    if not hr_files:
        return "gridrad-hourly"
    names = [p.name for p in hr_files]
    if all("v4_2" in n for n in names):
        return "gridrad-hourly-v42"
    if all("v3_1" in n for n in names):
        return "gridrad-hourly-v31"
    return "gridrad-hourly"


def find_gridrad_files(convective_day: date) -> tuple:
    """
    Find staged GridRad files for a convective day (12 UTC → 12 UTC).

    Prefer GridRad-Severe (5-min). Use hourly only when severe is absent, or to
    fill timesteps not covered by staged severe after a partial severe download.
    """
    sev_files = staged_nc_files_for_convective_day(GRIDRAD_SEV, convective_day)
    hr_files = staged_nc_files_for_convective_day(GRIDRAD_DIR, convective_day)
    sev_times = observation_times_from_paths(sev_files, convective_day)

    if sev_files and convective_window_coverage_ok(
        sev_times,
        convective_day,
        max_gap_minutes=15.0,
    ):
        return sev_files, "gridrad-severe-5min"

    if sev_files and hr_files:
        fill = _hourly_fill_for_severe_gaps(hr_files, sev_times, convective_day)
        if fill:
            return sorted(sev_files + fill), "gridrad-severe-5min+hourly-fill"
        return sev_files, "gridrad-severe-5min"

    if sev_files:
        return sev_files, "gridrad-severe-5min"

    if hr_files:
        return hr_files, _hourly_source_label(hr_files)

    return [], "none"


def _read_var_array(ds, name: str) -> np.ndarray:
    data = ds.variables[name][:]
    return data.filled(np.nan) if hasattr(data, "filled") else np.asarray(data)


def _load_reflectivity_3d(ds) -> np.ndarray | None:
    """
    Load reflectivity (dBZ) on (altitude, lat, lon).

    GridRad v3/v4 store the physical field as sparse ``Reflectivity(Index)``.
    ``Nradecho`` is a 3-D mask/count (typically 0–35), not dBZ — do not use it here.
    """
    if "Reflectivity" in ds.variables:
        dense = _read_var_array(ds, "Reflectivity")
        if dense.ndim == 3:
            return dense

    if "Reflectivity" not in ds.variables or "index" not in ds.variables:
        return None

    sparse = _read_var_array(ds, "Reflectivity")
    if sparse.ndim != 1:
        return None

    idx = _read_var_array(ds, "index").astype(np.int64)
    alts = _read_var_array(ds, "Altitude")
    lats = _read_var_array(ds, "Latitude")
    lons = _read_var_array(ds, "Longitude")
    na, nlat, nlon = len(alts), len(lats), len(lons)
    n = min(len(idx), len(sparse))
    if n == 0:
        return None

    flat = idx[:n]
    vals = sparse[:n].astype(np.float32)
    i = flat % nlon
    jj = (flat // nlon) % nlat
    kk = flat // (nlon * nlat)
    valid = (
        (kk >= 0) & (kk < na) & (jj >= 0) & (jj < nlat) & (i >= 0) & (i < nlon) & np.isfinite(vals)
    )
    if not np.any(valid):
        return None

    grid = np.full((na, nlat, nlon), -np.inf, dtype=np.float32)
    np.maximum.at(grid, (kk[valid], jj[valid], i[valid]), vals[valid])
    grid[~np.isfinite(grid)] = np.nan
    grid[grid == -np.inf] = np.nan
    return grid


def process_gridrad_file(nc_path, daily_max, month):
    """Process a single GridRad NetCDF: compute SHI → MESH75, update daily_max."""
    import netCDF4

    ds = netCDF4.Dataset(nc_path, "r")
    try:
        for lat_name in ["Latitude", "latitude", "lat"]:
            if lat_name in ds.variables:
                lats = ds.variables[lat_name][:]
                break
        else:
            ds.close()
            return 0

        for lon_name in ["Longitude", "longitude", "lon"]:
            if lon_name in ds.variables:
                lons = ds.variables[lon_name][:]
                break
        else:
            ds.close()
            return 0

        for alt_name in ["Altitude", "altitude", "alt"]:
            if alt_name in ds.variables:
                alts = ds.variables[alt_name][:]
                break
        else:
            ds.close()
            return 0

        refl = _load_reflectivity_3d(ds)
        if refl is None:
            ds.close()
            return 0
    finally:
        ds.close()

    max_refl = np.nanmax(refl, axis=0)
    active = np.argwhere(max_refl >= Z_THRESHOLD)
    count = 0

    for idx in active:
        j, k = int(idx[0]), int(idx[1])
        lat = float(lats[j])
        lon = float(lons[k])
        if lon > 180.0:
            lon -= 360.0

        if not (24.0 <= lat <= 50.0 and -125.0 <= lon <= -66.0):
            continue

        h_0c, h_m20c = get_freezing_levels_era5(lat, lon, month)
        z_profile = refl[:, j, k]
        shi = compute_shi_column(z_profile, alts, h_0c, h_m20c)
        if shi <= 0:
            continue

        mesh75_mm = MESH75_A * (shi ** MESH75_B)
        if not np.isfinite(mesh75_mm) or mesh75_mm < 5.0 or mesh75_mm > QA_MAX_HAIL_MM:
            continue

        out_row = int((OUT_LAT_MAX - lat) / OUT_DX)
        out_col = int((lon - OUT_LON_MIN) / OUT_DX)
        if 0 <= out_row < OUT_NROWS and 0 <= out_col < OUT_NCOLS:
            if mesh75_mm > daily_max[out_row, out_col]:
                daily_max[out_row, out_col] = mesh75_mm
                count += 1

    return count


def summarize_gridrad_formats(nc_files: list) -> tuple[int, int]:
    """Return plain vs gzipped NetCDF counts for manifest columns."""
    names = [p.name for p in nc_files]
    return count_plain_and_compressed_sources(
        names,
        plain_suffixes=(".nc",),
        compressed_suffixes=(".nc.gz",),
    )


def upsert_manifest_row(row: dict) -> None:
    upsert_mesh_manifest_row(MANIFEST_FILE, row)


def manifest_row_for_day(
    convective_day: date,
    out_path: Path,
    nc_files: list,
    *,
    source_pixels: int | None,
    active_cells: int,
    max_mesh_mm: float,
    read_errors: int | None = None,
    skipped: bool = False,
) -> dict:
    plain_count, gz_count = summarize_gridrad_formats(nc_files)
    status = classify_mesh_source_day(
        len(nc_files), active_cells, read_errors or 0
    )
    return mesh_manifest_row(
        convective_day,
        out_path,
        REPO_ROOT,
        source_files=len(nc_files),
        plain_count=plain_count,
        gz_count=gz_count,
        source_pixels=source_pixels,
        active_cells=active_cells,
        max_mesh_mm=max_mesh_mm,
        status=status,
        skipped=skipped,
        read_errors=read_errors,
    )


def process_day(convective_day: date):
    load_era5_isotherms()

    out_path = mesh_path_for_convective_day(OUT_DIR, convective_day)
    nc_files, _source = find_gridrad_files(convective_day)

    if out_path.exists():
        active_cells, max_mesh_mm = summarize_mesh_output_raster(
            out_path, max_hail_mm=QA_MAX_HAIL_MM
        )
        upsert_manifest_row(manifest_row_for_day(
            convective_day,
            out_path,
            nc_files,
            source_pixels=None,
            active_cells=active_cells,
            max_mesh_mm=max_mesh_mm,
            skipped=True,
        ))
        return {"skipped": True, "active_cells": active_cells, "max_mesh_mm": max_mesh_mm}

    if not nc_files:
        upsert_manifest_row(manifest_row_for_day(
            convective_day,
            out_path,
            nc_files,
            source_pixels=0,
            active_cells=0,
            max_mesh_mm=0.0,
            read_errors=0,
        ))
        return {"files": 0, "no_data": True}

    source = _source
    daily_max = np.zeros((OUT_NROWS, OUT_NCOLS), dtype=np.float32)
    total_cols = errors = 0

    for nc_path in nc_files:
        try:
            n = process_gridrad_file(nc_path, daily_max, convective_day.month)
            total_cols += n
        except Exception as e:
            errors += 1
            if errors <= 3:
                log(f"    WARN: {nc_path.name}: {e}")

    out_data, n_repaired = sanitize_hail_values(
        daily_max,
        max_hail_mm=QA_MAX_HAIL_MM,
        nodata=OUT_NODATA,
    )
    if n_repaired:
        log(f"    WARN: removed {n_repaired:,} non-finite/out-of-bound cells for {convective_day}")
    active = out_data[(out_data > 0) & np.isfinite(out_data)]
    peak = float(active.max()) if active.size else 0.0
    n_active = int(active.size)
    write_geotiff(
        out_data,
        out_path,
        tags={
            "PRODUCT": "MESH75",
            "DATE": convective_day.isoformat(),
            "CONVECTIVE_WINDOW_UTC": convective_day_window_tag(convective_day),
            "SOURCE": source,
            "MAX_MESH75_MM": f"{peak:.2f}",
            "MAX_MESH75_IN": f"{peak / 25.4:.3f}",
            "ACTIVE_CELLS": str(n_active),
        },
    )
    max_mesh_mm = round(peak, 1)
    upsert_manifest_row(manifest_row_for_day(
        convective_day,
        out_path,
        nc_files,
        source_pixels=total_cols,
        active_cells=n_active,
        max_mesh_mm=max_mesh_mm,
        read_errors=errors,
    ))
    return {
        "files": len(nc_files),
        "source": source,
        "active_cols": total_cols,
        "active_cells": n_active,
        "peak_mesh75_mm": max_mesh_mm,
        "errors": errors,
        "tif": str(out_path),
    }


def rebuild_manifest_from_outputs(d_start: date, d_end: date) -> int:
    """Upsert manifest rows from staged GridRad files and existing GeoTIFFs."""
    n = 0
    for day in iter_dates(d_start, d_end):
        nc_files, _ = find_gridrad_files(day)
        out_path = mesh_path_for_convective_day(OUT_DIR, day)
        if out_path.exists():
            active_cells, max_mesh_mm = summarize_mesh_output_raster(
                out_path, max_hail_mm=QA_MAX_HAIL_MM
            )
            upsert_manifest_row(manifest_row_for_day(
                day,
                out_path,
                nc_files,
                source_pixels=None,
                active_cells=active_cells,
                max_mesh_mm=max_mesh_mm,
                skipped=True,
            ))
        elif not nc_files:
            upsert_manifest_row(manifest_row_for_day(
                day,
                out_path,
                nc_files,
                source_pixels=0,
                active_cells=0,
                max_mesh_mm=0.0,
                read_errors=0,
            ))
        else:
            continue
        n += 1
    return n


def iter_dates(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_iso_date(value: str) -> date:
    """Parse ``YYYY-MM-DD`` for CLI bounds."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def filter_days_for_run(
    days: list[date],
    *,
    missing_only: bool,
) -> list[date]:
    """Keep only convective days that still need a GeoTIFF when ``missing_only``."""
    if not missing_only:
        return days
    pending: list[date] = []
    for day in days:
        if not mesh_path_for_convective_day(OUT_DIR, day).exists():
            pending.append(day)
    return pending


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fill 2012-2019 gap with GridRad MESH75 (ERA5 + GridRad-Severe).")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--check-data", action="store_true")
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Rebuild manifest_stage04c_gridrad.csv from staged inputs + GeoTIFFs",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Parallel worker processes across days (default: 1; use 4+ only if RAM allows)",
    )
    parser.add_argument(
        "--keep-gridrad-inputs",
        action="store_true",
        help="Do not delete local GridRad / GridRad-Severe NetCDF trees after each day.",
    )
    parser.add_argument(
        "--with-04b-download",
        action="store_true",
        help=(
            "For each day: run Stage 04b download, then process this day. "
            "Compatible with --workers > 1 (each worker process uses its own session)."
        ),
    )
    parser.add_argument(
        "--04b-download-workers",
        type=int,
        default=1,
        metavar="N",
        dest="download_workers",
        help="With --with-04b-download: parallel download threads per day (default: 1).",
    )
    parser.add_argument(
        "--from-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive convective-day start (overrides --year/--month lower bound).",
    )
    parser.add_argument(
        "--until-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive convective-day end (overrides --year/--month upper bound).",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Process only days without an output GeoTIFF (backfill retries).",
    )
    return parser


def _load_04b_module():
    """Load Stage 04b without a package import path (matches run_pipeline subprocess style)."""
    p = Path(__file__).resolve().parent / "04b_download_gridrad.py"
    spec = importlib.util.spec_from_file_location("b04_gridrad_dl", p)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load 04b_download_gridrad.py")
    mod = importlib.util.module_from_spec(spec)
    # Required so dataclasses / typing can resolve cls.__module__ when 04b is
    # exec'd in worker processes (importlib does not auto-register until post-exec).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _process_day_worker(day: date) -> tuple[str, dict]:
    try:
        return day.strftime("%Y%m%d"), process_day(day)
    except Exception as e:
        return day.strftime("%Y%m%d"), {"files": 0, "error": str(e)}


def _04c_pool_init_load_04b() -> None:
    """ProcessPool initializer: load Stage 04b once per worker process."""
    global _worker_04b_mod
    _worker_04b_mod = _load_04b_module()


def _run_one_day_download_then_process(
    spec: tuple[date, bool, int],
) -> tuple[str, dict]:
    """
    ProcessPool entry: ``(day, with_04b_download, download_workers)``.

    With ``--workers > 1``, the pool initializer sets ``_worker_04b_mod`` so each
    worker process loads 04b once. Each day still uses a fresh ``requests.Session``.
    """
    day, with_04b_download, download_workers = spec
    ymd = day.strftime("%Y%m%d")
    out_path = mesh_path_for_convective_day(OUT_DIR, day)
    try:
        if with_04b_download and not out_path.exists():
            b04 = _worker_04b_mod if _worker_04b_mod is not None else _load_04b_module()
            sess = b04._request_session()
            try:
                cat_t = (30.0, 180.0)
                b04.download_for_day_adaptive(
                    sess,
                    day,
                    catalog_timeout=cat_t,
                    connect_timeout=30.0,
                    read_timeout=900.0,
                    max_workers=max(1, int(download_workers)),
                )
            finally:
                sess.close()
        return ymd, process_day(day)
    except Exception as e:
        return ymd, {"files": 0, "error": str(e)}


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.manifest_only:
        if args.year and args.month:
            import calendar
            d_start = date(args.year, args.month, 1)
            d_end = date(args.year, args.month,
                         calendar.monthrange(args.year, args.month)[1])
            d_start = max(d_start, GAP_START)
            d_end = min(d_end, GAP_END)
        elif args.year:
            d_start = max(date(args.year, 1, 1), GAP_START)
            d_end = min(date(args.year, 12, 31), GAP_END)
        else:
            d_start = GAP_START
            d_end = GAP_END
        n = rebuild_manifest_from_outputs(d_start, d_end)
        log(f"  Manifest rows upserted: {n:,} → {MANIFEST_FILE}")
        sys.exit(0)

    if args.validate:
        import rasterio
        gap_tifs = sorted(p for p in OUT_DIR.rglob("mesh_????????.tif")
                          if "mesh_2012" <= p.stem <= "mesh_20201013")
        log(f"  Found {len(gap_tifs):,} GridRad gap-fill TIFFs")
        errors = []
        if len(gap_tifs) < 2000:
            errors.append(f"Too few GridRad gap-fill TIFFs: {len(gap_tifs)}")
        for p in gap_tifs:
            try:
                with rasterio.open(p) as src:
                    data = src.read(1)
                invalid = (~np.isfinite(data)) | (data < 0) | (data > QA_MAX_HAIL_MM)
                if np.any(invalid):
                    errors.append(
                        f"Invalid GridRad MESH75 values in {p.name}: "
                        f"{int(np.count_nonzero(invalid)):,} cells outside "
                        f"[0, {QA_MAX_HAIL_MM:.1f}] mm"
                    )
            except Exception as e:
                errors.append(f"Cannot read {p.name}: {e}")
        if errors:
            log("CRITICAL: Validation FAILED:")
            for err in errors[:50]:
                log(f"  ✗ {err}")
            sys.exit(1)
        log("Output validation passed ✓")
        sys.exit(0)

    log(f"\n{'='*60}")
    log("  GridRad Gap Fill (ERA5 + Severe Priority) — Stage 04c")
    log(f"{'='*60}")
    log(f"  MESH75: {MESH75_A} × SHI^{MESH75_B} (corrected 2021)")

    load_era5_isotherms()
    if _era5_h0c is not None:
        log("  Freezing levels: ERA5 gridded (0.25°, monthly)")
    else:
        log("  Freezing levels: Climatological fallback (latitude-band)")

    if args.year and args.month:
        import calendar
        d_start = date(args.year, args.month, 1)
        d_end = date(args.year, args.month,
                     calendar.monthrange(args.year, args.month)[1])
        d_start = max(d_start, GAP_START)
        d_end = min(d_end, GAP_END)
    elif args.year:
        d_start = max(date(args.year, 1, 1), GAP_START)
        d_end = min(date(args.year, 12, 31), GAP_END)
    else:
        d_start = GAP_START
        d_end = GAP_END

    if args.from_date:
        d_start = max(parse_iso_date(args.from_date), GAP_START)
    if args.until_date:
        d_end = min(parse_iso_date(args.until_date), GAP_END)

    log(f"  Period: {d_start} → {d_end}")
    log(f"  Workers: {args.workers} process(es) across days")
    log(f"  With 04b: {args.with_04b_download}")
    log(f"  Missing only: {args.missing_only}")
    log(f"  Delete GridRad inputs after each day: {not args.keep_gridrad_inputs}")

    if args.check_data:
        log("\n  Checking data availability ...")
        total = sev = hourly_v31 = hourly_v42 = hourly_other = missing = 0
        for day in iter_dates(d_start, d_end):
            total += 1
            _files, src = find_gridrad_files(day)
            if src == "gridrad-severe-5min":
                sev += 1
            elif src == "gridrad-hourly-v31":
                hourly_v31 += 1
            elif src == "gridrad-hourly-v42":
                hourly_v42 += 1
            elif src.startswith("gridrad-hourly"):
                hourly_other += 1
            elif "severe" in src:
                sev += 1
            else:
                missing += 1
        log(
            f"  {total} days: {sev} GridRad-Severe, "
            f"{hourly_v31} hourly V3.1, {hourly_v42} hourly V4.2, "
            f"{hourly_other} hourly (mixed), {missing} missing"
        )
        sys.exit(0)

    gridrad_days_file = OUT_DIR / "gridrad_days.txt"
    gridrad_days = []

    all_days = filter_days_for_run(
        list(iter_dates(d_start, d_end)),
        missing_only=args.missing_only,
    )
    done = skipped = no_data = 0
    peak_mesh = 0.0
    sev_count = hr_count = 0
    t0 = time.time()

    log(f"\n  Processing {len(all_days):,} days ...\n")
    if args.missing_only and not all_days:
        log("  No missing-output days in range; nothing to do.")
        sys.exit(0)

    w = max(1, int(args.workers))
    if args.with_04b_download and w > 1:
        dw = max(1, int(args.download_workers))
        est = w * dw
        log(
            "  NOTE: --with-04b-download with multiple day workers: each worker uses "
            "its own HTTP session. Rough peak in-flight GETs ≈ "
            f"(--workers) × (--04b-download-workers) = {w} × {dw} = {est}. "
            "Stay within NCAR/GDEX throttling (often ≤10 concurrent streams per account)."
        )

    b04 = b_sess = None
    if args.with_04b_download and w == 1:
        b04 = _load_04b_module()
        b_sess = b04._request_session()

    def _peak_from_tif(tif_path: Path) -> tuple[float, int]:
        """Read daily max hail diagnostic from GeoTIFF tags or raster values."""
        try:
            import rasterio
            with rasterio.open(tif_path) as src:
                tags = src.tags() or {}
                if "MAX_MESH75_MM" in tags:
                    peak = float(tags["MAX_MESH75_MM"])
                    active = int(tags.get("ACTIVE_CELLS", 0))
                    return peak, active
                data = src.read(1)
            active = data[(data > 0) & np.isfinite(data)]
            return (float(active.max()) if active.size else 0.0, int(active.size))
        except Exception:
            return 0.0, 0

    def _finalize_day(day: date, ymd: str, result: dict) -> None:
        nonlocal done, skipped, no_data, peak_mesh, sev_count, hr_count
        tif_path = OUT_DIR / f"{day.year}" / f"mesh_{ymd}.tif"
        if result.get("skipped"):
            skipped += 1
            if tif_path.exists():
                peak, n_active = _peak_from_tif(tif_path)
                peak_mesh = max(peak_mesh, peak)
                log(
                    f"  [{ymd}] skipped (exists)  max_mesh75={peak:.1f} mm "
                    f"({peak / 25.4:.2f} in)  active_cells={n_active:,}"
                )
            else:
                log(f"  [{ymd}] skipped")
        elif result.get("no_data"):
            no_data += 1
            log(f"  [{ymd}] no_data (no GridRad inputs)")
        elif result.get("error"):
            log(f"  [{ymd}] ERROR: {result['error']}")
            no_data += 1
        else:
            done += 1
            src = result.get("source", "")
            if "severe" in src:
                sev_count += 1
            elif src == "gridrad-hourly" or src.startswith("gridrad-hourly"):
                hr_count += 1
            peak = float(result.get("peak_mesh75_mm", 0.0))
            n_active = int(result.get("active_cells", 0))
            peak_mesh = max(peak_mesh, peak)
            gridrad_days.append(ymd)
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            remaining = len(all_days) - done - skipped - no_data
            eta = remaining / rate if rate > 0 else 0.0
            log(
                f"  [{ymd}] wrote {tif_path.name}  max_mesh75={peak:.1f} mm "
                f"({peak / 25.4:.2f} in)  active_cells={n_active:,}  "
                f"src={src}  done={done:,}  ETA={time.strftime('%H:%M:%S', time.gmtime(eta))}"
            )
        if not args.keep_gridrad_inputs:
            delete_gridrad_inputs_for_day(day)

    try:
        if w == 1:
            for day in all_days:
                ymd = day.strftime("%Y%m%d")
                out_path = mesh_path_for_convective_day(OUT_DIR, day)
                try:
                    if args.with_04b_download and not out_path.exists():
                        cat_t = (30.0, 180.0)
                        b04.download_for_day_adaptive(
                            b_sess,
                            day,
                            catalog_timeout=cat_t,
                            connect_timeout=30.0,
                            read_timeout=900.0,
                            max_workers=max(1, int(args.download_workers)),
                        )
                    result = process_day(day)
                except Exception as e:
                    result = {"files": 0, "error": str(e)}
                _finalize_day(day, ymd, result)
        else:
            if args.with_04b_download:
                pool = ProcessPoolExecutor(
                    max_workers=w,
                    initializer=_04c_pool_init_load_04b,
                )
                specs = [
                    (day, True, int(args.download_workers)) for day in all_days
                ]
                pairs = pool.map(_run_one_day_download_then_process, specs)
            else:
                pool = ProcessPoolExecutor(max_workers=w)
                pairs = pool.map(_process_day_worker, all_days)
            try:
                for day, (ymd, result) in zip(all_days, pairs):
                    _finalize_day(day, ymd, result)
            finally:
                pool.shutdown(cancel_futures=False)
    finally:
        if b_sess is not None:
            b_sess.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(gridrad_days_file, "w") as f:
        f.write("\n".join(sorted(gridrad_days)))

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/3600:.1f} hours")
    log(f"  Days processed: {done:,} (Severe-5min: {sev_count}, Hourly: {hr_count})")
    log(f"  Days skipped: {skipped:,}  |  No data: {no_data:,}")
    log(f"  Peak MESH75: {peak_mesh:.1f} mm ({peak_mesh/25.4:.1f} in)")
    log(f"{'='*60}\n")


if __name__ == "__main__":
    main()

