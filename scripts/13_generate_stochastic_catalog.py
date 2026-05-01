#!/usr/bin/env python3
"""
13_generate_stochastic_catalog.py — 50,000-Year Stochastic Catalog
====================================================================
Generates a stochastic hail catalog using event-resampling from the
historical event catalog (stage 08).

Methodology
-----------
  1. Load historical event catalog and sparse peak arrays
  2. Fit Poisson rate λ = n_events / n_years
  3. Build seasonal DOY distribution (Gaussian KDE, σ=10 days, wrapped)
  4. CALIBRATE σ_perturb from empirical inter-annual intensity variance
  5. Per simulated year (50,000 years):
     a. Draw N_events ~ Poisson(λ)
     b. For each event:
        - Draw DOY from seasonal distribution
        - Select template via seasonal weighting: exp(-|doy_diff| / 30)
        - Apply log-normal intensity perturbation: hail × exp(σ × ε)
        - Apply spatial translation: shift footprint ±2–4 cells
  6. Compute annual maxima at each cell → empirical return periods
  7. Build Probable Exceedance Tables (occurrence + aggregate)

Key Improvements over v1.0
---------------------------
  - σ_perturb CALIBRATED from data (v1.0 used fixed 0.15)
  - Spatial translation ENABLED (v1.0 had it disabled)
  - Sparse event storage handles 0.05° grid efficiently
  - Return periods computed up to 50,000 years

Input
-----
  data/historical/events/event_catalog.csv
  data/historical/events/event_peaks.npz
  data/analysis/conus_mask/conus_mask.tif

Output
------
  data/stochastic/catalog/stochastic_event_summary.parquet
  data/stochastic/maps/rp_*yr_stochastic.tif (empirical RP GeoTIFFs)
  data/stochastic/pet/pet_occurrence.csv
  data/stochastic/pet/pet_aggregate.csv
  data/stochastic/ann_max_hail.npy (50,000 × nrows × ncols, active-cell sparse)

Usage
-----
  python scripts/13_generate_stochastic_catalog.py
  python scripts/13_generate_stochastic_catalog.py --n-years 10000   # shorter test
  python scripts/13_generate_stochastic_catalog.py --validate
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
EVENT_DIR = DATA_ROOT / "historical" / "events"
MASK_DIR  = DATA_ROOT / "analysis" / "conus_mask"
OUT_DIR   = DATA_ROOT / "stochastic"
CAT_DIR   = OUT_DIR / "catalog"
MAP_DIR   = OUT_DIR / "maps"
PET_DIR   = OUT_DIR / "pet"
LOG_DIR   = REPO_ROOT / "logs"
LOG_FILE  = LOG_DIR / "13_stochastic_catalog.log"

NROWS = 520
NCOLS = 1180
DX    = 0.05
LAT_MAX = 50.005
LON_MIN = -125.005

N_SIM_YEARS       = 50_000
DAMAGE_THRESH_MM  = 25.4    # 1.0 inch
MAX_HAIL_MM       = 250.0   # physical ceiling (~10 inches)
SPATIAL_TRANSLATE  = True
TRANSLATE_SIGMA_CELLS = 2.0     # Gaussian translation σ (~11 km)
MAX_TRANSLATE_CELLS = 8       # clip Gaussian displacement to avoid unrealistic jumps
RNG_SEED           = 42
RP_YEARS = [10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_historical_events():
    """Load event catalog and sparse peak arrays without dense reconstruction."""
    event_df = pd.read_csv(EVENT_DIR / "event_catalog.csv", parse_dates=["start_date", "end_date"])
    npz = np.load(EVENT_DIR / "event_peaks.npz")

    event_ids = npz["event_ids"]
    sparse_events = []
    for eid in event_ids:
        rows = npz[f"rows_{eid}"].astype(np.int32)
        cols = npz[f"cols_{eid}"].astype(np.int32)
        vals = npz[f"vals_{eid}"].astype(np.float32)
        sparse_events.append({"event_id": int(eid), "rows": rows, "cols": cols, "vals": vals})

    log(f"  Loaded {len(sparse_events):,} historical sparse events")
    return event_df, sparse_events


def sparse_event_peak(sparse_event: dict) -> float:
    return float(sparse_event["vals"].max()) if len(sparse_event["vals"]) else 0.0


def sparse_event_active_mask(sparse_events: list) -> tuple:
    """Return unique active rows/cols across all sparse templates."""
    flat_parts = []
    for ev in sparse_events:
        if len(ev["rows"]):
            flat_parts.append(ev["rows"].astype(np.int64) * NCOLS + ev["cols"].astype(np.int64))
    if not flat_parts:
        return np.array([], dtype=np.int32), np.array([], dtype=np.int32)
    flat = np.unique(np.concatenate(flat_parts))
    return (flat // NCOLS).astype(np.int32), (flat % NCOLS).astype(np.int32)


def translate_sparse_event(rows: np.ndarray, cols: np.ndarray, rng) -> tuple:
    if not SPATIAL_TRANSLATE:
        return rows, cols, 0, 0
    dr = int(np.rint(rng.normal(0.0, TRANSLATE_SIGMA_CELLS)))
    dc = int(np.rint(rng.normal(0.0, TRANSLATE_SIGMA_CELLS)))
    dr = int(np.clip(dr, -MAX_TRANSLATE_CELLS, MAX_TRANSLATE_CELLS))
    dc = int(np.clip(dc, -MAX_TRANSLATE_CELLS, MAX_TRANSLATE_CELLS))
    r2 = rows + dr
    c2 = cols + dc
    keep = (r2 >= 0) & (r2 < NROWS) & (c2 >= 0) & (c2 < NCOLS)
    return r2[keep], c2[keep], dr, dc


def update_sparse_annual_max(ann_row: np.ndarray, active_lookup: dict,
                             rows: np.ndarray, cols: np.ndarray, vals: np.ndarray):
    """Update annual maxima vector using sparse event coordinates."""
    flat = rows.astype(np.int64) * NCOLS + cols.astype(np.int64)
    idx = np.fromiter((active_lookup.get(int(f), -1) for f in flat), dtype=np.int64, count=len(flat))
    keep = idx >= 0
    if np.any(keep):
        np.maximum.at(ann_row, idx[keep], vals[keep])


def calibrate_sigma(event_df, sparse_events):
    """
    Calibrate σ_perturb from empirical inter-annual peak intensity variance.

    For events in the same DOY window across different years, compute
    the coefficient of variation of peak hail intensity. This gives
    the natural year-to-year variability that the perturbation should match.
    """
    log("  Calibrating intensity perturbation σ ...")

    # Group events by month, compute CV of peak hail within each month
    event_df = event_df.copy()
    event_df["month"] = event_df["start_date"].dt.month
    event_df["peak"] = [sparse_event_peak(ev) for ev in sparse_events]

    monthly_cv = []
    for month in range(3, 10):  # Mar–Sep (hail season)
        month_peaks = event_df.loc[event_df["month"] == month, "peak"].values
        if len(month_peaks) >= 10:
            cv = float(month_peaks.std() / month_peaks.mean())
            monthly_cv.append(cv)

    if monthly_cv:
        sigma = float(np.median(monthly_cv))
    else:
        sigma = 0.15  # fallback

    # Bound to reasonable range
    sigma = float(np.clip(sigma, 0.10, 0.40))
    log(f"  Calibrated σ = {sigma:.3f} (monthly CVs: {[f'{c:.3f}' for c in monthly_cv]})")
    return sigma


def build_doy_distribution(event_df):
    """Build smooth seasonal DOY distribution for event occurrence."""
    from scipy.ndimage import gaussian_filter1d

    doys = event_df["doy"].values
    hist = np.zeros(366)
    for d in doys:
        hist[d - 1] += 1

    # Smooth with wrapped Gaussian (σ=10 days)
    padded = np.concatenate([hist[-30:], hist, hist[:30]])
    smoothed = gaussian_filter1d(padded.astype(float), sigma=10)
    smoothed = smoothed[30:-30]

    # Normalize to CDF
    pdf = smoothed / smoothed.sum()
    cdf = np.cumsum(pdf)
    return cdf


def simulate_catalog(event_df, sparse_events, sigma, doy_cdf, n_years):
    """Run the stochastic simulation using sparse templates end-to-end."""
    rng = np.random.default_rng(RNG_SEED)
    n_hist = len(event_df)
    event_doys = event_df["doy"].values
    event_ids = event_df["event_id"].values

    hist_years = event_df["start_date"].dt.year.nunique()
    lam = n_hist / hist_years
    log(f"  λ = {lam:.1f} events/year ({n_hist} events / {hist_years} years)")

    active_rows, active_cols = sparse_event_active_mask(sparse_events)
    active_flat = active_rows.astype(np.int64) * NCOLS + active_cols.astype(np.int64)
    active_lookup = {int(f): i for i, f in enumerate(active_flat)}
    n_active = len(active_rows)
    log(f"  Active cells: {n_active:,}")

    ann_max = np.zeros((n_years, n_active), dtype=np.float32)
    ann_occ_peak = np.zeros(n_years, dtype=np.float32)
    ann_occ_cells = np.zeros(n_years, dtype=np.int32)
    ann_agg_cells = np.zeros(n_years, dtype=np.int32)
    ann_n_events = np.zeros(n_years, dtype=np.int32)

    stoch_records = []
    t0 = time.time()

    for yr in range(n_years):
        n_ev = int(rng.poisson(lam))
        if n_ev == 0:
            continue
        ann_n_events[yr] = n_ev

        ev_doys = np.searchsorted(doy_cdf, rng.random(n_ev)) + 1
        year_max_peak = 0.0
        year_max_cells = 0

        for ei in range(n_ev):
            doy = int(ev_doys[ei])
            doy_diff = np.abs(event_doys - doy)
            doy_diff = np.minimum(doy_diff, 366 - doy_diff)
            weights = np.exp(-doy_diff / 30.0)
            weights /= weights.sum()

            template_idx = int(rng.choice(n_hist, p=weights))
            ev = sparse_events[template_idx]
            scale = float(np.exp(sigma * rng.standard_normal()))
            vals = np.clip(ev["vals"] * scale, 0, MAX_HAIL_MM).astype(np.float32)
            rows, cols, dr, dc = translate_sparse_event(ev["rows"], ev["cols"], rng)
            if len(rows) != len(vals):
                # translation clipped some cells at domain edge
                r_full = ev["rows"] + dr
                c_full = ev["cols"] + dc
                keep = (r_full >= 0) & (r_full < NROWS) & (c_full >= 0) & (c_full < NCOLS)
                vals = vals[keep]

            update_sparse_annual_max(ann_max[yr], active_lookup, rows, cols, vals)

            fp = vals >= DAMAGE_THRESH_MM
            n_cells = int(fp.sum())
            peak_val = float(vals.max()) if len(vals) else 0.0
            ann_agg_cells[yr] += n_cells
            if peak_val > year_max_peak:
                year_max_peak = peak_val
                year_max_cells = n_cells

            stoch_records.append({
                "sim_year": yr,
                "event_idx": ei,
                "template_id": int(event_ids[template_idx]),
                "doy": doy,
                "scale_factor": round(scale, 4),
                "peak_hail_mm": round(peak_val, 1),
                "n_cells": n_cells,
                "dr": dr,
                "dc": dc,
            })

        ann_occ_peak[yr] = year_max_peak
        ann_occ_cells[yr] = year_max_cells

        if yr > 0 and yr % 5000 == 0:
            elapsed = time.time() - t0
            rate = yr / elapsed
            eta = (n_years - yr) / rate
            log(f"    Year {yr:,}/{n_years:,}  ({elapsed/60:.0f} min, ETA {eta/60:.0f} min)")

    elapsed = time.time() - t0
    log(f"  Simulation complete: {elapsed/60:.1f} min")
    log(f"  Total stochastic events: {len(stoch_records):,}")

    return (ann_max, active_rows, active_cols,
            ann_occ_peak, ann_occ_cells, ann_agg_cells, ann_n_events,
            pd.DataFrame(stoch_records))


def compute_empirical_rps(ann_max, active_rows, active_cols, n_years):
    """Compute empirical return periods from annual max at each active cell."""
    log(f"  Computing empirical return periods ...")

    rp_maps = {}
    for rp in RP_YEARS:
        rp_maps[rp] = np.zeros((NROWS, NCOLS), dtype=np.float32)

    n_active = len(active_rows)
    for ci in range(n_active):
        series = ann_max[:, ci]
        sorted_desc = np.sort(series)[::-1]

        for rp in RP_YEARS:
            rank = max(1, int(n_years / rp))
            if rank <= len(sorted_desc):
                rp_maps[rp][active_rows[ci], active_cols[ci]] = sorted_desc[rank - 1]

    return rp_maps


def build_pet(ann_occ_peak, ann_occ_cells, ann_agg_cells, ann_n_events, n_years):
    """Build Probable Exceedance Tables."""
    rps = [5, 10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000]

    # Occurrence PET: max single-event hail per year
    occ_sorted = np.sort(ann_occ_peak)[::-1]
    occ_cells_sorted = np.sort(ann_occ_cells.astype(float))[::-1]

    occ_rows = []
    for rp in rps:
        rank = max(1, int(n_years / rp))
        if rank <= len(occ_sorted):
            occ_rows.append({
                "return_period_yr": rp,
                "peak_hail_mm": round(float(occ_sorted[rank - 1]), 1),
                "peak_hail_in": round(float(occ_sorted[rank - 1]) / 25.4, 2),
                "occ_n_cells": int(occ_cells_sorted[rank - 1]),
            })

    # Aggregate PET: total footprint across all events per year
    agg_sorted = np.sort(ann_agg_cells.astype(float))[::-1]
    agg_ev_sorted = np.sort(ann_n_events.astype(float))[::-1]

    agg_rows = []
    for rp in rps:
        rank = max(1, int(n_years / rp))
        if rank <= len(agg_sorted):
            agg_rows.append({
                "return_period_yr": rp,
                "agg_n_cells": int(agg_sorted[rank - 1]),
                "agg_n_events": int(agg_ev_sorted[rank - 1]),
            })

    return pd.DataFrame(occ_rows), pd.DataFrame(agg_rows)


def write_geotiff(data, out_path):
    import rasterio
    from rasterio.transform import from_origin
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": NCOLS,
        "height": NROWS, "count": 1, "crs": "EPSG:4326",
        "transform": from_origin(LON_MIN, LAT_MAX, DX, DX),
        "compress": "lzw", "tiled": True, "blockxsize": 256,
        "blockysize": 256, "nodata": 0.0,
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data.astype(np.float32), 1)


def validate_outputs() -> bool:
    errors = []
    for rp in RP_YEARS:
        p = MAP_DIR / f"rp_{rp:05d}yr_stochastic.tif"
        if not p.exists():
            errors.append(f"Missing: {p.name}")
    for f in ["pet_occurrence.csv", "pet_aggregate.csv"]:
        if not (PET_DIR / f).exists():
            errors.append(f"Missing: {f}")
    if errors:
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate 50,000-yr stochastic catalog.")
    parser.add_argument("--n-years", type=int, default=N_SIM_YEARS)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    n_years = args.n_years

    log(f"\n{'='*60}")
    log(f"  Stochastic Catalog — Stage 13")
    log(f"{'='*60}")
    log(f"  Simulation years: {n_years:,}")
    log(f"  Spatial translate: {SPATIAL_TRANSLATE} (Gaussian σ={TRANSLATE_SIGMA_CELLS} cells, clip ±{MAX_TRANSLATE_CELLS})")

    # Load historical events
    log("\n[1/5] Loading historical events")
    event_df, sparse_events = load_historical_events()

    # Calibrate σ
    log("\n[2/5] Calibrating intensity perturbation")
    sigma = calibrate_sigma(event_df, sparse_events)

    # DOY distribution
    log("\n[3/5] Building seasonal distribution")
    doy_cdf = build_doy_distribution(event_df)

    # Simulate
    log(f"\n[4/5] Simulating {n_years:,} years (σ={sigma:.3f})")
    (ann_max, active_rows, active_cols,
     ann_occ_peak, ann_occ_cells, ann_agg_cells, ann_n_events,
     stoch_df) = simulate_catalog(event_df, sparse_events, sigma, doy_cdf, n_years)

    # Outputs
    log("\n[5/5] Computing return periods and saving outputs")

    # Empirical RP maps
    rp_maps = compute_empirical_rps(ann_max, active_rows, active_cols, n_years)
    MAP_DIR.mkdir(parents=True, exist_ok=True)
    for rp, data in rp_maps.items():
        path = MAP_DIR / f"rp_{rp:05d}yr_stochastic.tif"
        write_geotiff(data, path)
        peak = float(data.max())
        log(f"  {path.name}: peak = {peak:.1f} mm ({peak/25.4:.2f} in)")

    # PET
    PET_DIR.mkdir(parents=True, exist_ok=True)
    occ_pet, agg_pet = build_pet(ann_occ_peak, ann_occ_cells,
                                  ann_agg_cells, ann_n_events, n_years)
    occ_pet.to_csv(PET_DIR / "pet_occurrence.csv", index=False)
    agg_pet.to_csv(PET_DIR / "pet_aggregate.csv", index=False)
    log(f"  PET tables written")

    # Event summary
    CAT_DIR.mkdir(parents=True, exist_ok=True)
    stoch_df.to_parquet(CAT_DIR / "stochastic_event_summary.parquet", index=False)
    log(f"  Stochastic events: {len(stoch_df):,} saved to Parquet")

    # Summary
    log(f"\n  ── Stochastic Summary ──")
    log(f"  Years: {n_years:,}")
    log(f"  σ_perturb: {sigma:.3f}")
    log(f"  Mean events/yr: {ann_n_events.mean():.1f}")
    log(f"  100-yr OEP peak: {float(np.sort(ann_occ_peak)[::-1][n_years//100-1]):.1f} mm")
    log(f"  Historical vs stochastic annual max correlation check recommended")

    log(f"\n{'='*60}")
    log(f"  Complete")
    log(f"{'='*60}\n")

    ok = validate_outputs()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
