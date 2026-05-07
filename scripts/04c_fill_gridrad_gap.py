#!/usr/bin/env python3
"""
04c_fill_gridrad_gap.py — Compute MESH75 from GridRad 3D Reflectivity (2012–2019)
==================================================================================
Fills the 2012–2019 gap using GridRad NEXRAD composite reflectivity.

This stage is compute-only. It assumes GridRad inputs already exist locally under:

- `data/historical/gridrad/`
- `data/historical/gridrad_severe/`

Use Stage 04b (`scripts/04b_download_gridrad.py`) to retrieve those inputs from
NCAR RDA/GDEX.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
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
    from _io import sanitize_hail_values, write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import (
        REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN,
        NODATA, MAX_HAIL_MM,
    )
    from scripts._io import sanitize_hail_values, write_geotiff
    from scripts._logging import get_logger

GRIDRAD_DIR = DATA_ROOT / "historical" / "gridrad"
GRIDRAD_SEV = DATA_ROOT / "historical" / "gridrad_severe"
ERA5_FILE   = DATA_ROOT / "historical" / "era5" / "era5_monthly_isotherms_conus.nc"
OUT_DIR     = DATA_ROOT / "historical" / "mesh_0.05deg"
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


def find_gridrad_files(day: date) -> tuple:
    """
    Find GridRad files for a day. Returns (files, source_type).
    Prioritizes GridRad-Severe (5-min) over hourly when available.
    """
    sev_patterns = [
        GRIDRAD_SEV / f"{day.year}" / f"{day.strftime('%Y%m%d')}" / "*.nc",
        GRIDRAD_SEV / f"{day.year}" / f"nexrad_*_{day.strftime('%Y%m%d')}T*.nc",
    ]
    sev_files = []
    for pat in sev_patterns:
        sev_files.extend(sorted(pat.parent.glob(pat.name)))
    if sev_files:
        return sev_files, "gridrad-severe-5min"

    hr_patterns = [
        GRIDRAD_DIR / f"{day.year}" / f"{day.strftime('%Y%m%d')}" / "*.nc",
        GRIDRAD_DIR / f"{day.year}" / f"nexrad_*_{day.strftime('%Y%m%d')}T*.nc",
    ]
    hr_files = []
    seen = set()
    for pat in hr_patterns:
        for f in sorted(pat.parent.glob(pat.name)):
            if f not in seen and f.suffix == ".nc":
                hr_files.append(f)
                seen.add(f)
    if hr_files:
        return hr_files, "gridrad-hourly"

    return [], "none"


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

        for refl_name in ["Reflectivity", "reflectivity", "refl"]:
            if refl_name in ds.variables:
                refl = ds.variables[refl_name][:]
                break
        else:
            ds.close()
            return 0

        if hasattr(refl, "filled"):
            refl = refl.filled(np.nan)
    finally:
        ds.close()

    if refl.ndim != 3:
        return 0

    max_refl = np.nanmax(refl, axis=0)
    active = np.argwhere(max_refl >= Z_THRESHOLD)
    count = 0

    for idx in active:
        j, k = int(idx[0]), int(idx[1])
        lat = float(lats[j])
        lon = float(lons[k])

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


def process_day(day):
    load_era5_isotherms()

    out_path = OUT_DIR / f"{day.year}" / f"mesh_{day.strftime('%Y%m%d')}.tif"
    if out_path.exists():
        return {"skipped": True}

    nc_files, source = find_gridrad_files(day)
    if not nc_files:
        return {"files": 0, "no_data": True}

    daily_max = np.zeros((OUT_NROWS, OUT_NCOLS), dtype=np.float32)
    total_cols = errors = 0

    for nc_path in nc_files:
        try:
            n = process_gridrad_file(nc_path, daily_max, day.month)
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
        log(f"    WARN: removed {n_repaired:,} non-finite/out-of-bound cells for {day}")
    write_geotiff(out_data, out_path)
    active = out_data[(out_data > 0) & np.isfinite(out_data)]
    peak = float(active.max()) if active.size else 0.0
    return {
        "files": len(nc_files), "source": source, "active_cols": total_cols,
        "peak_mesh75_mm": round(peak, 1), "errors": errors,
    }


def iter_dates(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fill 2012-2019 gap with GridRad MESH75 (ERA5 + GridRad-Severe).")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--check-data", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        metavar="N",
        help="Parallel worker processes across days (default: 4; use 1 for sequential)",
    )
    return parser


def _process_day_worker(day: date) -> tuple[str, dict]:
    try:
        return day.strftime("%Y%m%d"), process_day(day)
    except Exception as e:
        return day.strftime("%Y%m%d"), {"files": 0, "error": str(e)}


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

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

    log(f"  Period: {d_start} → {d_end}")
    log(f"  Workers: {args.workers} process(es) across days")

    if args.check_data:
        log("\n  Checking data availability ...")
        total = sev = hourly = missing = 0
        for day in iter_dates(d_start, d_end):
            total += 1
            _files, src = find_gridrad_files(day)
            if src == "gridrad-severe-5min":
                sev += 1
            elif src == "gridrad-hourly":
                hourly += 1
            else:
                missing += 1
        log(f"  {total} days: {sev} GridRad-Severe, {hourly} hourly, {missing} missing")
        sys.exit(0)

    gridrad_days_file = OUT_DIR / "gridrad_days.txt"
    gridrad_days = []

    all_days = list(iter_dates(d_start, d_end))
    done = skipped = no_data = 0
    peak_mesh = 0.0
    sev_count = hr_count = 0
    t0 = time.time()

    log(f"\n  Processing {len(all_days):,} days ...\n")

    w = max(1, int(args.workers))
    if w == 1:
        iter_results = ((day.strftime("%Y%m%d"), process_day(day)) for day in all_days)
        pool = None
    else:
        pool = ProcessPoolExecutor(max_workers=w)
        iter_results = pool.map(_process_day_worker, all_days)

    try:
        for ymd, result in iter_results:
            if result.get("skipped"):
                skipped += 1
                continue
            if result.get("no_data"):
                no_data += 1
                continue
            if result.get("error"):
                log(f"    WARN: {ymd}: {result['error']}")
                no_data += 1
                continue

            done += 1
            src = result.get("source", "")
            if "severe" in src:
                sev_count += 1
            else:
                hr_count += 1

            peak = result.get("peak_mesh75_mm", 0.0)
            peak_mesh = max(peak_mesh, peak)
            gridrad_days.append(ymd)

            if done % 30 == 0 or peak > 50:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(all_days) - done - skipped - no_data) / rate if rate > 0 else 0
                log(
                    f"  [{ymd}] done={done:,}  src={src}  peak={peak:.0f}mm  "
                    f"ETA={time.strftime('%H:%M:%S', time.gmtime(eta))}"
                )
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=False)

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

