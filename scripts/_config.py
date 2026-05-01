"""
_config.py — Single source of truth for grid geometry and pipeline constants.

All stage scripts must import grid constants from here rather than redefining
them inline. Any change to grid geometry requires a model-version bump
(update MODEL_VERSION below) and a full pipeline rerun from Stage 01.

Usage in stage scripts:
    from _config import NROWS, NCOLS, DX, LAT_MAX, LON_MIN
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT
    from _config import DAMAGE_THRESH_MM, RP_YEARS

DO NOT import this module from run_pipeline.py's __main__ block using
a relative import — use sys.path insertion or `importlib` if needed.
Stage scripts add their parent directory to sys.path via REPO_ROOT resolution,
so `from _config import ...` works when scripts are run from repo root.

v2.1 Note: Grid constants are intentionally fixed for the lifetime of v2.1.
The "0.05° grid is fixed" rule is a non-negotiable implementation constraint.
"""

from __future__ import annotations

from pathlib import Path

# ── Model version ─────────────────────────────────────────────────────────────
MODEL_VERSION: str = "2.1.0"

# ── Grid geometry (0.05° CONUS) ───────────────────────────────────────────────
# These values define the authoritative grid for all raster I/O.
# Row 0 = northernmost row; Col 0 = westernmost column.
DX: float = 0.05          # degree; ~5.5 km at mid-latitudes
NROWS: int = 520           # latitude cells: 50.005°N → 23.995°N
NCOLS: int = 1180          # longitude cells: 125.005°W → 65.995°W
LAT_MAX: float = 50.005    # north edge of row 0, degrees N
LON_MIN: float = -125.005  # west edge of col 0, degrees E (negative = W)
CRS: str = "EPSG:4326"

# Derived grid bounds
LAT_MIN: float = LAT_MAX - NROWS * DX   # 23.995°N
LON_MAX: float = LON_MIN + NCOLS * DX   # -65.995°E

# Total active cells (pre-masking)
N_CELLS: int = NROWS * NCOLS            # 613,600

# ── Repository paths ──────────────────────────────────────────────────────────
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_ROOT: Path = REPO_ROOT / "data"
LOG_ROOT: Path = REPO_ROOT / "logs"

HISTORICAL: Path = DATA_ROOT / "historical"
ANALYSIS: Path = DATA_ROOT / "analysis"
STOCHASTIC: Path = DATA_ROOT / "stochastic"
DOCS_FIG: Path = REPO_ROOT / "docs" / "figures"

# Sub-directories used by multiple stages
MESH_CORR_DIR: Path = HISTORICAL / "mesh_0.05deg_corrected"
MESH_CLIMO_DIR: Path = HISTORICAL / "mesh_0.05deg_climo"
ERA5_DIR: Path = HISTORICAL / "era5"
SPC_DIR: Path = HISTORICAL / "spc"
EVENTS_DIR: Path = HISTORICAL / "events"
CDF_DIR: Path = ANALYSIS / "cdf"
OCC_DIR: Path = ANALYSIS / "occurrence"
TOPO_DIR: Path = ANALYSIS / "topography"
VULN_DIR: Path = ANALYSIS / "vulnerability"
MASK_DIR: Path = ANALYSIS / "conus_mask"

# ── Physical constants and thresholds ────────────────────────────────────────
DAMAGE_THRESH_MM: float = 25.4   # 1.0 inch — minimum hail for damage consideration
MAX_HAIL_MM: float = 250.0       # hard cap on MESH75 values (physical upper bound)
MM_PER_INCH: float = 25.4        # unit conversion

# MESH75 formula coefficients (Murillo & Homeyer 2021, Eq. 3, corrigendum)
MESH75_A: float = 15.096  # pre-factor
MESH75_B: float = 0.206   # exponent on SHI

# Witt (1998) SHI→MESH conversion (used for MYRORSS/MRMS — kept for reference)
WITT_INCH_TO_CM: float = 2.54
WITT_RATIO_EXP: float = 0.412

# ── EVT / return-period defaults ──────────────────────────────────────────────
RP_YEARS: tuple[int, ...] = (10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000)

# Stage 10 spatial smoothing defaults
POOL_RADIUS_KM: float = 150.0   # radius of pooling kernel
DECAY_KM: float = 75.0          # exponential decay length

# Stage 09 EVT defaults
N_REGIONS_DEFAULT: int = 6      # K-means clusters for regional ξ pooling
GPD_THRESH_MM_DEFAULT: float = 50.8  # 2.0 inches — starting threshold for MRL search

# ── Stochastic simulation defaults ───────────────────────────────────────────
RNG_SEED: int = 42
N_SIM_YEARS: int = 50_000
TRANSLATE_CELLS: int = 3        # maximum ±cell translation per event footprint

# ── Stage 08 event grouping thresholds ───────────────────────────────────────
MAX_CENTROID_KM_DAY: float = 150.0   # maximum centroid displacement for merge
MAX_INTENSITY_RATIO: float = 3.0     # maximum daily peak MESH75 ratio for merge

# ── Occurrence probability thresholds ────────────────────────────────────────
OCC_THRESHOLDS_INCH: tuple[float, ...] = (0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00)
OCC_THRESHOLDS_MM: tuple[float, ...] = tuple(t * MM_PER_INCH for t in OCC_THRESHOLDS_INCH)

# ── GeoTIFF I/O defaults ─────────────────────────────────────────────────────
GEOTIFF_PROFILE: dict = {
    "driver": "GTiff",
    "dtype": "float32",
    "width": NCOLS,
    "height": NROWS,
    "count": 1,
    "crs": CRS,
    # transform is set at write time via rasterio.transform.from_origin
    "compress": "lzw",
    "tiled": True,
    "blockxsize": 256,
    "blockysize": 256,
    "nodata": -1.0,
}

# ── Public API ────────────────────────────────────────────────────────────────
__all__ = [
    # Version
    "MODEL_VERSION",
    # Grid geometry
    "DX", "NROWS", "NCOLS", "LAT_MAX", "LON_MIN", "LAT_MIN", "LON_MAX",
    "CRS", "N_CELLS",
    # Paths
    "REPO_ROOT", "DATA_ROOT", "LOG_ROOT",
    "HISTORICAL", "ANALYSIS", "STOCHASTIC", "DOCS_FIG",
    "MESH_CORR_DIR", "MESH_CLIMO_DIR", "ERA5_DIR", "SPC_DIR",
    "EVENTS_DIR", "CDF_DIR", "OCC_DIR", "TOPO_DIR", "VULN_DIR", "MASK_DIR",
    # Physical constants
    "DAMAGE_THRESH_MM", "MAX_HAIL_MM", "MM_PER_INCH",
    "MESH75_A", "MESH75_B",
    "WITT_INCH_TO_CM", "WITT_RATIO_EXP",
    # EVT / RP
    "RP_YEARS", "POOL_RADIUS_KM", "DECAY_KM",
    "N_REGIONS_DEFAULT", "GPD_THRESH_MM_DEFAULT",
    # Stochastic
    "RNG_SEED", "N_SIM_YEARS", "TRANSLATE_CELLS",
    # Event grouping
    "MAX_CENTROID_KM_DAY", "MAX_INTENSITY_RATIO",
    # Occurrence
    "OCC_THRESHOLDS_INCH", "OCC_THRESHOLDS_MM",
    # I/O
    "GEOTIFF_PROFILE",
]
