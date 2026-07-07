"""
_radar_geometry.py — NEXRAD site geometry and range-dependent MESH debias helpers.

NEXRAD site coordinates follow NOAA HOMR / Py-ART ``nexrad_common`` (CONUS WSR-88D,
``K*`` ICAO IDs). Used by ``scripts/diagnostics/radar_artifact_diagnostic.py`` and
Stage 05 range debias.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import numpy as np

try:
    from _config import DX, LAT_MAX, LON_MIN, NCOLS, NROWS, REPO_ROOT
    from _io import haversine_km
except ImportError:  # pragma: no cover
    from scripts._config import DX, LAT_MAX, LON_MIN, NCOLS, NROWS, REPO_ROOT
    from scripts._io import haversine_km

MRMS_START = date(2020, 10, 14)
GRIDRAD_START = date(2012, 1, 1)
GRIDRAD_END = date(2020, 10, 13)

# CONUS WSR-88D (K*) from Py-ART / NOAA HOMR (subset of international / TDWR sites removed).
_NEXRAD_CONUS: dict[str, tuple[float, float]] = {
    "KABR": (45.45583, -98.41306),
    "KABX": (35.14972, -106.82333),
    "KAKQ": (36.98389, -77.0075),
    "KAMA": (35.23333, -101.70889),
    "KAMX": (25.61056, -80.41306),
    "KAPX": (44.90722, -84.71972),
    "KARX": (43.82278, -91.19111),
    "KATX": (48.19472, -122.49444),
    "KBBX": (39.49611, -121.63167),
    "KBGM": (42.19972, -75.985),
    "KBHX": (40.49833, -124.29194),
    "KBIS": (46.77083, -100.76028),
    "KBLX": (45.85389, -108.60611),
    "KBMX": (33.17194, -86.76972),
    "KBOX": (41.95583, -71.1375),
    "KBRO": (25.91556, -97.41861),
    "KBUF": (42.94861, -78.73694),
    "KBYX": (24.59694, -81.70333),
    "KCAE": (33.94861, -81.11861),
    "KCBW": (46.03917, -67.80694),
    "KCBX": (43.49083, -116.23444),
    "KCCX": (40.92306, -78.00389),
    "KCLE": (41.41306, -81.86),
    "KCLX": (32.65556, -81.04222),
    "KCRI": (35.2383, -97.4602),
    "KCRP": (27.78389, -97.51083),
    "KCXX": (44.51111, -73.16639),
    "KCYS": (41.15194, -104.80611),
    "KDAX": (38.50111, -121.67667),
    "KDDC": (37.76083, -99.96833),
    "KDFX": (29.2725, -100.28028),
    "KDGX": (32.28, -89.98444),
    "KDIX": (39.94694, -74.41111),
    "KDLH": (46.83694, -92.20972),
    "KDMX": (41.73111, -93.72278),
    "KDOX": (38.82556, -75.44),
    "KDTX": (42.69972, -83.47167),
    "KDVN": (41.61167, -90.58083),
    "KDYX": (32.53833, -99.25417),
    "KEAX": (38.81028, -94.26417),
    "KEMX": (31.89361, -110.63028),
    "KENX": (42.58639, -74.06444),
    "KEOX": (31.46028, -85.45944),
    "KEPZ": (31.87306, -106.6975),
    "KESX": (35.70111, -114.89139),
    "KEVX": (30.56417, -85.92139),
    "KEWX": (29.70361, -98.02806),
    "KEYX": (35.09778, -117.56),
    "KFCX": (37.02417, -80.27417),
    "KFDR": (34.36222, -98.97611),
    "KFDX": (34.63528, -103.62944),
    "KFFC": (33.36333, -84.56583),
    "KFSD": (43.58778, -96.72889),
    "KFSX": (34.57444, -111.19833),
    "KFTG": (39.78667, -104.54528),
    "KFWS": (32.57278, -97.30278),
    "KGGW": (48.20639, -106.62417),
    "KGJX": (39.06222, -108.21306),
    "KGLD": (39.36694, -101.7),
    "KGRB": (44.49833, -88.11111),
    "KGRK": (30.72167, -97.38278),
    "KGRR": (42.89389, -85.54472),
    "KGSP": (34.88306, -82.22028),
    "KGWX": (33.89667, -88.32889),
    "KGYX": (43.89139, -70.25694),
    "KHDC": (30.519, -90.407),
    "KHDX": (33.07639, -106.12222),
    "KHGX": (29.47194, -95.07889),
    "KHNX": (36.31417, -119.63111),
    "KHPX": (36.73667, -87.285),
    "KHTX": (34.93056, -86.08361),
    "KICT": (37.65444, -97.4425),
    "KICX": (37.59083, -112.86222),
    "KILN": (39.42028, -83.82167),
    "KILX": (40.15056, -89.33667),
    "KIND": (39.7075, -86.28028),
    "KINX": (36.175, -95.56444),
    "KIWA": (33.28917, -111.66917),
    "KIWX": (41.40861, -85.7),
    "KJAX": (30.48444, -81.70194),
    "KJGX": (32.675, -83.35111),
    "KJKL": (37.59083, -83.31306),
    "KLBB": (33.65417, -101.81361),
    "KLCH": (30.125, -93.21583),
    "KLGX": (47.1158, -124.1069),
    "KLIX": (30.33667, -89.82528),
    "KLNX": (41.95778, -100.57583),
    "KLOT": (41.60444, -88.08472),
    "KLRX": (40.73972, -116.80278),
    "KLSX": (38.69889, -90.68278),
    "KLTX": (33.98917, -78.42917),
    "KLVX": (37.97528, -85.94389),
    "KLWX": (38.97628, -77.48751),
    "KLZK": (34.83639, -92.26194),
    "KMAF": (31.94333, -102.18889),
    "KMAX": (42.08111, -122.71611),
    "KMBX": (48.3925, -100.86444),
    "KMHX": (34.77583, -76.87639),
    "KMKX": (42.96778, -88.55056),
    "KMLB": (28.11306, -80.65444),
    "KMOB": (30.67944, -88.23972),
    "KMPX": (44.84889, -93.56528),
    "KMQT": (46.53111, -87.54833),
    "KMRX": (36.16833, -83.40194),
    "KMSX": (47.04111, -113.98611),
    "KMTX": (41.26278, -112.44694),
    "KMUX": (37.15528, -121.8975),
    "KMVX": (47.52806, -97.325),
    "KMXX": (32.53667, -85.78972),
    "KNKX": (32.91889, -117.04194),
    "KNQA": (35.34472, -89.87333),
    "KOAX": (41.32028, -96.36639),
    "KOHX": (36.24722, -86.5625),
    "KOKX": (40.86556, -72.86444),
    "KOTX": (47.68056, -117.62583),
    "KPAH": (37.06833, -88.77194),
    "KPBZ": (40.53167, -80.21833),
    "KPDT": (45.69056, -118.85278),
    "KPOE": (31.15528, -92.97583),
    "KPUX": (38.45944, -104.18139),
    "KRAX": (35.66528, -78.49),
    "KRGX": (39.75417, -119.46111),
    "KRIW": (43.06611, -108.47667),
    "KRLX": (38.31194, -81.72389),
    "KRTX": (45.715, -122.96417),
    "KSFX": (43.10583, -112.68528),
    "KSGF": (37.23528, -93.40028),
    "KSHV": (32.45056, -93.84111),
    "KSJT": (31.37111, -100.49222),
    "KSOX": (33.81778, -117.635),
    "KSRX": (35.29056, -94.36167),
    "KTBW": (27.70528, -82.40194),
    "KTFX": (47.45972, -111.38444),
    "KTLH": (30.3975, -84.32889),
    "KTLX": (35.33306, -97.2775),
    "KTWX": (38.99694, -96.2325),
    "KTYX": (43.75583, -75.68),
    "KUDX": (44.125, -102.82944),
    "KUEX": (40.32083, -98.44167),
    "KVAX": (30.89, -83.00194),
    "KVBX": (34.83806, -120.39583),
    "KVNX": (36.74083, -98.1275),
    "KVTX": (34.41167, -119.17861),
    "KVWX": (38.26, -87.7247),
    "KYUX": (32.49528, -114.65583),
}

DEFAULT_RANGE_BIN_EDGES_KM = np.array(
    [0, 25, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400], dtype=np.float32
)
# Finer bins for per-site radial ring detection (10 km).
RADIAL_RING_BIN_EDGES_KM = np.arange(0, 405, 10, dtype=np.float32)
REFERENCE_RANGE_KM = 125.0
MM_PER_INCH = 25.4

CALIB_DIR = REPO_ROOT / "data" / "analysis" / "calibration"
RANGE_DEBIAS_NPZ = CALIB_DIR / "range_debias.npz"
RANGE_KM_NPY = CALIB_DIR / "nearest_radar_distance_km.npy"
NEAREST_SITE_NPY = CALIB_DIR / "nearest_nexrad_site_index.npy"


def classify_mesh_source(day: date) -> str:
    if day >= MRMS_START:
        return "MRMS"
    if GRIDRAD_START <= day <= GRIDRAD_END:
        return "GridRad"
    return "MYRORSS"


def classify_mesh_source_from_yyyymmdd(datestr: str) -> str:
    d = date(int(datestr[:4]), int(datestr[4:6]), int(datestr[6:8]))
    return classify_mesh_source(d)


def nexrad_sites_conus() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (lats, lons, site_ids) for CONUS WSR-88D."""
    ids = sorted(_NEXRAD_CONUS)
    lats = np.array([_NEXRAD_CONUS[i][0] for i in ids], dtype=np.float64)
    lons = np.array([_NEXRAD_CONUS[i][1] for i in ids], dtype=np.float64)
    return lats, lons, ids


