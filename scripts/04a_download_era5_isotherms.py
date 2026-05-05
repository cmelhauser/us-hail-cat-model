#!/usr/bin/env python3
"""
04a_download_era5_isotherms.py — ERA5 Monthly Freezing Level Heights
=====================================================================
Downloads ERA5 monthly-mean temperature on pressure levels over CONUS,
then interpolates to find the 0°C and −20°C isotherm heights (km AGL)
for each month and grid cell.

Output: a single NetCDF file with dimensions (month, lat, lon) and
variables h_0C_km and h_m20C_km — the monthly mean heights of the
0°C and −20°C isotherms in km above ground level.

This reduces the ~500 m freezing level error from a latitude-band
climatological lookup to ~100 m from gridded ERA5 reanalysis.

Prerequisites
-------------
  1. Free Copernicus CDS account: https://cds.climate.copernicus.eu
  2. API key in ~/.cdsapirc:
       url: https://cds.climate.copernicus.eu/api
       key: <YOUR-PERSONAL-ACCESS-TOKEN>
  3. Accepted CDS licence terms for the ERA5 pressure-level and single-level
     monthly mean datasets.
  4. pip install cdsapi

The pressure-level request is downloaded in reusable yearly chunks. If the
Copernicus CDS cost limit rejects a yearly request, the script automatically
falls back to monthly chunks for that year. Stage 04a computes the monthly
climatology directly from those cached chunks so it does not need to materialize
a large combined raw NetCDF.

Output
------
  data/historical/era5/era5_monthly_isotherms_conus.nc
    Dimensions: month (12), latitude, longitude
    Variables:  h_0C_km, h_m20C_km, surface_geopotential_m

Usage
-----
  python scripts/04a_download_era5_isotherms.py
  python scripts/04a_download_era5_isotherms.py --validate
"""

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

try:
    from _config import DATA_ROOT, LOG_ROOT
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import DATA_ROOT, LOG_ROOT
    from scripts._logging import get_logger

ERA5_DIR  = DATA_ROOT / "historical" / "era5"
OUT_FILE  = ERA5_DIR / "era5_monthly_isotherms_conus.nc"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "04a_download_era5.log"

# CONUS bounding box for ERA5 download (slightly padded)
AREA = [52, -128, 22, -64]   # [N, W, S, E]
GRID = [0.25, 0.25]          # 0.25° resolution (ERA5 native for atmos)

# Pressure levels to download (hPa) — span from surface to ~12 km
PRESSURE_LEVELS = [
    "1000", "975", "950", "925", "900", "875", "850",
    "825", "800", "775", "750", "700", "650", "600",
    "550", "500", "450", "400", "350", "300", "250", "200",
]

# Climatological years for monthly means
CLIM_YEARS = [str(y) for y in range(1991, 2021)]  # 1991–2020 climatology
MONTHS = [f"{m:02d}" for m in range(1, 13)]

log = get_logger("04a_download_era5", LOG_ROOT).info

PRESSURE_DATASET = "reanalysis-era5-pressure-levels-monthly-means"
SINGLE_LEVEL_DATASET = "reanalysis-era5-single-levels-monthly-means"
PRESSURE_LICENCE_URL = (
    "https://cds.climate.copernicus.eu/datasets/"
    "reanalysis-era5-pressure-levels-monthly-means?tab=download#manage-licences"
)
SINGLE_LEVEL_LICENCE_URL = (
    "https://cds.climate.copernicus.eu/datasets/"
    "reanalysis-era5-single-levels-monthly-means?tab=download#manage-licences"
)


def _era5_pressure_request(years: list[str], months: list[str]) -> dict:
    """Build the ERA5 pressure-level request for a bounded time chunk."""
    return {
        "product_type": "monthly_averaged_reanalysis",
        "variable": ["temperature", "geopotential"],
        "pressure_level": PRESSURE_LEVELS,
        "year": years,
        "month": months,
        "time": "00:00",
        "area": AREA,
        "grid": GRID,
        "data_format": "netcdf",
    }


