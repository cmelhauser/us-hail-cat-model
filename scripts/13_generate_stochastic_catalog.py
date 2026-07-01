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

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, DAMAGE_THRESH_MM, MAX_HAIL_MM, RP_YEARS, RNG_SEED, N_SIM_YEARS, TRANSLATE_CELLS, NODATA
    from _io import write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, DAMAGE_THRESH_MM, MAX_HAIL_MM, RP_YEARS, RNG_SEED, N_SIM_YEARS, TRANSLATE_CELLS, NODATA
    from scripts._io import write_geotiff
    from scripts._logging import get_logger

# Keep ann_max in RAM only for small simulations; full 50k-yr runs use memmap.
ANN_MAX_INMEM_BYTES = 512 * 1024 * 1024
STOCH_RECORD_BATCH = 100_000
RP_COMPUTE_CHUNK = 512

EVENT_DIR = DATA_ROOT / "historical" / "events"
MASK_DIR  = DATA_ROOT / "analysis" / "conus_mask"
OUT_DIR   = DATA_ROOT / "stochastic"
CAT_DIR   = OUT_DIR / "catalog"
MAP_DIR   = OUT_DIR / "maps"
PET_DIR   = OUT_DIR / "pet"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "13_stochastic_catalog.log"

# DAMAGE_THRESH_MM, MAX_HAIL_MM, N_SIM_YEARS, TRANSLATE_CELLS, and RNG_SEED imported from _config
SPATIAL_TRANSLATE  = True
RP_YEARS = list(RP_YEARS)  # mutable copy for legacy call sites

log = get_logger("13_generate_stochastic_catalog", LOG_ROOT).info


class StochasticEventWriter:
    """Append simulated event metadata to Parquet without holding all rows in RAM."""

    def __init__(self, path: Path, batch_size: int = STOCH_RECORD_BATCH):
        self.path = path
        self.batch_size = batch_size
        self._buffer: list[dict] = []
        self._writer = None
        self.total = 0

    def append(self, record: dict) -> None:
        self._buffer.append(record)
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.Table.from_pandas(pd.DataFrame(self._buffer), preserve_index=False)
        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(self.path, table.schema)
        self._writer.write_table(table)
        self.total += len(self._buffer)
        self._buffer.clear()

    def close(self) -> None:
        self.flush()
        if self._writer is not None:
            self._writer.close()


def _open_ann_max_store(n_years: int, n_active: int, work_dir: Path):
    """Allocate annual-max storage in RAM or on a memmap file when large."""
    nbytes = n_years * n_active * np.dtype(np.float32).itemsize
    if nbytes <= ANN_MAX_INMEM_BYTES:
        return np.zeros((n_years, n_active), dtype=np.float32), None

    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "_ann_max_simulation.mmap"
    if path.exists():
        path.unlink()
    log(
        f"  ann_max store: memmap {n_years:,} × {n_active:,} "
        f"({nbytes / 1e9:.1f} GB on disk; one year row in RAM)"
    )
    mmap = np.memmap(path, dtype=np.float32, mode="w+", shape=(n_years, n_active))
    return mmap, path


def _should_stream_events(n_years: int, lam: float, catalog_path: Path | None) -> bool:
    if catalog_path is None:
        return False
    return n_years >= 1000 or lam * n_years > 50_000

def load_historical_events():
    """Load event catalog and sparse peak arrays without dense reconstruction."""
    import pandas as pd
    event_df = pd.read_csv(EVENT_DIR / "event_catalog.csv", parse_dates=["start_date", "end_date"])
    npz = np.load(EVENT_DIR / "event_peaks.npz")
    event_ids = npz["event_ids"].astype(int)
    sparse_events = []
    peak_values = []
    for eid in event_ids:
        rows = npz[f"rows_{eid}"].astype(np.int32)
        cols = npz[f"cols_{eid}"].astype(np.int32)
        vals = npz[f"vals_{eid}"].astype(np.float32)
        sparse_events.append({"event_id": int(eid), "rows": rows, "cols": cols, "vals": vals})
        peak_values.append(float(vals.max()) if vals.size else 0.0)
    event_df = event_df.copy()
    # Keep event_df aligned to sparse_events order.
    event_df = event_df.set_index("event_id").loc[event_ids].reset_index()
    event_df["peak"] = np.array(peak_values, dtype=np.float32)
    log(f"  Loaded {len(sparse_events):,} historical sparse events")
    return event_df, sparse_events