def cell_center_latlon() -> tuple[np.ndarray, np.ndarray]:
    """Cell-center latitude/longitude grids (NROWS, NCOLS)."""
    lats = LAT_MAX - (np.arange(NROWS, dtype=np.float64) + 0.5) * DX
    lons = LON_MIN + (np.arange(NCOLS, dtype=np.float64) + 0.5) * DX
    lat_grid = np.broadcast_to(lats[:, None], (NROWS, NCOLS))
    lon_grid = np.broadcast_to(lons[None, :], (NROWS, NCOLS))
    return lat_grid, lon_grid


def nearest_radar_distance_km(
    lat_grid: np.ndarray | None = None,
    lon_grid: np.ndarray | None = None,
) -> np.ndarray:
    """Per-cell great-circle distance (km) to the nearest CONUS NEXRAD site."""
    if lat_grid is None or lon_grid is None:
        lat_grid, lon_grid = cell_center_latlon()
    site_lats, site_lons, _ = nexrad_sites_conus()
    flat_lat = lat_grid.ravel()
    flat_lon = lon_grid.ravel()
    n_cells = flat_lat.size
    n_sites = site_lats.size
    # Chunked haversine to limit peak memory (cells × sites).
    chunk = 50_000
    dist_min = np.full(n_cells, np.inf, dtype=np.float64)
    for i0 in range(0, n_cells, chunk):
        i1 = min(i0 + chunk, n_cells)
        clat = flat_lat[i0:i1][:, None]
        clon = flat_lon[i0:i1][:, None]
        slat = site_lats[None, :]
        slon = site_lons[None, :]
        dlat = np.radians(slat - clat)
        dlon = np.radians(slon - clon)
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(np.radians(clat)) * np.cos(np.radians(slat)) * np.sin(dlon / 2) ** 2
        )
        dist = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))
        dist_min[i0:i1] = dist.min(axis=1)
    return dist_min.reshape(NROWS, NCOLS).astype(np.float32)