def _is_cds_cost_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "cost limits exceeded" in msg or "request is too large" in msg


def _is_cds_licence_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "licence" in msg and "accepted" in msg


def _raise_cds_licence_error(dataset_url: str) -> None:
    raise RuntimeError(
        "CDS credentials are configured, but the required ERA5 dataset licence "
        f"has not been accepted for this account. Visit {dataset_url}, accept "
        "the licence terms while signed in, then rerun Stage 04a."
    )


def _retrieve_era5_chunk(client, years: list[str], months: list[str], target: Path) -> Path:
    if target.exists() and target.stat().st_size > 0:
        log(f"    Existing chunk: {target.name}")
        return target

    if target.exists():
        target.unlink()

    label = ",".join(years)
    month_label = ",".join(months)
    log(f"    Requesting ERA5 pressure chunk year={label} month={month_label}")
    try:
        client.retrieve(PRESSURE_DATASET, _era5_pressure_request(years, months), str(target))
    except Exception as exc:
        if _is_cds_licence_error(exc):
            _raise_cds_licence_error(PRESSURE_LICENCE_URL)
        raise
    log(f"    Downloaded chunk: {target.name} ({target.stat().st_size / 1e6:.1f} MB)")
    return target


def download_era5_temperature():
    """Download ERA5 monthly mean temperature on pressure levels."""
    import cdsapi

    ERA5_DIR.mkdir(parents=True, exist_ok=True)
    raw_file = ERA5_DIR / "era5_monthly_temp_plevels_conus.nc"
    chunk_dir = ERA5_DIR / "pressure_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    if raw_file.exists():
        log(f"  Raw ERA5 file already exists: {raw_file.name}")
        return [raw_file]

    log("  Requesting ERA5 monthly mean temperature from CDS in bounded chunks ...")
    log("  (This may take time depending on CDS queue and request throttling)")

    client = cdsapi.Client()
    chunk_files = []
    for year in CLIM_YEARS:
        yearly_file = chunk_dir / f"era5_monthly_temp_plevels_conus_{year}.nc"
        try:
            chunk_files.append(_retrieve_era5_chunk(client, [year], MONTHS, yearly_file))
            continue
        except Exception as exc:
            if not _is_cds_cost_limit_error(exc):
                raise
            log(f"    Yearly request for {year} exceeded CDS cost limits; falling back to monthly chunks")
            if yearly_file.exists():
                yearly_file.unlink()

        for month in MONTHS:
            monthly_file = chunk_dir / f"era5_monthly_temp_plevels_conus_{year}_{month}.nc"
            chunk_files.append(_retrieve_era5_chunk(client, [year], [month], monthly_file))

    log(f"  ERA5 pressure chunks ready: {len(chunk_files)} file(s)")
    return chunk_files

def download_era5_surface_geopotential():
    """Download ERA5 surface geopotential for AGL conversion."""
    import cdsapi

    sfc_file = ERA5_DIR / "era5_surface_geopotential_conus.nc"
    if sfc_file.exists():
        log(f"  Surface geopotential already exists: {sfc_file.name}")
        return sfc_file

    log("  Requesting ERA5 surface geopotential ...")
    client = cdsapi.Client()
    try:
        client.retrieve(
            SINGLE_LEVEL_DATASET,
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable": "geopotential",
                "year": "2020",
                "month": "01",
                "time": "00:00",
                "area": AREA,
                "grid": GRID,
                "data_format": "netcdf",
            },
            str(sfc_file),
        )
    except Exception as exc:
        if _is_cds_licence_error(exc):
            _raise_cds_licence_error(SINGLE_LEVEL_LICENCE_URL)
        raise
    return sfc_file

def _time_dim_name(ds) -> str:
    for name in ("time", "valid_time"):
        if name in ds.dims:
            return name
        if name in ds.coords and ds[name].dims:
            return ds[name].dims[0]
    raise KeyError("ERA5 dataset has no time/valid_time dimension")


