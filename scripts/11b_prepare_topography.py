#!/usr/bin/env python3
"""
11b_prepare_topography.py — Public DEM Preparation
==================================================
Downloads NOAA/NCEI ETOPO 2022 60 arc-second surface elevation and resamples it
to the model's 0.05° CONUS grid for Stage 12 topographic correction.

Why ETOPO 2022?
---------------
ETOPO 2022 is a public, DOI-backed, peer-reviewed global relief model from
NOAA/NCEI. The 60 arc-second surface GeoTIFF is coarse enough to download as a
single stable file and fine enough to aggregate to the model's 0.05° grid.

Input
-----
  https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/60s/
    60s_surface_elev_gtif/ETOPO_2022_v1_60s_N90W180_surface.tif

Output
------
  data/analysis/topography/source/ETOPO_2022_v1_60s_N90W180_surface.tif
  data/analysis/topography/elevation_0.05deg.tif

Usage
-----
  python scripts/11b_prepare_topography.py
  python scripts/11b_prepare_topography.py --validate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import CRS, DX, LAT_MAX, LON_MIN, LOG_ROOT, NCOLS, NROWS, TOPO_DIR
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import CRS, DX, LAT_MAX, LON_MIN, LOG_ROOT, NCOLS, NROWS, TOPO_DIR
    from scripts._logging import get_logger

ETOPO_2022_SURFACE_URL = (
    "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/60s/"
    "60s_surface_elev_gtif/ETOPO_2022_v1_60s_N90W180_surface.tif"
)
ETOPO_2022_DOI = "https://doi.org/10.25921/fd45-gt74"
ETOPO_2022_REFERENCE = (
    "NOAA National Centers for Environmental Information, 2022: "
    "ETOPO 2022 15 Arc-Second Global Relief Model. "
    "https://doi.org/10.25921/fd45-gt74"
)

SOURCE_DIR = TOPO_DIR / "source"
SOURCE_TIF = SOURCE_DIR / "ETOPO_2022_v1_60s_N90W180_surface.tif"
ELEVATION_TIF = TOPO_DIR / "elevation_0.05deg.tif"

MIN_SOURCE_BYTES = 100_000_000
MAX_REASONABLE_CONUS_ELEV_M = 5000.0

log = get_logger("11b_prepare_topography", LOG_ROOT).info


def target_transform():
    """Return the canonical model-grid affine transform."""
    from rasterio.transform import from_origin

    return from_origin(LON_MIN, LAT_MAX, DX, DX)


def sanitize_elevation_m(data: np.ndarray) -> np.ndarray:
    """Return finite nonnegative surface elevation in meters."""
    arr = np.asarray(data, dtype=np.float32).copy()
    arr[~np.isfinite(arr)] = 0.0
    arr[arr < 0.0] = 0.0
    return arr


def download_source(source_path: Path = SOURCE_TIF, url: str = ETOPO_2022_SURFACE_URL) -> Path:
    """Download the ETOPO 2022 source GeoTIFF if it is not already cached."""
    import requests

    source_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.exists() and source_path.stat().st_size >= MIN_SOURCE_BYTES:
        log(f"  Source DEM already cached: {source_path.name} ({source_path.stat().st_size / 1e6:.1f} MB)")
        return source_path

    tmp_path = source_path.with_suffix(source_path.suffix + ".part")
    if tmp_path.exists():
        tmp_path.unlink()

    log("  Downloading NOAA/NCEI ETOPO 2022 60 arc-second surface GeoTIFF ...")
    log(f"  Source: {url}")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", "0"))
        downloaded = 0
        next_report = 50_000_000
        with open(tmp_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)
                if downloaded >= next_report:
                    if total:
                        pct = 100.0 * downloaded / total
                        log(f"    Downloaded {downloaded / 1e6:.0f}/{total / 1e6:.0f} MB ({pct:.1f}%)")
                    else:
                        log(f"    Downloaded {downloaded / 1e6:.0f} MB")
                    next_report += 50_000_000

    if tmp_path.stat().st_size < MIN_SOURCE_BYTES:
        raise RuntimeError(f"Downloaded DEM is unexpectedly small: {tmp_path.stat().st_size} bytes")

    tmp_path.replace(source_path)
    log(f"  Cached source DEM: {source_path} ({source_path.stat().st_size / 1e6:.1f} MB)")
    return source_path


def build_model_grid_dem(source_path: Path = SOURCE_TIF, out_path: Path = ELEVATION_TIF) -> Path:
    """Resample ETOPO 2022 to the model grid and write elevation_0.05deg.tif."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    out_path.parent.mkdir(parents=True, exist_ok=True)
    transform = target_transform()

    log("  Resampling DEM to 0.05° model grid ...")
    with rasterio.open(source_path) as src:
        with WarpedVRT(
            src,
            crs=CRS,
            transform=transform,
            width=NCOLS,
            height=NROWS,
            resampling=Resampling.average,
        ) as vrt:
            elev = vrt.read(1, out_shape=(NROWS, NCOLS)).astype(np.float32)

    elev = sanitize_elevation_m(elev)

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": NCOLS,
        "height": NROWS,
        "count": 1,
        "crs": CRS,
        "transform": transform,
        "compress": "lzw",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "nodata": 0.0,
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(elev, 1)
        dst.update_tags(
            source="NOAA/NCEI ETOPO 2022 60 arc-second surface elevation",
            source_url=ETOPO_2022_SURFACE_URL,
            doi=ETOPO_2022_DOI,
            reference=ETOPO_2022_REFERENCE,
            processing="Resampled to 0.05 degree CONUS model grid using rasterio average resampling; negative ocean elevations set to 0 m.",
        )

    log(f"  Wrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
    log(f"  Elevation range: {float(np.nanmin(elev)):.1f} to {float(np.nanmax(elev)):.1f} m")
    return out_path


def validate_outputs() -> bool:
    errors: list[str] = []
    if not ELEVATION_TIF.exists():
        errors.append(f"Missing: {ELEVATION_TIF}")
    else:
        import rasterio

        with rasterio.open(ELEVATION_TIF) as src:
            if src.width != NCOLS or src.height != NROWS:
                errors.append(f"Unexpected DEM shape: {src.height}x{src.width}")
            if str(src.crs) != CRS:
                errors.append(f"Unexpected DEM CRS: {src.crs}")
            data = src.read(1)

        if not np.isfinite(data).all():
            errors.append("DEM contains non-finite values")
        if float(np.nanmin(data)) < 0.0:
            errors.append(f"DEM contains negative values after sea-level clipping: {float(np.nanmin(data)):.1f}")
        max_elev = float(np.nanmax(data))
        if not (3000.0 <= max_elev <= MAX_REASONABLE_CONUS_ELEV_M):
            errors.append(f"Suspicious CONUS max elevation: {max_elev:.1f} m")
        if float(np.nanmean(data)) <= 100.0:
            errors.append(f"Suspiciously low mean elevation: {float(np.nanmean(data)):.1f} m")

    if errors:
        log("Validation FAILED:")
        for err in errors:
            log(f"  ✗ {err}")
        return False

    log("Output validation passed ✓")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare NOAA/NCEI ETOPO 2022 DEM.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log("  Public DEM Preparation — Stage 11b")
    log(f"{'='*60}")
    log(f"  DEM source: NOAA/NCEI ETOPO 2022 surface elevation ({ETOPO_2022_DOI})")

    source_path = download_source()
    build_model_grid_dem(source_path)

    ok = validate_outputs()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