def nearest_nexrad_site_index(
    lat_grid: np.ndarray | None = None,
    lon_grid: np.ndarray | None = None,
) -> np.ndarray:
    """Per-cell index into ``nexrad_sites_conus()`` for the nearest WSR-88D."""
    if lat_grid is None or lon_grid is None:
        lat_grid, lon_grid = cell_center_latlon()
    site_lats, site_lons, _ = nexrad_sites_conus()
    flat_lat = lat_grid.ravel()
    flat_lon = lon_grid.ravel()
    n_cells = flat_lat.size
    n_sites = site_lats.size
    chunk = 50_000
    idx_min = np.zeros(n_cells, dtype=np.int16)
    dist_min = np.full(n_cells, np.inf, dtype=np.float64)
    for i0 in range(0, n_cells, chunk):
        i1 = min(i0 + chunk, n_cells)
        clat = flat_lat[i0:i1][:, None]
        clon = flat_lon[i0:i1][:, None]
        slat = site_lats[None, :]
        slon = site_lons[None, :]
        dlat = np.radians(slat - clat)
        dlon = np.radians(slon - clon)
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(np.radians(clat)) * np.cos(np.radians(slat)) * np.sin(dlon / 2) ** 2
        )
        dist = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))
        arg = dist.argmin(axis=1)
        dist_min[i0:i1] = dist[np.arange(i1 - i0), arg]
        idx_min[i0:i1] = arg
    return idx_min.reshape(NROWS, NCOLS)


def ensure_nearest_site_index_grid(cache_path: Path | None = None) -> np.ndarray:
    """Load or compute per-cell nearest-radar site index."""
    path = Path(cache_path or NEAREST_SITE_NPY)
    if path.exists():
        arr = np.load(path)
        if arr.shape == (NROWS, NCOLS):
            return arr.astype(np.int16)
    arr = nearest_nexrad_site_index()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, arr)
    return arr


def ensure_range_km_grid(cache_path: Path | None = None) -> np.ndarray:
    """Load or compute the per-cell nearest-radar distance grid."""
    path = Path(cache_path or RANGE_KM_NPY)
    if path.exists():
        arr = np.load(path)
        if arr.shape == (NROWS, NCOLS):
            return arr.astype(np.float32)
    arr = nearest_radar_distance_km()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, arr)
    return arr


def write_nexrad_sites_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _, _, ids = nexrad_sites_conus()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "lat", "lon"])
        for sid in ids:
            lat, lon = _NEXRAD_CONUS[sid]
            w.writerow([sid, lat, lon])