def _load_pressure_climatology(pressure_files: Sequence[Path]):
    """Load ERA5 pressure chunks and return 12-month means as small arrays."""
    import xarray as xr

    if not pressure_files:
        raise ValueError("No ERA5 pressure files were provided")

    temp_sum = None
    geop_sum = None
    counts = np.zeros(12, dtype=np.int32)
    lats = None
    lons = None

    for path in pressure_files:
        log(f"    Reading pressure chunk: {path.name}")
        with xr.open_dataset(path) as ds:
            time_dim = _time_dim_name(ds)
            temp = ds["t"]
            geop = ds["z"]

            if temp_sum is None:
                sample_shape = temp.isel({time_dim: 0}).shape
                temp_sum = np.zeros((12, *sample_shape), dtype=np.float64)
                geop_sum = np.zeros((12, *sample_shape), dtype=np.float64)
                lats = ds["latitude"].values
                lons = ds["longitude"].values

            months = ds[time_dim].dt.month.values
            for month in range(1, 13):
                idx = np.where(months == month)[0]
                if idx.size == 0:
                    continue
                selector = {time_dim: idx}
                temp_sum[month - 1] += temp.isel(selector).mean(time_dim).values
                geop_sum[month - 1] += geop.isel(selector).mean(time_dim).values
                counts[month - 1] += 1

    missing = np.where(counts == 0)[0] + 1
    if missing.size:
        missing_text = ", ".join(str(m) for m in missing)
        raise ValueError(f"ERA5 pressure climatology is missing month(s): {missing_text}")

    temp_monthly = (temp_sum / counts[:, None, None, None]).astype(np.float32)
    heights_monthly = (geop_sum / counts[:, None, None, None] / 9.80665).astype(np.float32)
    return temp_monthly, heights_monthly, lats, lons, counts


