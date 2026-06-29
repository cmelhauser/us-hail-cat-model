#!/usr/bin/env python3
"""
05_apply_mesh_bias_correction.py — Unified MESH Correction Pipeline
=====================================================================
Applies source-specific corrections to all daily MESH rasters, producing
a homogeneous MESH75 record across three input sources:

  MYRORSS (1998–2011):     Witt MESH → MESH75 recalibration + env filter
  GridRad (2012–2019):     Quantile-mapping cross-calibration + env filter
  Operational MRMS (2020+): Witt MESH → MESH75 recalibration + env filter

This stage ensures that downstream CDF fitting and stochastic generation
operate on a consistent, source-independent MESH75 field.

Internal Phases (run automatically in order)
---------------------------------------------
  Phase A — Build cross-calibration from overlap period (2005–2011)
    Both MYRORSS and GridRad outputs exist for these years. Phase A
    applies Witt→MESH75 to MYRORSS data, then builds a quantile-mapping
    transfer function aligning GridRad MESH75 to the MYRORSS distribution.
    Saved to: data/analysis/calibration/gridrad_quantile_map.npz

  Phase B — Apply source-specific corrections to ALL rasters
    For each daily raster:
    - MYRORSS/MRMS → Witt→MESH75 recalibration
    - GridRad → quantile-mapping cross-calibration
    Then apply environmental filter to all sources.
    Output to: data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif

MESH75 Recalibration (Witt-algorithm sources)
----------------------------------------------
  MESH75 = 15.096 × (MESH_witt / 2.54)^0.412
  (Murillo & Homeyer 2021 corrigendum)

GridRad Cross-Calibration
--------------------------
  GridRad MESH75 is systematically lower than MYRORSS/MRMS due to hourly
  temporal resolution, reflectivity smoothing, and coarser resolution.
  Quantile mapping aligns GridRad to MYRORSS using the overlap period.

Environmental Filtering (all sources)
--------------------------------------
  1. Noise floor: MESH75 < 5 mm → 0
  2. Subtropical winter (Nov–Feb): lat < 30°N requires MESH75 ≥ 29.0 mm (skill threshold)

Usage
-----
  python scripts/05_apply_mesh_bias_correction.py
  python scripts/05_apply_mesh_bias_correction.py --year 2005
  python scripts/05_apply_mesh_bias_correction.py --skip-calibration
  python scripts/05_apply_mesh_bias_correction.py --validate
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, NODATA, MAX_HAIL_MM, EVENT_ACTIVE_THRESH_MM
    from _io import sanitize_hail_values, write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, NODATA, MAX_HAIL_MM, EVENT_ACTIVE_THRESH_MM
    from scripts._io import sanitize_hail_values, write_geotiff
    from scripts._logging import get_logger

IN_DIR    = DATA_ROOT / "historical" / "mesh_0.05deg"
OUT_DIR   = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
CAL_DIR   = DATA_ROOT / "analysis" / "calibration"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "05_mesh_bias_correction.log"

QQ_FILE   = CAL_DIR / "gridrad_quantile_map.npz"
CQM_FILE  = CAL_DIR / "gridrad_cqm_model.pkl"
FILTER_FILE = CAL_DIR / "hail_filter_model.pkl"
DIAG_FILE = CAL_DIR / "calibration_diagnostics.csv"
FILTER_DIAG_FILE = CAL_DIR / "hail_filter_diagnostics.csv"

OUT_NROWS = NROWS
OUT_NCOLS = NCOLS
OUT_DX = DX
QA_MAX_HAIL_MM = MAX_HAIL_MM

WITT_A     = 2.54
WITT_B     = 0.5
MH19_A     = 15.096
MH19_B     = 0.206
RATIO_EXP  = 2.0 * MH19_B

MIN_MESH75_MM     = 5.0
MIN_MESH75_SEVERE = EVENT_ACTIVE_THRESH_MM

OVERLAP_START_YEAR = 2005
OVERLAP_END_YEAR   = 2011
GRIDRAD_CALIB_START_YEAR = 2012
GRIDRAD_CALIB_END_YEAR   = 2019
N_PERCENTILES      = 200
PERCENTILES        = np.linspace(0, 100, N_PERCENTILES + 1)
MIN_PAIRS          = 1000

_gridrad_days = None
_qq_gridrad   = None
_qq_myrorss   = None
_qq_type      = None
_cqm_model    = None
_filter_model = None

log = get_logger("05_apply_mesh_bias_correction", LOG_ROOT).info

def load_gridrad_days() -> set:
    global _gridrad_days
    if _gridrad_days is not None:
        return _gridrad_days
    gd_file = IN_DIR / "gridrad_days.txt"
    if not gd_file.exists():
        _gridrad_days = set()
    else:
        with open(gd_file) as f:
            _gridrad_days = set(line.strip() for line in f if line.strip())
    return _gridrad_days

def is_gridrad_source(datestr: str) -> bool:
    return datestr in load_gridrad_days()

def apply_mesh75_correction(data: np.ndarray) -> np.ndarray:
    """Convert Witt MESH → MESH75."""
    out = np.zeros_like(data)
    mask = data > 0
    if np.any(mask):
        shi_proxy = (data[mask] / WITT_A) ** (1.0 / WITT_B)
        out[mask] = MH19_A * (shi_proxy ** MH19_B)
    return out

def _collect_active_pixels(tif_path, *, as_mesh75: bool) -> list[float]:
    import rasterio

    try:
        with rasterio.open(tif_path) as src:
            data = src.read(1)
    except Exception:
        return []
    if as_mesh75:
        data = apply_mesh75_correction(data)
    active = data[data > MIN_MESH75_MM]
    return active.tolist() if active.size else []


def _collect_era_pooled_calibration() -> tuple[np.ndarray, np.ndarray]:
    """Pool MYRORSS-era and GridRad-era active pixels when same-day overlap is absent."""
    myrorss_vals: list[float] = []
    gridrad_vals: list[float] = []

    for year in range(OVERLAP_START_YEAR, OVERLAP_END_YEAR + 1):
        year_dir = IN_DIR / str(year)
        if not year_dir.exists():
            continue
        for tif_path in sorted(year_dir.glob("mesh_????????.tif")):
            datestr = tif_path.stem.replace("mesh_", "")
            if is_gridrad_source(datestr):
                continue
            myrorss_vals.extend(_collect_active_pixels(tif_path, as_mesh75=True))

    for year in range(GRIDRAD_CALIB_START_YEAR, GRIDRAD_CALIB_END_YEAR + 1):
        year_dir = IN_DIR / str(year)
        if not year_dir.exists():
            continue
        for tif_path in sorted(year_dir.glob("mesh_????????.tif")):
            datestr = tif_path.stem.replace("mesh_", "")
            if not is_gridrad_source(datestr):
                continue
            gridrad_vals.extend(_collect_active_pixels(tif_path, as_mesh75=False))

    return np.array(myrorss_vals, dtype=np.float32), np.array(gridrad_vals, dtype=np.float32)


def _save_quantile_map(gridrad_arr: np.ndarray, myrorss_arr: np.ndarray, correction_type: str) -> None:
    gr_q = np.percentile(gridrad_arr, PERCENTILES)
    my_q = np.percentile(myrorss_arr, PERCENTILES)
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(
        QQ_FILE,
        percentiles=PERCENTILES,
        gridrad_quantiles=gr_q,
        myrorss_quantiles=my_q,
        correction_type=correction_type,
        n_gridrad=len(gridrad_arr),
        n_myrorss=len(myrorss_arr),
    )
    with open(DIAG_FILE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["percentile", "gridrad_mm", "myrorss_mm", "ratio"])
        for p, g, m in zip(PERCENTILES, gr_q, my_q):
            ratio = m / g if g > 0 else np.nan
            w.writerow([f"{p:.1f}", f"{g:.2f}", f"{m:.2f}",
                        f"{ratio:.3f}" if np.isfinite(ratio) else ""])
    median_ratio = np.nanmedian(my_q[gr_q > 10] / gr_q[gr_q > 10])
    log(f"  Quantile map built ({correction_type}): median ratio (>10mm) = {median_ratio:.3f}")
    log(f"  GridRad p50={np.median(gridrad_arr):.1f} → MYRORSS p50={np.median(myrorss_arr):.1f} mm")
    log(f"  GridRad p95={np.percentile(gridrad_arr,95):.1f} → MYRORSS p95={np.percentile(myrorss_arr,95):.1f} mm")


def build_cross_calibration():
    """Phase A: build quantile mapping from overlap period."""
    import rasterio

    log("\n[Phase A] Building cross-calibration from overlap period")
    log(f"  Overlap: {OVERLAP_START_YEAR}–{OVERLAP_END_YEAR}")

    gridrad_days = load_gridrad_days()
    if not gridrad_days:
        log("  No GridRad days found — saving identity mapping")
        _save_default_calibration()
        return

    myrorss_vals = []
    gridrad_vals = []

    for year in range(OVERLAP_START_YEAR, OVERLAP_END_YEAR + 1):
        year_dir = IN_DIR / str(year)
        if not year_dir.exists():
            continue

        for tif_path in sorted(year_dir.glob("mesh_????????.tif")):
            datestr = tif_path.stem.replace("mesh_", "")
            try:
                with rasterio.open(tif_path) as src:
                    data = src.read(1)
            except Exception:
                continue

            active = data[data > 5.0]
            if len(active) == 0:
                continue

            if datestr in gridrad_days:
                gridrad_vals.extend(active.tolist())
            else:
                corrected = apply_mesh75_correction(data)
                active_corr = corrected[corrected > 5.0]
                if len(active_corr) > 0:
                    myrorss_vals.extend(active_corr.tolist())

    myrorss_arr = np.array(myrorss_vals, dtype=np.float32)
    gridrad_arr = np.array(gridrad_vals, dtype=np.float32)

    log(f"  MYRORSS pixel values: {len(myrorss_arr):,}")
    log(f"  GridRad pixel values: {len(gridrad_arr):,}")

    if len(gridrad_arr) < MIN_PAIRS or len(myrorss_arr) < MIN_PAIRS:
        log("  Insufficient same-day overlap — trying era-pooled MYRORSS vs GridRad calibration")
        myrorss_arr, gridrad_arr = _collect_era_pooled_calibration()
        log(f"  Era-pooled MYRORSS pixel values: {len(myrorss_arr):,}")
        log(f"  Era-pooled GridRad pixel values: {len(gridrad_arr):,}")
        if len(gridrad_arr) < MIN_PAIRS or len(myrorss_arr) < MIN_PAIRS:
            log("  Insufficient era-pooled data — using identity")
            _save_default_calibration()
            return
        _save_quantile_map(gridrad_arr, myrorss_arr, "era_pooled_quantile_mapping")
        return

    _save_quantile_map(gridrad_arr, myrorss_arr, "quantile_mapping")

def _save_default_calibration():
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(QQ_FILE,
             percentiles=PERCENTILES,
             gridrad_quantiles=np.linspace(0, 200, N_PERCENTILES + 1),
             myrorss_quantiles=np.linspace(0, 200, N_PERCENTILES + 1),
             correction_type="identity",
             note="No overlap data; 1:1 mapping")
    log("  Saved identity (1:1) mapping as fallback")

def load_qq_map():
    global _qq_gridrad, _qq_myrorss, _qq_type
    if _qq_gridrad is not None:
        return
    if not QQ_FILE.exists():
        _qq_type = "identity"
        return
    data = np.load(QQ_FILE, allow_pickle=True)
    _qq_type = str(data.get("correction_type", "identity"))
    _qq_gridrad = data.get("gridrad_quantiles")
    _qq_myrorss = data.get("myrorss_quantiles")

def apply_gridrad_calibration(data: np.ndarray) -> np.ndarray:
    load_qq_map()
    if _qq_type == "identity" or _qq_gridrad is None:
        return data
    out = data.copy()
    mask = out > 0
    if np.any(mask):
        out[mask] = np.interp(out[mask], _qq_gridrad, _qq_myrorss)
        out[out < 0] = 0
    return out

def _load_pickle_model(path: Path):
    """Load an optional model artifact. Missing or unreadable artifacts return None.

    This keeps Stage 05 deterministic and runnable without optional ML assets.
    """
    if not path.exists():
        return None
    try:
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        log(f"  WARN: could not load optional model {path.name}: {e}")
        return None

def _feature_matrix(data: np.ndarray, lat_grid: np.ndarray, day_of_year: int) -> np.ndarray:
    """Build a conservative, documented Stage 05 feature matrix.

    Feature order is stable for external model training:
      mesh_mm, latitude, day_of_year, month_sin, month_cos
    """
    month_angle = 2.0 * np.pi * ((max(1, min(366, int(day_of_year))) - 1) / 366.0)
    month_sin = np.full(data.shape, np.sin(month_angle), dtype=np.float32)
    month_cos = np.full(data.shape, np.cos(month_angle), dtype=np.float32)
    feats = np.column_stack([
        data.reshape(-1).astype(np.float32),
        lat_grid.reshape(-1).astype(np.float32),
        np.full(data.size, day_of_year, dtype=np.float32),
        month_sin.reshape(-1),
        month_cos.reshape(-1),
    ])
    return feats

def apply_optional_cqm(data: np.ndarray, lat_grid: np.ndarray, day_of_year: int,
                       skip_ml: bool = False) -> np.ndarray:
    """Apply optional conditional GridRad calibration model.

    If no artifact exists, or prediction fails, return the quantile-mapped result.
    """
    global _cqm_model
    fallback = apply_gridrad_calibration(data)
    if skip_ml:
        return fallback
    if _cqm_model is None:
        _cqm_model = _load_pickle_model(CQM_FILE)
    if _cqm_model is None:
        return fallback
    try:
        feats = _feature_matrix(data, lat_grid, day_of_year)
        pred = _cqm_model.predict(feats).reshape(data.shape).astype(np.float32)
        pred = np.where(np.isfinite(pred) & (pred > 0), pred, 0.0)
        # Never let a malformed optional model inflate values beyond the physical cap.
        repaired, _ = sanitize_hail_values(pred, max_hail_mm=QA_MAX_HAIL_MM, nodata=NODATA)
        return repaired
    except Exception as e:
        log(f"  WARN: conditional calibration failed; using quantile fallback: {e}")
        return fallback

def apply_probabilistic_filter(data: np.ndarray, day_of_year: int, lat_grid: np.ndarray,
                               skip_ml: bool = False) -> np.ndarray:
    """Apply optional probabilistic hail-realness filter with deterministic fallback.

    The deterministic environmental filter remains the baseline so the pipeline can run
    before any ML artifacts are trained.
    """
    global _filter_model
    deterministic = apply_environmental_filter(data, day_of_year, lat_grid)
    if skip_ml:
        return deterministic
    if _filter_model is None:
        _filter_model = _load_pickle_model(FILTER_FILE)
    if _filter_model is None:
        return deterministic
    try:
        feats = _feature_matrix(data, lat_grid, day_of_year)
        if hasattr(_filter_model, "predict_proba"):
            prob = _filter_model.predict_proba(feats)[:, 1]
        else:
            prob = _filter_model.predict(feats)
        prob = np.asarray(prob, dtype=np.float32).reshape(data.shape)
        prob = np.clip(np.nan_to_num(prob, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
        out = data * prob
        # Keep a small deterministic safety floor after weighting.
        out[out < MIN_MESH75_MM] = 0.0
        repaired, _ = sanitize_hail_values(out, max_hail_mm=QA_MAX_HAIL_MM, nodata=NODATA)
        return repaired
    except Exception as e:
        log(f"  WARN: probabilistic filter failed; using deterministic fallback: {e}")
        return deterministic

def apply_probabilistic_environmental_filter(data: np.ndarray, lat_grid: np.ndarray,
                                             month=None, day_of_year: int = 1,
                                             skip_ml: bool = False) -> np.ndarray:
    """Compatibility wrapper for the v2.1 optional environmental filter API."""
    return apply_probabilistic_filter(data, day_of_year, lat_grid, skip_ml=skip_ml)

def build_lat_grid() -> np.ndarray:
    lats = LAT_MAX - (np.arange(OUT_NROWS) + 0.5) * OUT_DX
    return np.broadcast_to(lats[:, np.newaxis], (OUT_NROWS, OUT_NCOLS))

def apply_environmental_filter(data, day_of_year, lat_grid):
    out = data.copy()
    out[out < MIN_MESH75_MM] = 0.0
    is_winter = (day_of_year >= 305) or (day_of_year <= 59)
    if is_winter:
        out[(lat_grid < 30.0) & (out < MIN_MESH75_SEVERE)] = 0.0
    return out

def process_file(in_path, out_path, lat_grid, skip_ml: bool = False):
    import rasterio

    if out_path.exists():
        return {"skipped": True}

    with rasterio.open(in_path) as src:
        data = src.read(1)
        profile = src.profile.copy()

    datestr = in_path.stem.replace("mesh_", "")
    doy = datetime.strptime(datestr, "%Y%m%d").timetuple().tm_yday

    if is_gridrad_source(datestr):
        corrected = apply_optional_cqm(data, lat_grid, doy, skip_ml=skip_ml)
        source = "GridRad"
    else:
        corrected = apply_mesh75_correction(data)
        source = "MYRORSS/MRMS"

    filtered = apply_probabilistic_filter(corrected, doy, lat_grid, skip_ml=skip_ml)
    filtered, n_repaired = sanitize_hail_values(filtered, max_hail_mm=QA_MAX_HAIL_MM, nodata=NODATA)
    if n_repaired:
        log(f"  WARN: removed {n_repaired:,} non-finite/out-of-bound corrected cells in {in_path.name}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile.update(compress="lzw", tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(filtered.astype(np.float32), 1)

    in_nz  = int(np.count_nonzero(data > 0))
    out_nz = int(np.count_nonzero(filtered > 0))
    return {
        "source":       source,
        "in_pixels":    in_nz,
        "out_pixels":   out_nz,
        "peak_in_mm":   round(float(data.max()), 1) if in_nz else 0.0,
        "peak_out_mm":  round(float(filtered.max()), 1) if out_nz else 0.0,
        "filtered_pct": round(100 * (1 - out_nz / max(in_nz, 1)), 1),
    }

def validate_outputs():
    import rasterio, random
    errors = []
    if not OUT_DIR.exists():
        errors.append(f"Missing: {OUT_DIR}")
    else:
        tifs = sorted(OUT_DIR.rglob("mesh_????????.tif"))
        in_tifs = sorted(IN_DIR.rglob("mesh_????????.tif"))
        if len(tifs) < len(in_tifs) * 0.90:
            errors.append(f"Count mismatch: {len(tifs)} corrected vs {len(in_tifs)} input")
        else:
            log(f"  Found {len(tifs):,} corrected MESH75 GeoTIFFs")
        sample = random.sample(tifs, min(20, len(tifs)))
        for p in sample:
            try:
                with rasterio.open(p) as src:
                    if src.crs.to_epsg() != 4326:
                        errors.append(f"Wrong CRS: {p.name}")
                    if src.width != OUT_NCOLS or src.height != OUT_NROWS:
                        errors.append(f"Wrong shape: {p.name}")
            except Exception as e:
                errors.append(f"Cannot read {p.name}: {e}")
        for p in tifs:
            try:
                with rasterio.open(p) as src:
                    data = src.read(1)
                invalid = (~np.isfinite(data)) | (data < 0) | (data > QA_MAX_HAIL_MM)
                if np.any(invalid):
                    errors.append(
                        f"Invalid corrected MESH75 values in {p.name}: "
                        f"{int(np.count_nonzero(invalid)):,} cells outside "
                        f"[0, {QA_MAX_HAIL_MM:.1f}] mm"
                    )
            except Exception as e:
                errors.append(f"Cannot read {p.name}: {e}")
    if errors:
        log("CRITICAL: Validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Unified MESH correction: MESH75 + GridRad calibration + env filter.")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--skip-calibration", action="store_true",
                        help="Skip Phase A (use existing calibration file)")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--skip-ml", action="store_true",
                        help="Use deterministic calibration/filtering fallbacks even if optional artifacts exist")
    parser.add_argument("--retrain-models", action="store_true",
                        help="Accepted for pipeline compatibility; training is external to this script")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    if args.retrain_models:
        log("  NOTE: --retrain-models accepted; train artifacts externally, then rerun Stage 05")

    log(f"\n{'='*60}")
    log(f"  Unified MESH Bias Correction — Stage 05")
    log(f"{'='*60}")
    log(f"  Input:       {IN_DIR}")
    log(f"  Output:      {OUT_DIR}")
    log(f"  MESH75:      {MH19_A} × (MESH_witt / {WITT_A})^{RATIO_EXP:.3f}")
    log(f"  Env filter:  min {MIN_MESH75_MM} mm, subtropical winter ≥ {MIN_MESH75_SEVERE} mm")

    gridrad_days = load_gridrad_days()
    log(f"  GridRad days: {len(gridrad_days):,}")

    if not args.skip_calibration:
        build_cross_calibration()
    else:
        log("\n[Phase A] Skipped — using existing calibration")

    load_qq_map()
    log(f"  Cross-calibration type: {_qq_type}")

    log("\n[Phase B] Applying corrections to all rasters")
    lat_grid = build_lat_grid()

    if args.year:
        in_files = sorted((IN_DIR / str(args.year)).glob("mesh_????????.tif"))
    else:
        in_files = sorted(IN_DIR.rglob("mesh_????????.tif"))

    log(f"  Input files: {len(in_files):,}")

    done = skipped = 0
    source_counts = {"MYRORSS/MRMS": 0, "GridRad": 0}
    filt_pcts = []
    t0 = time.time()

    for in_path in in_files:
        rel = in_path.relative_to(IN_DIR)
        out_path = OUT_DIR / rel
        result = process_file(in_path, out_path, lat_grid, skip_ml=args.skip_ml)

        if result.get("skipped"):
            skipped += 1
            continue

        done += 1
        src = result.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
        filt_pcts.append(result.get("filtered_pct", 0))

        if done % 200 == 0 or result.get("peak_out_mm", 0) > 50:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(in_files) - done - skipped) / rate if rate > 0 else 0
            log(f"  [{in_path.stem}] done={done:,}  src={src}  "
                f"peak={result.get('peak_out_mm',0):.0f}mm  "
                f"ETA={time.strftime('%H:%M:%S', time.gmtime(eta))}")

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/60:.1f} min")
    log(f"  Days processed: {done:,}  |  Skipped: {skipped:,}")
    log(f"  Sources: {source_counts}")
    log(f"  Mean pixels filtered: {np.mean(filt_pcts):.1f}%" if filt_pcts else "")
    log(f"{'='*60}\n")

    ok = validate_outputs()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