def _bin_index(range_km: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.clip(np.digitize(range_km, edges, right=False) - 1, 0, len(edges) - 2)


def range_bin_centers(edges: np.ndarray) -> np.ndarray:
    return ((edges[:-1] + edges[1:]) / 2.0).astype(np.float32)


def fit_range_debias_factors(
    pairs: list[dict],
    *,
    min_report_in: float = 1.0,
    min_mesh_mm: float = 5.0,
    edges: np.ndarray | None = None,
    reference_range_km: float = REFERENCE_RANGE_KM,
    clip: tuple[float, float] = (0.45, 1.15),
) -> dict:
    """
    Fit multiplicative debias factors from SPC–MESH pairs.

    Factor multiplies MESH so that median(report/MESH) → 1 at each range bin.
    Normalized to 1.0 at ``reference_range_km``.
    """
    edges = np.asarray(edges if edges is not None else DEFAULT_RANGE_BIN_EDGES_KM, dtype=np.float32)
    centers = range_bin_centers(edges)
    sources = ("MYRORSS", "GridRad", "MRMS")
    raw: dict[str, list[tuple[float, float]]] = {s: [] for s in sources}

    site_lats, site_lons, _ = nexrad_sites_conus()
    for p in pairs:
        if p.get("spc_size_in", 0) < min_report_in:
            continue
        mesh = float(p.get("mesh75_mm", 0))
        if mesh < min_mesh_mm:
            continue
        lat, lon = float(p["lat"]), float(p["lon"])
        src = classify_mesh_source_from_yyyymmdd(str(p["date"]))
        # Nearest-site distance at report location.
        dlat = np.radians(site_lats - lat)
        dlon = np.radians(site_lons - lon)
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(np.radians(lat)) * np.cos(np.radians(site_lats)) * np.sin(dlon / 2) ** 2
        )
        dist = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))
        r_km = float(dist.min())
        ratio = (float(p["spc_size_in"]) * MM_PER_INCH) / mesh
        raw[src].append((r_km, ratio))

    factors: dict[str, np.ndarray] = {}
    for src in sources:
        fac = np.ones(len(centers), dtype=np.float32)
        if raw[src]:
            rs = np.array([t[0] for t in raw[src]], dtype=np.float32)
            ratios = np.array([t[1] for t in raw[src]], dtype=np.float32)
            for bi in range(len(centers)):
                lo, hi = edges[bi], edges[bi + 1]
                mask = (rs >= lo) & (rs < hi)
                if mask.sum() >= 30:
                    fac[bi] = float(np.median(ratios[mask]))
        # Fill empty bins by linear interpolation along centers.
        valid = np.isfinite(fac) & (fac > 0)
        if valid.sum() >= 2:
            fac = np.interp(centers, centers[valid], fac[valid]).astype(np.float32)
        ref_idx = int(np.argmin(np.abs(centers - reference_range_km)))
        ref = fac[ref_idx] if fac[ref_idx] > 0 else 1.0
        fac = fac / ref
        fac = np.clip(fac, clip[0], clip[1]).astype(np.float32)
        factors[src] = fac

    return {
        "range_bin_edges_km": edges,
        "range_bin_centers_km": centers,
        "factors": factors,
        "n_pairs": {s: len(raw[s]) for s in sources},
    }


def save_range_debias(fit: dict, path: Path | None = None) -> Path:
    path = Path(path or RANGE_DEBIAS_NPZ)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        range_bin_edges_km=fit["range_bin_edges_km"],
        range_bin_centers_km=fit["range_bin_centers_km"],
        factor_myrorss=fit["factors"]["MYRORSS"],
        factor_gridrad=fit["factors"]["GridRad"],
        factor_mrms=fit["factors"]["MRMS"],
        reference_range_km=np.float32(REFERENCE_RANGE_KM),
    )
    return path


def load_range_debias(path: Path | None = None) -> dict | None:
    path = Path(path or RANGE_DEBIAS_NPZ)
    if not path.exists():
        return None
    z = np.load(path)
    return {
        "range_bin_edges_km": z["range_bin_edges_km"],
        "range_bin_centers_km": z["range_bin_centers_km"],
        "factors": {
            "MYRORSS": z["factor_myrorss"],
            "GridRad": z["factor_gridrad"],
            "MRMS": z["factor_mrms"],
        },
        "reference_range_km": float(z["reference_range_km"]),
    }


def apply_range_debias(
    data: np.ndarray,
    range_km_grid: np.ndarray,
    source: str,
    debias: dict,
) -> np.ndarray:
    """Multiply MESH by range-dependent factors (per source era)."""
    src = source if source in debias["factors"] else "GridRad"
    if src == "MYRORSS/MRMS":
        src = "MRMS" if "MRMS" in debias["factors"] else "MYRORSS"
    factors = debias["factors"].get(src)
    if factors is None:
        return data
    edges = debias["range_bin_edges_km"]
    centers = debias["range_bin_centers_km"]
    fac_2d = np.interp(range_km_grid.ravel(), centers, factors).reshape(NROWS, NCOLS)
    out = data.astype(np.float32) * fac_2d.astype(np.float32)
    return out


SPECKLE_THRESH = 2.5
SPECKLE_ACTIVE_MM = 5.0


def remove_speckle_spikes(
    data: np.ndarray,
    *,
    speckle_thresh: float = SPECKLE_THRESH,
    active_mm: float = SPECKLE_ACTIVE_MM,
) -> tuple[np.ndarray, int]:
    """
    Zero isolated spikes: active cells > ``speckle_thresh`` × local 3×3 median.

    Matches the diagnostic definition in ``radar_artifact_diagnostic.py``.
    """
    from scipy.ndimage import median_filter

    out = data.astype(np.float32, copy=True)
    active = out >= active_mm
    if not np.any(active):
        return out, 0
    med = median_filter(out, size=3, mode="nearest")
    speckle = active & (out > speckle_thresh * np.maximum(med, 1.0))
    n = int(speckle.sum())
    if n:
        out[speckle] = 0.0
    return out, n


# Ring/spoke artifacts: cells along a range annulus share elevated values (3×3 test misses them).
AZIMUTH_ANNULUS_FACTOR = 2.5
AZIMUTH_MIN_ANNULUS_CELLS = 8
# Uniform range rings: entire annulus elevated vs adjacent radial bins at the same site.
RADIAL_RING_FACTOR = 1.12
RADIAL_RING_FAR_FACTOR = 1.18
RADIAL_RING_INNER_RANGE_KM = 75.0
RADIAL_RING_MIN_OUTER_RANGE_KM = 50.0
RADIAL_RING_FAR_RANGE_KM = 100.0
RADIAL_RING_MIN_ANNULUS_CELLS = 5
RADIAL_RING_CELL_MARGIN_MM = 5.0
FILAMENT_BG_SIZE = 21  # ~1° at 0.05° grid — wider than typical ring width
FILAMENT_MARGIN_MM = 20.0
FILAMENT_QUIET_BG_MM = 15.0