def compute_isotherm_heights(pressure_files: Sequence[Path], sfc_file: Path):
    """
    Compute monthly mean 0°C and −20°C isotherm heights from ERA5 data.

    For each grid cell and month:
    1. Convert geopotential to geometric height (m)
    2. Subtract surface geopotential to get AGL
    3. Interpolate vertically to find H where T = 273.15 K (0°C) and T = 253.15 K (−20°C)
    4. Convert to km
    """
    import xarray as xr

    log("  Loading ERA5 temperature profiles from cached chunks ...")
    temp_monthly, heights_monthly, lats, lons, counts = _load_pressure_climatology(pressure_files)
    ds_sfc = xr.open_dataset(sfc_file)

    # Surface geopotential
    sfc_time_dim = _time_dim_name(ds_sfc) if any(name in ds_sfc["z"].dims for name in ("time", "valid_time")) else None
    sfc_geop = ds_sfc["z"].isel({sfc_time_dim: 0}) if sfc_time_dim else ds_sfc["z"]

    # Heights = geopotential / g (approximate, ignoring latitude variation)
    g = 9.80665
    sfc_height = sfc_geop / g  # surface elevation

    # Average over climatological years to get monthly means
    # Group by month
    log("  Computing 30-year monthly climatology ...")
    log(f"    Month sample counts: {counts.tolist()}")

    months = np.arange(1, 13)
    n_months = 12
    n_lats = len(lats)
    n_lons = len(lons)

    h_0C = np.full((n_months, n_lats, n_lons), np.nan, dtype=np.float32)
    h_m20C = np.full((n_months, n_lats, n_lons), np.nan, dtype=np.float32)

    log("  Interpolating isotherm heights ...")
    for m_idx in range(n_months):
        t_profile = temp_monthly[m_idx]                         # (plev, lat, lon) in K
        h_profile = heights_monthly[m_idx]                      # (plev, lat, lon) in m MSL
        sfc_h = sfc_height.values                                # (lat, lon) in m MSL

        for j in range(n_lats):
            for k in range(n_lons):
                t_col = t_profile[:, j, k]   # temperature profile (K), top-to-bottom
                h_col = h_profile[:, j, k]   # height profile (m MSL)
                h_sfc = sfc_h[j, k]

                # Convert to AGL
                h_agl = h_col - h_sfc  # meters AGL

                # Find 0°C (273.15 K) isotherm by linear interpolation
                for i in range(len(t_col) - 1):
                    # Pressure levels are top-to-bottom, so heights decrease
                    # We want the lowest crossing (nearest to surface)
                    if (t_col[i] <= 273.15 <= t_col[i + 1]) or (t_col[i + 1] <= 273.15 <= t_col[i]):
                        frac = (273.15 - t_col[i]) / (t_col[i + 1] - t_col[i]) if t_col[i + 1] != t_col[i] else 0.5
                        h_0C[m_idx, j, k] = (h_agl[i] + frac * (h_agl[i + 1] - h_agl[i])) / 1000.0

                # Find -20°C (253.15 K) isotherm
                for i in range(len(t_col) - 1):
                    if (t_col[i] <= 253.15 <= t_col[i + 1]) or (t_col[i + 1] <= 253.15 <= t_col[i]):
                        frac = (253.15 - t_col[i]) / (t_col[i + 1] - t_col[i]) if t_col[i + 1] != t_col[i] else 0.5
                        h_m20C[m_idx, j, k] = (h_agl[i] + frac * (h_agl[i + 1] - h_agl[i])) / 1000.0

        log(f"    Month {m_idx + 1}: median H_0C = {np.nanmedian(h_0C[m_idx]):.2f} km, "
            f"H_-20C = {np.nanmedian(h_m20C[m_idx]):.2f} km")

    # Fill any remaining NaNs with reasonable defaults
    h_0C = np.where(np.isnan(h_0C), 3.5, h_0C)
    h_m20C = np.where(np.isnan(h_m20C), 6.0, h_m20C)

    # Save as NetCDF
    log(f"  Writing {OUT_FILE.name} ...")
    import xarray as xr
    out_ds = xr.Dataset(
        {
            "h_0C_km":  (["month", "latitude", "longitude"], h_0C,
                         {"units": "km AGL", "long_name": "Monthly mean 0°C isotherm height"}),
            "h_m20C_km": (["month", "latitude", "longitude"], h_m20C,
                          {"units": "km AGL", "long_name": "Monthly mean -20°C isotherm height"}),
        },
        coords={
            "month": months,
            "latitude": lats,
            "longitude": lons,
        },
        attrs={
            "source": "ERA5 monthly mean 1991-2020 climatology",
            "reference": "Copernicus Climate Data Store",
            "created": time.strftime("%Y-%m-%d"),
        },
    )
    out_ds.to_netcdf(OUT_FILE)
    log(f"  Done: {OUT_FILE} ({OUT_FILE.stat().st_size / 1e3:.0f} KB)")

    ds_sfc.close()

def validate_outputs() -> bool:
    errors = []
    if not OUT_FILE.exists():
        errors.append(f"Missing: {OUT_FILE}")
    else:
        import xarray as xr
        ds = xr.open_dataset(OUT_FILE)
        for var in ["h_0C_km", "h_m20C_km"]:
            if var not in ds:
                errors.append(f"Missing variable: {var}")
            else:
                vals = ds[var].values
                if np.all(np.isnan(vals)):
                    errors.append(f"All NaN: {var}")
                med = np.nanmedian(vals)
                if var == "h_0C_km" and not (1.0 < med < 6.0):
                    errors.append(f"Suspicious median {var}: {med:.2f} km")
                if var == "h_m20C_km" and not (3.0 < med < 10.0):
                    errors.append(f"Suspicious median {var}: {med:.2f} km")
        ds.close()
        if not errors:
            log(f"  Isotherm file OK: {OUT_FILE.name}")

    if errors:
        log("Validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True

def main():
    parser = argparse.ArgumentParser(description="Download ERA5 isotherm heights.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  ERA5 Isotherm Heights — Stage 04a")
    log(f"{'='*60}")

    raw_file = download_era5_temperature()
    sfc_file = download_era5_surface_geopotential()
    compute_isotherm_heights(raw_file, sfc_file)

    ok = validate_outputs()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
