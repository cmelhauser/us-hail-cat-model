#!/usr/bin/env python3
"""
04b_fill_gridrad_gap.py — Compute MESH75 from GridRad 3D Reflectivity (2012–2019)
==================================================================================
Fills the 2012–2019 gap using GridRad NEXRAD composite reflectivity.

Improvements over the naive approach:
  1. ERA5 gridded freezing levels (from stage 04a) replace the latitude-band
     lookup table, reducing isotherm height error from ~500 m to ~100 m.
  2. GridRad-Severe (5-min temporal resolution) files are prioritized over
     hourly GridRad V3.1/V4.2 when available, capturing short-lived peak
     hail signatures that hourly composites miss.
  3. Output is tagged as GridRad-sourced in a sidecar metadata file so that
     stage 04c can apply cross-calibration independently.

Data Sources
------------
  GridRad V3.1:      NCAR RDA d841000, 1995–2017, hourly, 0.02°
  GridRad V4.2:      NCAR RDA d841000, 2008–2021, hourly, 0.02°
  GridRad-Severe:    NCAR RDA d841006, 2010–2023, 5-min, 0.02°
  ERA5 isotherms:    data/historical/era5/era5_monthly_isotherms_conus.nc (from stage 04a)

SHI → MESH75 Algorithm
-----------------------
  SHI = 0.1 × ∫[H0 to Htop] Wt(H) × E(Z(H)) dH   (Witt et al. 1998)
  MESH75 = 15.096 × SHI^0.206                        (corrected corrigendum 2021)

Output
------
  data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif
  + data/historical/mesh_0.05deg/gridrad_days.txt (list of dates processed from GridRad)

Usage
-----
  python scripts/04b_fill_gridrad_gap.py
  python scripts/04b_fill_gridrad_gap.py --year 2015 --month 5
  python scripts/04b_fill_gridrad_gap.py --check-data
  python scripts/04b_fill_gridrad_gap.py --validate
"""

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, NODATA
    from _io import write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, NODATA
    from scripts._io import write_geotiff
    from scripts._logging import get_logger

GRIDRAD_DIR = DATA_ROOT / "historical" / "gridrad"
GRIDRAD_SEV = DATA_ROOT / "historical" / "gridrad_severe"
ERA5_FILE   = DATA_ROOT / "historical" / "era5" / "era5_monthly_isotherms_conus.nc"
OUT_DIR     = DATA_ROOT / "historical" / "mesh_0.05deg"
LOG_DIR     = LOG_ROOT
LOG_FILE    = LOG_DIR / "04b_fill_gridrad_gap.log"

# Output grid (must match stages 01–02)
OUT_DX      = DX
OUT_NROWS = NROWS
OUT_NCOLS = NCOLS
OUT_LAT_MAX = LAT_MAX
OUT_LON_MIN = LON_MIN
OUT_NODATA  = NODATA

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

log = get_logger("04b_fill_gridrad_gap", LOG_ROOT).info

def load_era5_isotherms():
    """Load ERA5 monthly isotherm heights. Cached globally."""
    global _era5_h0c, _era5_hm20c, _era5_lats, _era5_lons

    if _era5_h0c is not None:
        return

    if not ERA5_FILE.exists():
        log(f"  WARNING: ERA5 isotherm file not found: {ERA5_FILE}")
        log(f"  Run stage 04a first, or using climatological fallback.")
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
    # Check GridRad-Severe first (5-min resolution, ~100 events/yr)
    sev_patterns = [
        GRIDRAD_SEV / f"{day.year}" / f"{day.strftime('%Y%m%d')}" / "*.nc",
        GRIDRAD_SEV / f"{day.year}" / f"nexrad_*_{day.strftime('%Y%m%d')}T*.nc",
    ]
    sev_files = []
    for pat in sev_patterns:
        sev_files.extend(sorted(pat.parent.glob(pat.name)))

    if sev_files:
        return sev_files, "gridrad-severe-5min"

    # Fall back to hourly GridRad
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
        # Try standard variable names
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

    # Pre-filter: find columns with Z ≥ 40 dBZ
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
        if mesh75_mm < 5.0:
            continue

        out_row = int((OUT_LAT_MAX - lat) / OUT_DX)
        out_col = int((lon - OUT_LON_MIN) / OUT_DX)

        if 0 <= out_row < OUT_NROWS and 0 <= out_col < OUT_NCOLS:
            if mesh75_mm > daily_max[out_row, out_col]:
                daily_max[out_row, out_col] = mesh75_mm
                count += 1

    return count