# Pass 5: spatiotemporal range-ring persistence (Stage 05 rolling history).
# NEXRAD range rings are stationary in (site, range) but ephemeral storms are not.
# Chilson et al. (2018) and roost-detection work use multi-scan dynamics; on daily
# grids we approximate this with a trailing window of pre-filter GridRad rasters.
PERSISTENCE_ACTIVE_MM = 25.4
PERSISTENCE_MIN_HISTORY_DAYS = 7
PERSISTENCE_HISTORY_MAX_DAYS = 21
PERSISTENCE_RANGE_FRAC = 0.60  # annulus active on ≥60% of prior days
PERSISTENCE_CELL_FRAC = 0.35  # cell active on ≥35% of prior days
PERSISTENCE_BURST_FACTOR = 1.75  # keep rare extreme revisits
PERSISTENCE_ANNULUS_BURST_FACTOR = 1.50  # coordinated storm on a usually-noisy annulus

# Site-specific remediation (visual QA on GridRad−MYRORSS diff map, 2026-07-07).
# Murillo et al. (2021) manually excluded failed radar volumes; Cintineo et al. (2012)
# cropped radial fragments by hand. These nine sites retained spoke/ring streaks after the
# global four-pass filter; Stage 05 applies a fifth pass with stricter thresholds and a
# polar (range × azimuth) spoke test only under their nearest-radar domains.
SITE_REMEDIATION_IDS: tuple[str, ...] = (
    "KLRX",  # northern Nevada (Elko)
    "KEMX",  # southern Arizona (Tucson)
    "KBLX",  # south-central Montana (Billings)
    "KGRR",  # west-central Michigan (Grand Rapids)
    "KGWX",  # northwest Alabama (Columbus AFB / west AL)
    "KTLX",  # east-central Oklahoma (Oklahoma City)
    "KILN",  # southwest Ohio (Wilmington)
    "KHPX",  # southwest Kentucky (Fort Campbell)
    "KDOX",  # central Delaware (Dover)
)
SITE_SPECKLE_THRESH = 2.0
SITE_AZIMUTH_ANNULUS_FACTOR = 1.6
SITE_RADIAL_RING_FACTOR = 1.05
SITE_RADIAL_RING_FAR_FACTOR = 1.10
SITE_FILAMENT_MARGIN_MM = 12.0
SITE_SPOKE_AZIMUTH_BIN_DEG = 15.0
SITE_SPOKE_FACTOR = 1.5
SITE_SPOKE_MIN_CELLS = 4


def remove_radial_range_rings(
    data: np.ndarray,
    site_idx_grid: np.ndarray,
    range_km_grid: np.ndarray,
    *,
    edges: np.ndarray | None = None,
    active_mm: float = SPECKLE_ACTIVE_MM,
    ring_factor: float = RADIAL_RING_FACTOR,
    far_ring_factor: float = RADIAL_RING_FAR_FACTOR,
    inner_range_km: float = RADIAL_RING_INNER_RANGE_KM,
    min_outer_range_km: float = RADIAL_RING_MIN_OUTER_RANGE_KM,
    far_range_km: float = RADIAL_RING_FAR_RANGE_KM,
    min_annulus_cells: int = RADIAL_RING_MIN_ANNULUS_CELLS,
    cell_margin_mm: float = RADIAL_RING_CELL_MARGIN_MM,
) -> tuple[np.ndarray, int]:
    """
    Zero cells on range annuli that sit high vs adjacent radial bins at the same site.

    Isolated-speckle and azimuthal passes miss **uniform** range rings: every azimuth
    on the annulus is elevated so the annulus median tracks the ring. Compare each
    (site, range bin) median to neighbor bins and to the inner-range (≤75 km) baseline.
    The inner reference catches wide mid-range plateaus where several adjacent bins are
    jointly elevated (common in Oklahoma / Plains overlap regions).
    """
    edges = np.asarray(edges if edges is not None else RADIAL_RING_BIN_EDGES_KM, dtype=np.float32)
    centers = ((edges[:-1] + edges[1:]) / 2.0).astype(np.float32)
    out = data.astype(np.float32, copy=True)
    active = out >= active_mm
    if not np.any(active):
        return out, 0
    bin_idx = _bin_index(range_km_grid, edges)
    site_idx = site_idx_grid.astype(np.int16, copy=False)
    n_bins = len(edges) - 1
    n_sites = int(site_idx.max()) + 1
    medians = np.full((n_sites, n_bins), np.nan, dtype=np.float32)
    for si in range(n_sites):
        site_mask = site_idx == si
        if not site_mask.any():
            continue
        for bi in range(n_bins):
            mask = active & site_mask & (bin_idx == bi)
            if int(mask.sum()) < min_annulus_cells:
                continue
            medians[si, bi] = float(np.median(out[mask]))

    def _neighbor_median(row: np.ndarray, bi: int) -> float | None:
        vals: list[float] = []
        for off in (-2, -1, 1, 2):
            j = bi + off
            if 0 <= j < n_bins and np.isfinite(row[j]):
                vals.append(float(row[j]))
        if not vals:
            return None
        return float(np.median(vals))

    remove = np.zeros(data.shape, dtype=bool)
    for si in range(n_sites):
        site_mask = site_idx == si
        row = medians[si]
        inner_vals = [
            float(row[bi])
            for bi in range(n_bins)
            if np.isfinite(row[bi]) and float(centers[bi]) <= inner_range_km
        ]
        inner_ref = float(np.median(inner_vals)) if inner_vals else np.nan
        for bi in range(n_bins):
            med_b = row[bi]
            if not np.isfinite(med_b):
                continue
            nbr = _neighbor_median(row, bi)
            if nbr is None and not np.isfinite(inner_ref):
                continue
            ref = max(nbr if nbr is not None else 0.0, 1.0)
            if float(centers[bi]) >= min_outer_range_km and np.isfinite(inner_ref):
                ref = max(ref, inner_ref)
            thresh_factor = far_ring_factor if float(centers[bi]) > far_range_km else ring_factor
            if med_b <= thresh_factor * ref:
                continue
            excess = med_b - ref
            cell_thresh = ref + max(cell_margin_mm, 0.5 * excess)
            mask = active & site_mask & (bin_idx == bi)
            remove |= mask & (out > cell_thresh)
    n_removed = int(remove.sum())
    if n_removed:
        out[remove] = 0.0
    return out, n_removed