def calibrate_sigma(event_df, sparse_events=None):
    """Calibrate σ_perturb from monthly variability of sparse event peaks."""
    log("  Calibrating intensity perturbation σ ...")
    df = event_df.copy()
    df["month"] = df["start_date"].dt.month
    if "peak" not in df:
        df["peak"] = [float(e["vals"].max()) if len(e["vals"]) else 0.0 for e in sparse_events]
    monthly_cv = []
    for month in range(3, 10):
        month_peaks = df.loc[df["month"] == month, "peak"].values
        month_peaks = month_peaks[month_peaks > 0]
        if len(month_peaks) >= 10 and month_peaks.mean() > 0:
            monthly_cv.append(float(month_peaks.std() / month_peaks.mean()))
    sigma = float(np.median(monthly_cv)) if monthly_cv else 0.15
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

def build_active_index(sparse_events):
    """Map all historically active cells to compact active-column indices."""
    keys = set()
    for ev in sparse_events:
        keys.update(zip(ev["rows"].tolist(), ev["cols"].tolist()))
    keys = sorted(keys)
    active_rows = np.array([k[0] for k in keys], dtype=np.int32)
    active_cols = np.array([k[1] for k in keys], dtype=np.int32)
    lookup = {k: i for i, k in enumerate(keys)}
    return active_rows, active_cols, lookup

def sparse_event_active_mask(sparse_events):
    """Return unique active rows/cols across sparse historical events."""
    active_rows, active_cols, _ = build_active_index(sparse_events)
    return active_rows, active_cols

def translate_sparse(rows, cols, rng, sigma_cells=TRANSLATE_CELLS):
    """Gaussian sparse translation clipped to model domain."""
    dr = int(np.rint(rng.normal(0, sigma_cells))) if sigma_cells > 0 else 0
    dc = int(np.rint(rng.normal(0, sigma_cells))) if sigma_cells > 0 else 0
    rows_new = rows + dr
    cols_new = cols + dc
    keep = (rows_new >= 0) & (rows_new < NROWS) & (cols_new >= 0) & (cols_new < NCOLS)
    return rows_new[keep], cols_new[keep], keep, dr, dc

def sparse_shape_perturb(rows, cols, vals, rng):
    """Light sparse footprint perturbation without dense grids."""
    if len(rows) == 0 or rng.random() >= 0.25:
        return rows, cols, vals, "none"
    # Add one random 4-neighbor shell at half intensity. Duplicates are reduced later.
    direction = [(1,0), (-1,0), (0,1), (0,-1)][int(rng.integers(0, 4))]
    rr = rows + direction[0]
    cc = cols + direction[1]
    keep = (rr >= 0) & (rr < NROWS) & (cc >= 0) & (cc < NCOLS)
    if not np.any(keep):
        return rows, cols, vals, "none"
    rows2 = np.concatenate([rows, rr[keep]])
    cols2 = np.concatenate([cols, cc[keep]])
    vals2 = np.concatenate([vals, vals[keep] * 0.5]).astype(np.float32)
    return rows2, cols2, vals2, "neighbor_shell"

def update_sparse_max(target_row, rows, cols, vals, active_lookup):
    """Update one simulated annual-max row using sparse event cells."""
    if len(vals) == 0:
        return 0, 0.0
    # Collapse duplicates by max in compact index space.
    idx_vals = []
    for r, c, v in zip(rows.tolist(), cols.tolist(), vals.tolist()):
        j = active_lookup.get((int(r), int(c)))
        if j is not None:
            idx_vals.append((j, float(v)))
    if not idx_vals:
        return 0, 0.0
    # Efficient enough for sparse event footprints.
    by_idx = {}
    for j, v in idx_vals:
        if v > by_idx.get(j, 0.0):
            by_idx[j] = v
    idx = np.fromiter(by_idx.keys(), dtype=np.int32)
    vv = np.fromiter(by_idx.values(), dtype=np.float32)
    np.maximum.at(target_row, idx, vv)
    return int(np.count_nonzero(vv >= DAMAGE_THRESH_MM)), float(vv.max())

