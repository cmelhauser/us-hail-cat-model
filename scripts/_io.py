"""
_io.py — Shared I/O helpers for the CONUS Hail Catastrophe Model v2.1
======================================================================

Contains three functions that used to be duplicated across multiple stage
scripts. Stage scripts now import these helpers so grid geometry and GeoTIFF
profile behavior stay in one place.

Functions
---------
write_geotiff   Write a single-band float32 GeoTIFF at the canonical 0.05° grid.
sanitize_hail_values  Reset invalid hail values to the no-signal sentinel.
haversine_km    Great-circle distance in km between two (lat, lon) points.
latlon_to_grid  Convert a (lat, lon) coordinate to grid (row, col).

Usage
-----
    from _io import write_geotiff, haversine_km, latlon_to_grid

All three functions accept the same arguments and return the same types as the
inline copies they replace — the refactor is purely a mechanical substitution.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

try:
    from _config import (
        CONVECTIVE_DAY_START_HOUR_UTC,
        LAT_MAX,
        LON_MIN,
        NROWS,
        NCOLS,
        DX,
        NODATA,
        MAX_HAIL_MM,
    )
except ImportError:  # pragma: no cover - exercised by pytest importlib loading
    from scripts._config import (
        CONVECTIVE_DAY_START_HOUR_UTC,
        LAT_MAX,
        LON_MIN,
        NROWS,
        NCOLS,
        DX,
        NODATA,
        MAX_HAIL_MM,
    )

_UTC = timezone.utc
_RE_GRIDRAD_UTC = re.compile(r"(\d{8})T(\d{6})Z", re.IGNORECASE)
_RE_MYRORSS_UTC = re.compile(r"(\d{8})-(\d{6})")
_RE_MRMS_UTC = re.compile(r"(\d{8})-(\d{6})")

# ---------------------------------------------------------------------------
# Convective day (12 UTC → 12 UTC)
# ---------------------------------------------------------------------------

def convective_day_window_utc(
    convective_day: date,
    start_hour_utc: int = CONVECTIVE_DAY_START_HOUR_UTC,
) -> tuple[datetime, datetime]:
    """Return [start, end) UTC for a convective day labeled ``convective_day``.

    Label ``2016-07-21`` means 2016-07-21 12:00 UTC through 2016-07-22 12:00 UTC
    (exclusive end).
    """
    start = datetime(
        convective_day.year,
        convective_day.month,
        convective_day.day,
        start_hour_utc,
        0,
        0,
        tzinfo=_UTC,
    )
    return start, start + timedelta(days=1)


def observation_utc_to_convective_day(
    obs_utc: datetime,
    start_hour_utc: int = CONVECTIVE_DAY_START_HOUR_UTC,
) -> date:
    """Map a UTC observation time to its convective-day label."""
    if obs_utc.tzinfo is None:
        obs_utc = obs_utc.replace(tzinfo=_UTC)
    else:
        obs_utc = obs_utc.astimezone(_UTC)
    shifted = obs_utc - timedelta(hours=start_hour_utc)
    return shifted.date()


def observation_in_convective_day(
    obs_utc: datetime,
    convective_day: date,
    start_hour_utc: int = CONVECTIVE_DAY_START_HOUR_UTC,
) -> bool:
    """True if ``obs_utc`` falls in the convective window for ``convective_day``."""
    start, end = convective_day_window_utc(convective_day, start_hour_utc)
    if obs_utc.tzinfo is None:
        obs_utc = obs_utc.replace(tzinfo=_UTC)
    else:
        obs_utc = obs_utc.astimezone(_UTC)
    return start <= obs_utc < end


def calendar_days_for_convective_day(convective_day: date) -> tuple[date, date]:
    """UTC calendar dates whose archives can contain timesteps for this convective day."""
    return convective_day, convective_day + timedelta(days=1)


def parse_observation_utc_from_name(name: str) -> datetime | None:
    """Parse UTC time from MYRORSS, MRMS, or GridRad-style filenames."""
    for pattern in (_RE_GRIDRAD_UTC, _RE_MYRORSS_UTC, _RE_MRMS_UTC):
        m = pattern.search(name)
        if not m:
            continue
        ymd, hms = m.group(1), m.group(2)
        try:
            return datetime(
                int(ymd[0:4]),
                int(ymd[4:6]),
                int(ymd[6:8]),
                int(hms[0:2]),
                int(hms[2:4]),
                int(hms[4:6]),
                tzinfo=_UTC,
            )
        except ValueError:
            continue
    return None


def convective_day_window_tag(convective_day: date) -> str:
    """ISO interval tag for GeoTIFF metadata."""
    start, end = convective_day_window_utc(convective_day)
    return f"{start.isoformat()}/{end.isoformat()}"


def mesh_path_for_convective_day(mesh_dir: Path, convective_day: date) -> Path:
    """Canonical daily MESH GeoTIFF path for a convective-day label."""
    ymd = convective_day.strftime("%Y%m%d")
    return mesh_dir / f"{convective_day.year}" / f"mesh_{ymd}.tif"


def filter_keys_for_convective_day(
    keys: Iterable[str],
    convective_day: date,
    start_hour_utc: int = CONVECTIVE_DAY_START_HOUR_UTC,
) -> list[str]:
    """Keep object keys whose parsed UTC time maps to ``convective_day``."""
    out: list[str] = []
    for key in keys:
        obs = parse_observation_utc_from_name(Path(key).name)
        if obs is not None and observation_utc_to_convective_day(obs, start_hour_utc) == convective_day:
            out.append(key)
    return sorted(set(out))


# ---------------------------------------------------------------------------
# GeoTIFF writing
# ---------------------------------------------------------------------------

def write_geotiff(
    data: np.ndarray,
    out_path: Path | str,
    nodata: float = NODATA,
    tags: dict[str, str] | None = None,
) -> None:
    """Write a single-band float32 GeoTIFF at the canonical 0.05° CONUS grid.

    Parameters
    ----------
    data : np.ndarray, shape (NROWS, NCOLS)
        Array to write.  Values below ``nodata`` are preserved as-is; no
        masking is applied here.
    out_path : Path or str
        Destination file path.  Parent directories are created if absent.
    nodata : float, optional
        Nodata sentinel written to the GeoTIFF profile.  Default is
        ``_config.NODATA`` (0.0 for no MESH signal).
    tags : dict[str, str], optional
        Optional GDAL metadata tags (e.g. daily max hail diagnostics).

    Notes
    -----
    * Compression: LZW with 256×256 tiles for efficient partial reads.
    * CRS: EPSG:4326.
    * Transform: ``from_origin(LON_MIN, LAT_MAX, DX, DX)`` — upper-left corner
      of cell (0, 0) at (LAT_MAX, LON_MIN), cell size DX in both axes.
    """
    import rasterio
    from rasterio.transform import from_origin

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver":     "GTiff",
        "dtype":      "float32",
        "width":      NCOLS,
        "height":     NROWS,
        "count":      1,
        "crs":        "EPSG:4326",
        "transform":  from_origin(LON_MIN, LAT_MAX, DX, DX),
        "compress":   "lzw",
        "tiled":      True,
        "blockxsize": 256,
        "blockysize": 256,
        "nodata":     nodata,
    }
    if tags:
        profile["tags"] = {str(k): str(v) for k, v in tags.items()}

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)


def sanitize_hail_values(
    data: np.ndarray,
    max_hail_mm: float = MAX_HAIL_MM,
    nodata: float = NODATA,
) -> tuple[np.ndarray, int]:
    """Return a float32 hail array with invalid values reset to ``nodata``.

    This is the shared physical QA guard for hail-size rasters. Values that are
    non-finite, negative, or above ``max_hail_mm`` are treated as source/model
    artifacts and reset to the model's no-signal sentinel before downstream
    use.
    """
    arr = np.asarray(data, dtype=np.float32).copy()
    bad = (~np.isfinite(arr)) | (arr < 0) | (arr > max_hail_mm)
    n_bad = int(np.count_nonzero(bad))
    if n_bad:
        arr[bad] = nodata
    return arr, n_bad


# ---------------------------------------------------------------------------
# Geodetic distance
# ---------------------------------------------------------------------------

def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance in km between two (lat, lon) points (scalar).

    Parameters
    ----------
    lat1, lon1 : float
        First point in decimal degrees.
    lat2, lon2 : float
        Second point in decimal degrees.

    Returns
    -------
    float
        Distance in kilometres.

    Notes
    -----
    Uses the haversine formula with Earth radius R = 6371 km.
    ``np.clip`` guards against floating-point rounding outside [0, 1] before
    the ``arcsin``.
    """
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    )
    return float(6371.0 * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))))


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------

def latlon_to_grid(
    lat: float,
    lon: float,
) -> tuple[int, int]:
    """Convert a (lat, lon) coordinate to the canonical grid (row, col).

    The grid origin is the upper-left corner of cell (0, 0) at
    (LAT_MAX, LON_MIN).  Row index increases southward; column index increases
    eastward.

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees (positive = north).
    lon : float
        Longitude in decimal degrees (negative = west).

    Returns
    -------
    tuple[int, int]
        ``(row, col)`` if the point falls inside the CONUS grid, otherwise
        ``(-1, -1)``.
    """
    row = int((LAT_MAX - lat) / DX)
    col = int((lon - LON_MIN) / DX)
    if 0 <= row < NROWS and 0 <= col < NCOLS:
        return row, col
    return -1, -1