def process_day(day):
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

    write_geotiff(daily_max, out_path)
    peak = float(daily_max.max())
    return {
        "files": len(nc_files), "source": source, "active_cols": total_cols,
        "peak_mesh75_mm": round(peak, 1), "errors": errors,
    }

def iter_dates(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)

def main():
    parser = argparse.ArgumentParser(
        description="Fill 2012-2019 gap with GridRad MESH75 (ERA5 + GridRad-Severe).")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--check-data", action="store_true")
    args = parser.parse_args()

    if args.validate:
        # Simple check
        gap_tifs = sorted(p for p in OUT_DIR.rglob("mesh_????????.tif")
                          if "mesh_2012" <= p.stem <= "mesh_20201013")
        log(f"  Found {len(gap_tifs):,} GridRad gap-fill TIFFs")
        sys.exit(0 if len(gap_tifs) >= 2000 else 1)

    log(f"\n{'='*60}")
    log(f"  GridRad Gap Fill (ERA5 + Severe Priority) — Stage 04b")
    log(f"{'='*60}")
    log(f"  MESH75: {MESH75_A} × SHI^{MESH75_B} (corrected 2021)")

    # Load ERA5 isotherms
    load_era5_isotherms()
    if _era5_h0c is not None:
        log(f"  Freezing levels: ERA5 gridded (0.25°, monthly)")
    else:
        log(f"  Freezing levels: Climatological fallback (latitude-band)")

    # Date range
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

    if args.check_data:
        log("\n  Checking data availability ...")
        total = sev = hourly = missing = 0
        for day in iter_dates(d_start, d_end):
            total += 1
            files, src = find_gridrad_files(day)
            if src == "gridrad-severe-5min":
                sev += 1
            elif src == "gridrad-hourly":
                hourly += 1
            else:
                missing += 1
        log(f"  {total} days: {sev} GridRad-Severe, {hourly} hourly, {missing} missing")
        sys.exit(0)

    # Track which dates use GridRad (for cross-calibration in 04c)
    gridrad_days_file = OUT_DIR / "gridrad_days.txt"
    gridrad_days = []

    all_days = list(iter_dates(d_start, d_end))
    done = skipped = no_data = 0
    peak_mesh = 0.0
    sev_count = hr_count = 0
    t0 = time.time()

    log(f"\n  Processing {len(all_days):,} days ...\n")

    for day in all_days:
        result = process_day(day)

        if result.get("skipped"):
            skipped += 1
            continue
        if result.get("no_data"):
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
        gridrad_days.append(day.strftime("%Y%m%d"))

        if done % 30 == 0 or peak > 50:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(all_days) - done - skipped - no_data) / rate if rate > 0 else 0
            log(f"  [{day}] done={done:,}  src={src}  peak={peak:.0f}mm  "
                f"ETA={time.strftime('%H:%M:%S', time.gmtime(eta))}")

    # Write GridRad days list
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(gridrad_days_file, "w") as f:
        f.write("\n".join(gridrad_days))

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/3600:.1f} hours")
    log(f"  Days processed: {done:,} (Severe-5min: {sev_count}, Hourly: {hr_count})")
    log(f"  Days skipped: {skipped:,}  |  No data: {no_data:,}")
    log(f"  Peak MESH75: {peak_mesh:.1f} mm ({peak_mesh/25.4:.1f} in)")
    log(f"{'='*60}\n")

if __name__ == "__main__":
    main()