def remove_azimuthal_ring_artifacts(
    data: np.ndarray,
    site_idx_grid: np.ndarray,
    range_km_grid: np.ndarray,
    *,
    edges: np.ndarray | None = None,
    active_mm: float = SPECKLE_ACTIVE_MM,
    annulus_factor: float = AZIMUTH_ANNULUS_FACTOR,
    min_annulus_cells: int = AZIMUTH_MIN_ANNULUS_CELLS,
) -> tuple[np.ndarray, int]:
    """
    Zero azimuthal outliers on a radar range annulus (spokes, hot pixels on rings).

    For each (nearest site, range bin), active cells above ``annulus_factor`` × the
    annulus median MESH are removed. Real storm cores usually span many range bins;
    thin radial spokes on one annulus are suppressed.
    """
    edges = np.asarray(edges if edges is not None else DEFAULT_RANGE_BIN_EDGES_KM, dtype=np.float32)
    out = data.astype(np.float32, copy=True)
    active = out >= active_mm
    if not np.any(active):
        return out, 0
    bin_idx = _bin_index(range_km_grid, edges)
    site_idx = site_idx_grid.astype(np.int16, copy=False)
    remove = np.zeros(data.shape, dtype=bool)
    n_bins = len(edges) - 1
    n_sites = int(site_idx.max()) + 1
    for si in range(n_sites):
        site_mask = site_idx == si
        if not site_mask.any():
            continue
        for bi in range(n_bins):
            mask = active & site_mask & (bin_idx == bi)
            n = int(mask.sum())
            if n < min_annulus_cells:
                continue
            med = float(np.median(out[mask]))
            thresh = annulus_factor * max(med, 1.0)
            remove |= mask & (out > thresh)
    n_removed = int(remove.sum())
    if n_removed:
        out[remove] = 0.0
    return out, n_removed


def remove_background_filament_artifacts(
    data: np.ndarray,
    *,
    active_mm: float = SPECKLE_ACTIVE_MM,
    bg_size: int = FILAMENT_BG_SIZE,
    margin_mm: float = FILAMENT_MARGIN_MM,
    quiet_bg_mm: float = FILAMENT_QUIET_BG_MM,
) -> tuple[np.ndarray, int]:
    """
    Zero thin high filaments in an otherwise quiet background (partial range rings).

    Uses a wide median background; removes active cells far above background when
    the local background is below ``quiet_bg_mm``.
    """
    from scipy.ndimage import median_filter

    out = data.astype(np.float32, copy=True)
    active = out >= active_mm
    if not np.any(active):
        return out, 0
    bg = median_filter(out, size=bg_size, mode="nearest")
    artifact = active & (bg < quiet_bg_mm) & (out > bg + margin_mm)
    n = int(artifact.sum())
    if n:
        out[artifact] = 0.0
    return out, n


