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

import csv
import fcntl
import re
from collections.abc import Iterable, Sequence
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


def staged_nc_files_for_convective_day(
    stage_base: Path,
    convective_day: date,
    start_hour_utc: int = CONVECTIVE_DAY_START_HOUR_UTC,
) -> list[Path]:
    """Return staged NetCDF paths under ``by_convective_day/YYYYMMDD`` for one label."""
    stage_dir = stage_base / "by_convective_day" / convective_day.strftime("%Y%m%d")
    if not stage_dir.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(stage_dir.glob("*.nc")):
        obs = parse_observation_utc_from_name(path.name)
        if obs is None or observation_utc_to_convective_day(obs, start_hour_utc) != convective_day:
            continue
        out.append(path)
    return out


def observation_times_from_paths(
    paths: Iterable[Path | str],
    convective_day: date,
    start_hour_utc: int = CONVECTIVE_DAY_START_HOUR_UTC,
) -> list[datetime]:
    """Parse observation UTC times from filenames, keeping only the convective window."""
    start, end = convective_day_window_utc(convective_day, start_hour_utc)
    times: list[datetime] = []
    for path in paths:
        obs = parse_observation_utc_from_name(Path(path).name)
        if obs is None:
            continue
        if obs.tzinfo is None:
            obs = obs.replace(tzinfo=_UTC)
        else:
            obs = obs.astimezone(_UTC)
        if start <= obs < end:
            times.append(obs)
    return sorted(times)


def convective_window_coverage_ok(
    timestamps: Sequence[datetime],
    convective_day: date,
    *,
    start_hour_utc: int = CONVECTIVE_DAY_START_HOUR_UTC,
    min_files: int = 6,
    edge_tolerance_minutes: float = 30.0,
    max_gap_minutes: float = 60.0,
) -> bool:
    """True if timesteps span the convective day without large interior gaps."""
    start, end = convective_day_window_utc(convective_day, start_hour_utc)
    times: list[datetime] = []
    for obs in timestamps:
        if obs.tzinfo is None:
            obs = obs.replace(tzinfo=_UTC)
        else:
            obs = obs.astimezone(_UTC)
        if start <= obs < end:
            times.append(obs)
    times = sorted(set(times))
    if len(times) < min_files:
        return False
    edge_tol = edge_tolerance_minutes * 60.0
    if (times[0] - start).total_seconds() > edge_tol:
        return False
    if (end - times[-1]).total_seconds() > edge_tol:
        return False
    max_gap = max_gap_minutes * 60.0
    for a, b in zip(times, times[1:]):
        if (b - a).total_seconds() > max_gap:
            return False
    return True


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


# ---------------------------------------------------------------------------
# Daily MESH source manifests (stages 01, 02, 04c)
# ---------------------------------------------------------------------------

MESH_SOURCE_MANIFEST_FIELDS = [
    "date",
    "output_path",
    "source_files",
    "plain_netcdf_files",
    "gz_netcdf_files",
    "source_valid_pixels",
    "active_cells_0p05",
    "max_mesh_mm",
    "status",
    "skipped",
    "read_errors",
]


def count_plain_and_compressed_sources(
    names: Iterable[str],
    *,
    plain_suffixes: tuple[str, ...] = (".netcdf",),
    compressed_suffixes: tuple[str, ...] = (".netcdf.gz",),
) -> tuple[int, int]:
    """Count plain vs compressed source objects by filename suffix."""
    plain = compressed = 0
    for name in names:
        lowered = name.lower()
        if any(lowered.endswith(suffix) for suffix in compressed_suffixes):
            compressed += 1
        elif any(lowered.endswith(suffix) for suffix in plain_suffixes):
            plain += 1
    return plain, compressed


def classify_mesh_source_day(
    source_files: int,
    active_cells: int,
    read_errors: int = 0,
) -> str:
    """Classify source availability separately from hail/no-hail signal."""
    if source_files == 0:
        return "missing_source"
    if read_errors >= source_files:
        return "error"
    if read_errors > 0:
        if active_cells > 0:
            return "ok_with_read_errors"
        return "no_hail_pixels_with_read_errors"
    if active_cells == 0:
        return "no_hail_pixels"
    return "ok"


def mesh_manifest_row(
    day: date,
    out_path: Path,
    repo_root: Path,
    *,
    source_files: int,
    plain_count: int,
    gz_count: int,
    source_pixels: int | None,
    active_cells: int,
    max_mesh_mm: float,
    status: str,
    skipped: bool = False,
    read_errors: int | None = None,
) -> dict:
    """Build one daily MESH source-coverage manifest row."""
    try:
        output_path = str(out_path.relative_to(repo_root))
    except ValueError:
        output_path = str(out_path)
    return {
        "date": day.isoformat(),
        "output_path": output_path,
        "source_files": source_files,
        "plain_netcdf_files": plain_count,
        "gz_netcdf_files": gz_count,
        "source_valid_pixels": "" if source_pixels is None else source_pixels,
        "active_cells_0p05": active_cells,
        "max_mesh_mm": max_mesh_mm,
        "status": status,
        "skipped": int(skipped),
        "read_errors": "" if read_errors is None else read_errors,
    }


def read_mesh_manifest_rows_by_date(manifest_path: Path) -> dict:
    """Read a MESH source manifest keyed by ISO date."""
    rows: dict = {}
    if manifest_path.exists():
        with open(manifest_path, newline="") as f:
            for row in csv.DictReader(f):
                rows[row["date"]] = row
    return rows


def write_mesh_manifest_rows(manifest_path: Path, rows: dict) -> None:
    """Write a complete MESH source manifest dictionary keyed by date."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = manifest_path.with_suffix(".csv.tmp")
    with open(tmp_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MESH_SOURCE_MANIFEST_FIELDS)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(
                {field: rows[key].get(field, "") for field in MESH_SOURCE_MANIFEST_FIELDS}
            )
    tmp_path.replace(manifest_path)


def upsert_mesh_manifest_row(manifest_path: Path, row: dict) -> None:
    """Write or replace one manifest row by date (process-safe via file lock)."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = manifest_path.with_suffix(".csv.lock")
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            rows = read_mesh_manifest_rows_by_date(manifest_path)
            rows[row["date"]] = {
                field: row.get(field, "") for field in MESH_SOURCE_MANIFEST_FIELDS
            }
            write_mesh_manifest_rows(manifest_path, rows)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def summarize_mesh_output_raster(
    path: Path,
    *,
    max_hail_mm: float = MAX_HAIL_MM,
) -> tuple[int, float]:
    """Return active 0.05° cells and max MESH (mm) from a daily GeoTIFF."""
    import rasterio

    with rasterio.open(path) as src:
        data = src.read(1)
    valid = np.isfinite(data) & (data > 0) & (data <= max_hail_mm)
    if not np.any(valid):
        return 0, 0.0
    active_cells = int(np.count_nonzero(valid))
    max_mesh = float(data[valid].max())
    return active_cells, round(max_mesh, 1)