def update_sparse_annual_max(target_row, active_lookup, rows, cols, vals):
    """Compatibility wrapper for updating a compact annual-max row."""
    tuple_lookup = {
        ((int(k) // NCOLS, int(k) % NCOLS) if not isinstance(k, tuple) else k): v
        for k, v in active_lookup.items()
    }
    update_sparse_max(target_row, rows, cols, vals, tuple_lookup)

def simulate_catalog(event_df, sparse_events, sigma, doy_cdf, n_years, catalog_path=None, work_dir=None):
    """Run sparse-safe stochastic simulation."""
    rng = np.random.default_rng(RNG_SEED)
    n_hist = len(event_df)
    event_doys = event_df["doy"].values
    event_ids = event_df["event_id"].values
    event_peaks = event_df["peak"].values.astype(float)
    peak_order = np.argsort(np.argsort(event_peaks))
    peak_percentiles = peak_order / max(len(peak_order) - 1, 1)

    hist_years = max(1, event_df["start_date"].dt.year.nunique())
    lam = n_hist / hist_years
    log(f"  λ = {lam:.1f} events/year ({n_hist} events / {hist_years} years)")

    active_rows, active_cols, active_lookup = build_active_index(sparse_events)
    n_active = len(active_rows)
    log(f"  Active cells: {n_active:,}")
    work_dir = Path(work_dir or OUT_DIR)
    catalog_path = Path(catalog_path) if catalog_path is not None else None
    ann_max, ann_max_mmap_path = _open_ann_max_store(n_years, n_active, work_dir / "_work")
    year_row = np.zeros(n_active, dtype=np.float32)

    ann_occ_peak = np.zeros(n_years, dtype=np.float32)
    ann_occ_cells = np.zeros(n_years, dtype=np.int32)
    ann_agg_cells = np.zeros(n_years, dtype=np.int32)
    ann_n_events = np.zeros(n_years, dtype=np.int32)
    stream_events = _should_stream_events(n_years, lam, catalog_path)
    event_writer = StochasticEventWriter(catalog_path) if stream_events else None
    stoch_records: list[dict] = []
    t0 = time.time()

    for yr in range(n_years):
        year_row.fill(0.0)
        n_ev = int(rng.poisson(lam))
        if n_ev == 0:
            ann_max[yr, :] = year_row
            continue
        ann_n_events[yr] = n_ev
        ev_doys = np.searchsorted(doy_cdf, rng.random(n_ev)) + 1
        year_max_peak = 0.0
        year_max_cells = 0

        for ei, doy in enumerate(ev_doys.astype(int)):
            doy_diff = np.abs(event_doys - doy)
            doy_diff = np.minimum(doy_diff, 366 - doy_diff)
            weights = np.exp(-doy_diff / 30.0)
            weights /= weights.sum()
            template_idx = int(rng.choice(n_hist, p=weights))
            ev = sparse_events[template_idx]

            rows = ev["rows"]
            cols = ev["cols"]
            vals = ev["vals"].astype(np.float32)

            pct = float(peak_percentiles[template_idx])
            sigma_event = float(np.clip(0.10 + 0.15 * pct, 0.10, max(0.25, sigma)))
            scale = float(np.exp(sigma_event * rng.standard_normal()))
            vals_new = np.clip(vals * scale, 0, MAX_HAIL_MM).astype(np.float32)

            if SPATIAL_TRANSLATE:
                rows_new, cols_new, keep, dr, dc = translate_sparse(rows, cols, rng, TRANSLATE_CELLS)
                vals_new = vals_new[keep]
            else:
                rows_new, cols_new, dr, dc = rows, cols, 0, 0

            rows_new, cols_new, vals_new, perturbation_type = sparse_shape_perturb(rows_new, cols_new, vals_new, rng)
            n_cells, peak_val = update_sparse_max(year_row, rows_new, cols_new, vals_new, active_lookup)
            ann_agg_cells[yr] += n_cells
            if peak_val > year_max_peak:
                year_max_peak = peak_val
                year_max_cells = n_cells

            record = {
                "sim_year": yr, "event_idx": ei, "template_id": int(event_ids[template_idx]),
                "doy": int(doy), "scale_factor": round(scale, 4),
                "peak_hail_mm": round(peak_val, 1), "n_cells": n_cells,
                "drow": int(dr), "dcol": int(dc),
                "perturbation_type": perturbation_type,
                "template_peak_percentile": round(pct, 4),
            }
            if event_writer is not None:
                event_writer.append(record)
            else:
                stoch_records.append(record)

        ann_max[yr, :] = year_row
        ann_occ_peak[yr] = year_max_peak
        ann_occ_cells[yr] = year_max_cells
        if yr > 0 and yr % 5000 == 0:
            elapsed = time.time() - t0
            rate = yr / elapsed
            eta = (n_years - yr) / rate
            log(f"    Year {yr:,}/{n_years:,}  ({elapsed/60:.0f} min, ETA {eta/60:.0f} min)")

    elapsed = time.time() - t0
    log(f"  Simulation complete: {elapsed/60:.1f} min")
    if event_writer is not None:
        event_writer.close()
        log(f"  Total stochastic events: {event_writer.total:,}")
        stoch_df = pd.DataFrame()
    else:
        log(f"  Total stochastic events: {len(stoch_records):,}")
        stoch_df = pd.DataFrame(stoch_records)
    return (ann_max, active_rows, active_cols, ann_occ_peak, ann_occ_cells,
            ann_agg_cells, ann_n_events, stoch_df, ann_max_mmap_path)

def compute_empirical_rps(ann_max, active_rows, active_cols, n_years, chunk_size=RP_COMPUTE_CHUNK):
    """Compute empirical return periods from annual max at each active cell."""
    log(f"  Computing empirical return periods ...")

    rp_maps = {}
    for rp in RP_YEARS:
        rp_maps[rp] = np.zeros((NROWS, NCOLS), dtype=np.float32)

    n_active = len(active_rows)
    ranks = {rp: max(1, int(n_years / rp)) for rp in RP_YEARS}
    for ci_start in range(0, n_active, chunk_size):
        ci_end = min(ci_start + chunk_size, n_active)
        block = np.asarray(ann_max[:, ci_start:ci_end])
        for j, ci in enumerate(range(ci_start, ci_end)):
            sorted_desc = np.sort(block[:, j])[::-1]
            for rp in RP_YEARS:
                rank = ranks[rp]
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

def load_conus_mask():
    """Load the Stage 12 CONUS mask when available."""
    import rasterio
    mask_path = MASK_DIR / "conus_mask.tif"
    if not mask_path.exists():
        log(f"  WARN: CONUS mask not found at {mask_path}; stochastic maps unmasked")
        return None
    with rasterio.open(mask_path) as src:
        mask = src.read(1) > 0
    if mask.shape != (NROWS, NCOLS):
        log(f"  WARN: CONUS mask shape {mask.shape} does not match {(NROWS, NCOLS)}; stochastic maps unmasked")
        return None
    return mask

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
    log(f"  Spatial translate: {SPATIAL_TRANSLATE} (±{TRANSLATE_CELLS} cells)")

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
    catalog_path = CAT_DIR / "stochastic_event_summary.parquet"
    if catalog_path.exists():
        catalog_path.unlink()
    ann_max_mmap_path = None
    ann_n_events = ann_occ_peak = None
    try:
        (ann_max, active_rows, active_cols,
         ann_occ_peak, ann_occ_cells, ann_agg_cells, ann_n_events,
         stoch_df, ann_max_mmap_path) = simulate_catalog(
            event_df, sparse_events, sigma, doy_cdf, n_years,
            catalog_path=catalog_path, work_dir=OUT_DIR,
        )

        # Outputs
        log("\n[5/5] Computing return periods and saving outputs")

        # Empirical RP maps
        rp_maps = compute_empirical_rps(ann_max, active_rows, active_cols, n_years)
        conus_mask = load_conus_mask()
        MAP_DIR.mkdir(parents=True, exist_ok=True)
        for rp, data in rp_maps.items():
            if conus_mask is not None:
                data = np.where(conus_mask, data, 0.0).astype(np.float32)
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
        if not stoch_df.empty:
            stoch_df.to_parquet(catalog_path, index=False)
            log(f"  Stochastic events: {len(stoch_df):,} saved to Parquet")
        elif catalog_path.exists():
            log(f"  Stochastic events saved to Parquet (streamed)")
        else:
            log("  WARN: no stochastic event summary written")

        # Summary
        log(f"\n  ── Stochastic Summary ──")
        log(f"  Years: {n_years:,}")
        log(f"  σ_perturb: {sigma:.3f}")
        log(f"  Mean events/yr: {ann_n_events.mean():.1f}")
        rank100 = max(1, min(len(ann_occ_peak), n_years // 100 if n_years >= 100 else 1))
        log(f"  100-yr OEP peak: {float(np.sort(ann_occ_peak)[::-1][rank100-1]):.1f} mm")
        log(f"  Historical vs stochastic annual max correlation check recommended")
    finally:
        if ann_max_mmap_path is not None:
            try:
                del ann_max
            except NameError:
                pass
            if ann_max_mmap_path.exists():
                ann_max_mmap_path.unlink()
                log(f"  Removed temporary ann_max memmap")

    log(f"\n{'='*60}")
    log(f"  Complete")
    log(f"{'='*60}\n")

    ok = validate_outputs()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