def remove_persistent_range_artifacts(
    data: np.ndarray,
    site_idx_grid: np.ndarray,
    range_km_grid: np.ndarray,
    history: np.ndarray | None,
    *,
    edges: np.ndarray | None = None,
    active_mm: float = PERSISTENCE_ACTIVE_MM,
    min_history_days: int = PERSISTENCE_MIN_HISTORY_DAYS,
    range_frac: float = PERSISTENCE_RANGE_FRAC,
    cell_frac: float = PERSISTENCE_CELL_FRAC,
    burst_factor: float = PERSISTENCE_BURST_FACTOR,
    annulus_burst_factor: float = PERSISTENCE_ANNULUS_BURST_FACTOR,
    min_annulus_cells: int = RADIAL_RING_MIN_ANNULUS_CELLS,
) -> tuple[np.ndarray, int]:
    """
    Zero cells on chronically active (site, range) annuli using trailing daily history.

    Range rings reappear at the same radar distance across many days; real hail cores
    are episodic at fixed grid cells. Requires ``history`` shaped
    ``(n_days, nrows, ncols)`` of pre-artifact-filter MESH (post calibration/debias).
    """
    if history is None or history.ndim != 3 or history.shape[0] < min_history_days:
        return data.astype(np.float32, copy=True), 0
    if history.shape[1:] != data.shape:
        return data.astype(np.float32, copy=True), 0

    edges = np.asarray(edges if edges is not None else RADIAL_RING_BIN_EDGES_KM, dtype=np.float32)
    out = data.astype(np.float32, copy=True)
    active = out >= active_mm
    if not np.any(active):
        return out, 0

    hist_active = history >= active_mm
    n_days = hist_active.shape[0]
    bin_idx = _bin_index(range_km_grid, edges)
    site_idx = site_idx_grid.astype(np.int16, copy=False)
    n_bins = len(edges) - 1
    n_sites = int(site_idx.max()) + 1

    annulus_day_frac = np.zeros((n_sites, n_bins), dtype=np.float32)
    annulus_hist_med = np.full((n_sites, n_bins), np.nan, dtype=np.float32)
    annulus_today_med = np.full((n_sites, n_bins), np.nan, dtype=np.float32)

    for si in range(n_sites):
        site_mask = site_idx == si
        if not site_mask.any():
            continue
        for bi in range(n_bins):
            ann_mask = site_mask & (bin_idx == bi)
            n_cells = int(ann_mask.sum())
            if n_cells < min_annulus_cells:
                continue
            day_hits = np.array(
                [bool(hist_active[d][ann_mask].any()) for d in range(n_days)],
                dtype=np.float32,
            )
            annulus_day_frac[si, bi] = float(day_hits.mean())
            annulus_hist_med[si, bi] = float(np.median(history[:, ann_mask]))
            if active[ann_mask].any():
                annulus_today_med[si, bi] = float(np.median(out[ann_mask]))

    cell_hist_frac = hist_active.mean(axis=0)
    cell_hist_med = np.median(history, axis=0)

    remove = np.zeros(data.shape, dtype=bool)
    si_grid = site_idx
    bi_grid = bin_idx
    persistent_annulus = annulus_day_frac[si_grid, bi_grid] >= range_frac

    storm_annulus = np.isfinite(annulus_today_med[si_grid, bi_grid]) & np.isfinite(
        annulus_hist_med[si_grid, bi_grid]
    )
    storm_annulus &= (
        annulus_today_med[si_grid, bi_grid]
        >= annulus_burst_factor * np.maximum(annulus_hist_med[si_grid, bi_grid], 1.0)
    )
    storm_annulus &= annulus_today_med[si_grid, bi_grid] >= active_mm

    chronic_cell = cell_hist_frac >= cell_frac
    burst_cell = out >= burst_factor * np.maximum(cell_hist_med, 1.0)

    remove = (
        active
        & persistent_annulus
        & chronic_cell
        & ~burst_cell
        & ~storm_annulus
    )
    n_removed = int(remove.sum())
    if n_removed:
        out[remove] = 0.0
    return out, n_removed


def site_remediation_indices(site_ids: tuple[str, ...] | None = None) -> np.ndarray:
    """Integer site indices for ``SITE_REMEDIATION_IDS`` (or override list)."""
    _, _, all_ids = nexrad_sites_conus()
    id_to_idx = {sid: i for i, sid in enumerate(all_ids)}
    want = site_ids if site_ids is not None else SITE_REMEDIATION_IDS
    return np.array([id_to_idx[s] for s in want if s in id_to_idx], dtype=np.int16)


def remediation_site_mask(site_idx_grid: np.ndarray, site_ids: tuple[str, ...] | None = None) -> np.ndarray:
    """True where the nearest WSR-88D is in the remediation list."""
    return np.isin(site_idx_grid, site_remediation_indices(site_ids))


def _restrict_removals_to_sites(
    before: np.ndarray,
    after: np.ndarray,
    site_mask: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Apply zeros from ``after`` only on cells flagged by ``site_mask``."""
    out = before.astype(np.float32, copy=True)
    removed = site_mask & (before != after)
    n = int(removed.sum())
    if n:
        out[removed] = 0.0
    return out, n


def cell_azimuth_deg_from_site(
    site_lat: float,
    site_lon: float,
    cell_lat: np.ndarray,
    cell_lon: np.ndarray,
) -> np.ndarray:
    """Azimuth (degrees, 0–360) from radar site to each cell."""
    dlon = np.radians(cell_lon - site_lon)
    dlat = np.radians(cell_lat - site_lat)
    return np.degrees(np.arctan2(dlon * np.cos(np.radians(site_lat)), dlat)) % 360.0


def remove_site_polar_spokes(
    data: np.ndarray,
    site_idx_grid: np.ndarray,
    range_km_grid: np.ndarray,
    *,
    site_ids: tuple[str, ...] | None = None,
    azimuth_bin_deg: float = SITE_SPOKE_AZIMUTH_BIN_DEG,
    edges: np.ndarray | None = None,
    active_mm: float = SPECKLE_ACTIVE_MM,
    spoke_factor: float = SITE_SPOKE_FACTOR,
    min_cells: int = SITE_SPOKE_MIN_CELLS,
) -> tuple[np.ndarray, int]:
    """
    Polar spoke filter for flagged sites: per (site, range bin, azimuth sector),
    zero active cells above ``spoke_factor`` × sector median.

    WSR-88D clutter algorithms apply median filters in range and azimuth after
    identifying anomalous gates; this is the Cartesian-grid analogue for residual
    radial streaks that survive the global azimuthal annulus pass.
    """
    edges = np.asarray(edges if edges is not None else RADIAL_RING_BIN_EDGES_KM, dtype=np.float32)
    _, _, all_ids = nexrad_sites_conus()
    nrows, ncols = data.shape
    lats = LAT_MAX - (np.arange(nrows, dtype=np.float64) + 0.5) * DX
    lons = LON_MIN + (np.arange(ncols, dtype=np.float64) + 0.5) * DX
    lat_grid = np.broadcast_to(lats[:, None], (nrows, ncols))
    lon_grid = np.broadcast_to(lons[None, :], (nrows, ncols))
    out = data.astype(np.float32, copy=True)
    active = out >= active_mm
    if not np.any(active):
        return out, 0
    range_bin = _bin_index(range_km_grid, edges)
    n_az_bins = int(np.ceil(360.0 / azimuth_bin_deg))
    remove = np.zeros(data.shape, dtype=bool)
    remediation = site_remediation_indices(site_ids)
    for si in remediation:
        site_mask = site_idx_grid == si
        if not site_mask.any():
            continue
        sid = all_ids[int(si)]
        site_lat, site_lon = _NEXRAD_CONUS[sid]
        az = cell_azimuth_deg_from_site(site_lat, site_lon, lat_grid, lon_grid)
        az_bin = np.clip((az / azimuth_bin_deg).astype(np.int16), 0, n_az_bins - 1)
        n_bins = len(edges) - 1
        for bi in range(n_bins):
            for ai in range(n_az_bins):
                mask = active & site_mask & (range_bin == bi) & (az_bin == ai)
                n = int(mask.sum())
                if n < min_cells:
                    continue
                med = float(np.median(out[mask]))
                thresh = spoke_factor * max(med, 1.0)
                remove |= mask & (out > thresh)
    n_removed = int(remove.sum())
    if n_removed:
        out[remove] = 0.0
    return out, n_removed


def remove_flagged_site_artifacts(
    data: np.ndarray,
    site_idx_grid: np.ndarray,
    range_km_grid: np.ndarray,
    *,
    site_ids: tuple[str, ...] | None = None,
) -> tuple[np.ndarray, dict[str, int]]:
    """
    Fifth pass: stricter artifact removal under nine QA-flagged WSR-88D domains.

    Re-runs speckle, radial-ring, azimuthal, and filament tests with tighter
    thresholds, then applies a polar spoke filter. Only cells whose nearest radar
    is in ``SITE_REMEDIATION_IDS`` are modified.
    """
    site_mask = remediation_site_mask(site_idx_grid, site_ids)
    if not site_mask.any():
        return data.astype(np.float32, copy=True), {}
    out = data.astype(np.float32, copy=True)
    counts: dict[str, int] = {}

    tmp, _ = remove_speckle_spikes(out, speckle_thresh=SITE_SPECKLE_THRESH)
    out, counts["site_isolated"] = _restrict_removals_to_sites(out, tmp, site_mask)

    tmp, _ = remove_radial_range_rings(
        out,
        site_idx_grid,
        range_km_grid,
        ring_factor=SITE_RADIAL_RING_FACTOR,
        far_ring_factor=SITE_RADIAL_RING_FAR_FACTOR,
    )
    out, counts["site_radial_ring"] = _restrict_removals_to_sites(out, tmp, site_mask)

    tmp, _ = remove_azimuthal_ring_artifacts(
        out, site_idx_grid, range_km_grid, annulus_factor=SITE_AZIMUTH_ANNULUS_FACTOR,
    )
    out, counts["site_azimuthal"] = _restrict_removals_to_sites(out, tmp, site_mask)

    tmp, _ = remove_background_filament_artifacts(out, margin_mm=SITE_FILAMENT_MARGIN_MM)
    out, counts["site_filament"] = _restrict_removals_to_sites(out, tmp, site_mask)

    out, n_spoke = remove_site_polar_spokes(
        out, site_idx_grid, range_km_grid, site_ids=site_ids,
    )
    counts["site_polar_spoke"] = n_spoke
    return out, counts


def remove_gridrad_artifacts(
    data: np.ndarray,
    range_km_grid: np.ndarray,
    site_idx_grid: np.ndarray,
    *,
    history: np.ndarray | None = None,
    site_remediation: bool = False,
) -> tuple[np.ndarray, dict[str, int]]:
    """Full GridRad artifact pass: spatial four passes + spatiotemporal persistence."""
    out, n_iso = remove_speckle_spikes(data)
    out, n_rad = remove_radial_range_rings(out, site_idx_grid, range_km_grid)
    out, n_az = remove_azimuthal_ring_artifacts(out, site_idx_grid, range_km_grid)
    out, n_fil = remove_background_filament_artifacts(out)
    out, n_persist = remove_persistent_range_artifacts(
        out, site_idx_grid, range_km_grid, history,
    )
    counts = {
        "isolated": n_iso,
        "radial_ring": n_rad,
        "azimuthal": n_az,
        "filament": n_fil,
        "persistent_range": n_persist,
    }
    if site_remediation:
        out, site_counts = remove_flagged_site_artifacts(out, site_idx_grid, range_km_grid)
        counts.update(site_counts)
    return out, counts
