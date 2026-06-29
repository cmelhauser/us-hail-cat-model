#!/usr/bin/env python3
"""
08_build_event_catalog.py — Synoptic Event Identification & Catalog
====================================================================
Identifies discrete hail events from the corrected MESH75 daily rasters
using a synoptic-system grouping rule, then builds an event catalog and
per-event peak hail arrays.

Event Grouping Rule (Doswell et al. 2005; SPC conventions)
-----------------------------------------------------------
Two consecutive hail days belong to the same event if ALL conditions hold:
  1. Temporal gap ≤ 1 day (consecutive days, or one quiet day between them)
  2. Spatial overlap: day-1 footprint dilated by ~83 km overlaps day-2
     At 0.05° resolution, 83 km ≈ 15 cells
  3. Hard cap: events longer than 5 calendar days are forcibly split

Damage threshold: 25.4 mm (1.0 inch) — residential asphalt shingle onset.

Sparse Storage
--------------
At 0.05° the full event_peak_array would be (n_events, 520, 1180) ~7 GB.
Instead we store per-event data as sparse arrays using active-cell-only
indexing: for each event, store (row_indices, col_indices, values).

Input
-----
  data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif

Output
------
  data/historical/events/event_catalog.csv
  data/historical/events/event_peaks.npz  (sparse: rows, cols, vals per event)

Usage
-----
  python scripts/08_build_event_catalog.py
  python scripts/08_build_event_catalog.py --validate
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, DAMAGE_THRESH_MM, MAX_CENTROID_KM_DAY, MAX_INTENSITY_RATIO
    from _io import haversine_km
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, DAMAGE_THRESH_MM, MAX_CENTROID_KM_DAY, MAX_INTENSITY_RATIO
    from scripts._io import haversine_km
    from scripts._logging import get_logger

IN_DIR    = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
OUT_DIR   = DATA_ROOT / "historical" / "events"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "08_build_event_catalog.log"

# Event identification parameters
DAMAGE_THRESHOLD_MM = DAMAGE_THRESH_MM
BUFFER_CELLS        = 15     # ~83 km at 0.05° (~5.5 km/cell)
MAX_DURATION_DAYS   = 5      # hard cap per AIR/RMS conventions
MAX_TEMPORAL_GAP    = 2      # max gap in days (1=consecutive, 2=one quiet day)
# MAX_CENTROID_KM_DAY imported from _config
# MAX_INTENSITY_RATIO imported from _config

log = get_logger("08_build_event_catalog", LOG_ROOT).info

def load_daily_data() -> tuple[list, list]:
    """
    Load all corrected MESH75 rasters.

    Returns (dates, daily_cells) where daily_cells[i] holds sparse
    (rows, cols, vals) for cells ≥ DAMAGE_THRESHOLD_MM only. Keeping active
    cells sparse avoids holding ~30 GB of full-grid arrays for ~9,800 days.
    """
    import rasterio

    tif_files = sorted(IN_DIR.rglob("mesh_????????.tif"))
    log(f"  Found {len(tif_files):,} corrected MESH75 rasters")

    dates: list = []
    daily_cells: list = []
    total_active_cells = 0

    for i, fpath in enumerate(tif_files):
        datestr = fpath.stem.replace("mesh_", "")
        try:
            dt = date(int(datestr[:4]), int(datestr[4:6]), int(datestr[6:8]))
        except ValueError:
            continue

        with rasterio.open(fpath) as src:
            data = src.read(1)

        rows, cols = np.where(data >= DAMAGE_THRESHOLD_MM)
        if rows.size:
            dates.append(dt)
            daily_cells.append({
                "rows": rows.astype(np.int16),
                "cols": cols.astype(np.int16),
                "vals": data[rows, cols].astype(np.float32),
            })
            total_active_cells += rows.size

        if (i + 1) % 1000 == 0:
            log(f"    Loaded {i+1:,}/{len(tif_files):,}  "
                f"({len(dates):,} active hail days so far)")

    log(f"  Active hail days (≥{DAMAGE_THRESHOLD_MM:.0f} mm): {len(dates):,}")
    if dates:
        mean_cells = total_active_cells / len(dates)
        est_mb = total_active_cells * 8 / 1e6
        log(f"  Sparse footprint: {total_active_cells:,} cells "
            f"(mean {mean_cells:,.0f}/day, ~{est_mb:.0f} MB in RAM)")
    return dates, daily_cells

def footprints_overlap_sparse(
    rows1: np.ndarray,
    cols1: np.ndarray,
    rows2: np.ndarray,
    cols2: np.ndarray,
    buffer: int = BUFFER_CELLS,
) -> bool:
    """Check if two sparse footprints overlap after buffering fp1 by buffer cells."""
    if rows1.size == 0 or rows2.size == 0:
        return False

    r1min, r1max = int(rows1.min()), int(rows1.max())
    c1min, c1max = int(cols1.min()), int(cols1.max())
    if (rows2.max() < r1min - buffer or rows2.min() > r1max + buffer or
        cols2.max() < c1min - buffer or cols2.min() > c1max + buffer):
        return False

    mask = (
        (rows2 >= r1min - buffer) & (rows2 <= r1max + buffer) &
        (cols2 >= c1min - buffer) & (cols2 <= c1max + buffer)
    )
    r2f, c2f = rows2[mask], cols2[mask]
    if r2f.size == 0:
        return False

    # Chunk fp2 queries so very large footprints do not allocate n1×n2 arrays.
    chunk = 2048
    for start in range(0, r2f.size, chunk):
        rr = r2f[start:start + chunk]
        cc = c2f[start:start + chunk]
        dr = np.abs(rr[:, None] - rows1[None, :])
        dc = np.abs(cc[:, None] - cols1[None, :])
        if np.any((dr <= buffer) & (dc <= buffer)):
            return True
    return False

def footprints_overlap(fp1: np.ndarray, fp2: np.ndarray) -> bool:
    """Dense-grid overlap check (tests and small synthetic grids)."""
    r1, c1 = np.where(fp1)
    r2, c2 = np.where(fp2)
    return footprints_overlap_sparse(r1, c1, r2, c2)

def footprint_centroid_sparse(
    rows: np.ndarray,
    cols: np.ndarray,
    vals: np.ndarray | None = None,
) -> tuple[float, float]:
    """Return an intensity-weighted centroid for sparse active cells."""
    if rows.size == 0:
        return np.nan, np.nan
    lats = LAT_MAX - (rows + 0.5) * DX
    lons = LON_MIN + (cols + 0.5) * DX
    if vals is not None and vals.size:
        w = vals.astype(float)
        if np.isfinite(w).all() and w.sum() > 0:
            return float(np.average(lats, weights=w)), float(np.average(lons, weights=w))
    return float(lats.mean()), float(lons.mean())

def physically_coherent_merge(
    dates,
    daily_cells: list,
    prev_idx: int,
    curr_idx: int,
) -> tuple[bool, float, float]:
    """v2.1 merge sanity checks: centroid speed and peak-intensity jump."""
    gap_days = max(1, (dates[curr_idx] - dates[prev_idx]).days)
    prev = daily_cells[prev_idx]
    curr = daily_cells[curr_idx]
    c1 = footprint_centroid_sparse(prev["rows"], prev["cols"], prev["vals"])
    c2 = footprint_centroid_sparse(curr["rows"], curr["cols"], curr["vals"])
    speed = np.inf if not np.all(np.isfinite(c1 + c2)) else haversine_km(c1[0], c1[1], c2[0], c2[1]) / gap_days
    p1 = max(float(prev["vals"].max()) if prev["vals"].size else 0.0, 1e-6)
    p2 = max(float(curr["vals"].max()) if curr["vals"].size else 0.0, 1e-6)
    ratio = max(p1, p2) / min(p1, p2)
    ok = (speed <= MAX_CENTROID_KM_DAY) and (ratio <= MAX_INTENSITY_RATIO)
    return ok, float(speed), float(ratio)

def merge_event_peak(grp: list, daily_cells: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cell-wise max hail across grouped days, returned as sparse triplets."""
    peak_map: dict[tuple[int, int], float] = {}
    for idx in grp:
        dc = daily_cells[idx]
        for r, c, v in zip(dc["rows"], dc["cols"], dc["vals"]):
            key = (int(r), int(c))
            fv = float(v)
            prev = peak_map.get(key)
            if prev is None or fv > prev:
                peak_map[key] = fv
    if not peak_map:
        return (
            np.empty(0, dtype=np.int16),
            np.empty(0, dtype=np.int16),
            np.empty(0, dtype=np.float32),
        )
    keys = list(peak_map.keys())
    rows = np.array([k[0] for k in keys], dtype=np.int16)
    cols = np.array([k[1] for k in keys], dtype=np.int16)
    vals = np.array([peak_map[k] for k in keys], dtype=np.float32)
    keep = vals >= DAMAGE_THRESHOLD_MM
    return rows[keep], cols[keep], vals[keep]

def group_events(dates: list, daily_cells: list) -> list:
    """Group active days into events using synoptic rules."""
    if not dates:
        return []

    log(f"\n  Grouping {len(dates):,} active days into events ...")
    t0 = time.time()

    # Initial grouping by temporal + spatial proximity
    groups = []
    current = [0]

    for k in range(1, len(dates)):
        gap_days = (dates[k] - dates[k - 1]).days

        if gap_days <= MAX_TEMPORAL_GAP:
            prev = daily_cells[k - 1]
            curr = daily_cells[k]
            if footprints_overlap_sparse(prev["rows"], prev["cols"], curr["rows"], curr["cols"]):
                coherent, _, _ = physically_coherent_merge(dates, daily_cells, k - 1, k)
                if coherent:
                    current.append(k)
                    continue

        groups.append(current)
        current = [k]

    groups.append(current)
    log(f"  Candidate events (before duration cap): {len(groups):,}")

    # Apply duration cap
    final_groups = []
    for grp in groups:
        if len(grp) <= 1:
            final_groups.append(grp)
            continue

        # Check span
        span = (dates[grp[-1]] - dates[grp[0]]).days + 1
        if span <= MAX_DURATION_DAYS:
            final_groups.append(grp)
        else:
            # Split at MAX_DURATION_DAYS boundaries
            sub = [grp[0]]
            sub_start = dates[grp[0]]
            for idx in grp[1:]:
                if (dates[idx] - sub_start).days < MAX_DURATION_DAYS:
                    sub.append(idx)
                else:
                    final_groups.append(sub)
                    sub = [idx]
                    sub_start = dates[idx]
            final_groups.append(sub)

    elapsed = time.time() - t0
    log(f"  Final events (after {MAX_DURATION_DAYS}-day cap): {len(final_groups):,}  ({elapsed:.0f}s)")
    return final_groups

def build_catalog(dates, daily_cells, groups):
    """Build event catalog DataFrame and sparse peak arrays."""
    import pandas as pd

    lats = LAT_MAX - (np.arange(NROWS) + 0.5) * DX
    cell_area_km2 = (DX * 111.32) * (DX * 111.32 * np.cos(np.radians(lats)))
    mean_cell_area = float(cell_area_km2.mean())

    records = []
    sparse_events = {}  # event_id -> {rows, cols, vals}

    for event_id, grp in enumerate(groups):
        rows, cols, vals = merge_event_peak(grp, daily_cells)
        n_cells = int(rows.size)
        if n_cells == 0:
            continue

        sparse_events[event_id] = {
            "rows": rows,
            "cols": cols,
            "vals": vals,
        }

        cell_lats = LAT_MAX - (rows + 0.5) * DX
        cell_lons = LON_MIN + (cols + 0.5) * DX
        total_w = float(vals.sum())
        if total_w > 0:
            centroid_lat = float((cell_lats * vals).sum() / total_w)
            centroid_lon = float((cell_lons * vals).sum() / total_w)
        else:
            centroid_lat = float(cell_lats.mean())
            centroid_lon = float(cell_lons.mean())

        start = dates[grp[0]]
        end = dates[grp[-1]]

        # v2.1 merge diagnostics within the grouped event
        centroid_speed_km_day = 0.0
        max_intensity_jump_ratio = 1.0
        if len(grp) > 1:
            speeds = []
            ratios = []
            for a, b in zip(grp[:-1], grp[1:]):
                _, speed, ratio = physically_coherent_merge(dates, daily_cells, a, b)
                speeds.append(speed)
                ratios.append(ratio)
            centroid_speed_km_day = float(np.nanmax(speeds)) if speeds else 0.0
            max_intensity_jump_ratio = float(np.nanmax(ratios)) if ratios else 1.0

        records.append({
            "event_id":           event_id,
            "start_date":         start,
            "end_date":           end,
            "duration_days":      (end - start).days + 1,
            "n_active_cells":     n_cells,
            "footprint_area_km2": round(n_cells * mean_cell_area, 0),
            "peak_hail_mm":       round(float(vals.max()), 1),
            "peak_hail_in":       round(float(vals.max()) / 25.4, 2),
            "mean_hail_mm":       round(float(vals.mean()), 1),
            "centroid_lat":       round(centroid_lat, 3),
            "centroid_lon":       round(centroid_lon, 3),
            "doy":                start.timetuple().tm_yday,
            "centroid_speed_km_day": round(centroid_speed_km_day, 1),
            "max_intensity_jump_ratio": round(max_intensity_jump_ratio, 2),
            "merge_quality_flag": "ok" if centroid_speed_km_day <= MAX_CENTROID_KM_DAY and max_intensity_jump_ratio <= MAX_INTENSITY_RATIO else "review",
        })

    return pd.DataFrame(records), sparse_events

def save_outputs(event_df, sparse_events):
    """Write event catalog CSV and sparse peak arrays."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # CSV catalog
    csv_path = OUT_DIR / "event_catalog.csv"
    event_df.to_csv(csv_path, index=False)
    log(f"  Wrote {csv_path.name}: {len(event_df):,} events")

    # Sparse peaks: save as npz with per-event arrays
    arrays = {}
    for eid, data in sparse_events.items():
        arrays[f"rows_{eid}"] = data["rows"]
        arrays[f"cols_{eid}"] = data["cols"]
        arrays[f"vals_{eid}"] = data["vals"]
    arrays["n_events"] = np.array([len(sparse_events)])
    arrays["event_ids"] = np.array(list(sparse_events.keys()), dtype=np.int32)
    arrays["grid_shape"] = np.array([NROWS, NCOLS])

    npz_path = OUT_DIR / "event_peaks.npz"
    np.savez_compressed(npz_path, **arrays)
    size_mb = npz_path.stat().st_size / 1e6
    log(f"  Wrote {npz_path.name}: {size_mb:.1f} MB (sparse, {len(sparse_events):,} events)")

def print_summary(event_df):
    """Print event catalog summary statistics."""
    log(f"\n  ── Event Catalog Summary ──")
    log(f"  Events: {len(event_df):,}")
    log(f"  Period: {event_df['start_date'].min()} to {event_df['end_date'].max()}")
    log(f"  Years:  {event_df['start_date'].apply(lambda d: d.year).nunique()}")

    dur = event_df["duration_days"]
    log(f"\n  Duration (days): mean={dur.mean():.1f}  median={dur.median():.0f}  max={dur.max()}")

    fp = event_df["footprint_area_km2"]
    log(f"  Footprint (km²): mean={fp.mean():,.0f}  median={fp.median():,.0f}  max={fp.max():,.0f}")

    ph = event_df["peak_hail_mm"]
    log(f"  Peak hail (mm):  mean={ph.mean():.1f}  max={ph.max():.1f}")
    log(f"  Peak hail (in):  mean={event_df['peak_hail_in'].mean():.2f}  max={event_df['peak_hail_in'].max():.2f}")

    log(f"\n  Duration distribution:")
    for d, c in sorted(dur.value_counts().items()):
        log(f"    {d} day{'s' if d > 1 else ''}: {c:,} events")

    log(f"\n  Annual event counts:")
    annual = event_df.groupby(event_df["start_date"].apply(lambda d: d.year)).size()
    log(f"    mean={annual.mean():.0f}/yr  min={annual.min()}  max={annual.max()}")

def validate_outputs() -> bool:
    errors = []
    csv_path = OUT_DIR / "event_catalog.csv"
    npz_path = OUT_DIR / "event_peaks.npz"

    if not csv_path.exists():
        errors.append("Missing event_catalog.csv")
    elif csv_path.stat().st_size == 0:
        errors.append("Empty event_catalog.csv")
    else:
        import pandas as pd
        df = pd.read_csv(csv_path)
        if len(df) < 100:
            errors.append(f"Too few events: {len(df)}")
        if df["peak_hail_mm"].max() > 300:
            errors.append(f"Implausible peak hail: {df['peak_hail_mm'].max()} mm")
        if df["duration_days"].max() > MAX_DURATION_DAYS:
            errors.append(f"Duration cap violated: max={df['duration_days'].max()}")

    if not npz_path.exists():
        errors.append("Missing event_peaks.npz")
    else:
        data = np.load(npz_path)
        n = int(data["n_events"][0])
        if n < 100:
            errors.append(f"Too few events in npz: {n}")

    if errors:
        log("Validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log(f"Output validation passed ✓")
    return True

def main():
    parser = argparse.ArgumentParser(description="Build event catalog from corrected MESH75.")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  Event Identification — Stage 08")
    log(f"{'='*60}")
    log(f"  Input:     {IN_DIR}")
    log(f"  Output:    {OUT_DIR}")
    log(f"  Threshold: {DAMAGE_THRESHOLD_MM} mm ({DAMAGE_THRESHOLD_MM/25.4:.1f} in)")
    log(f"  Buffer:    {BUFFER_CELLS} cells (~{BUFFER_CELLS * DX * 111:.0f} km)")
    log(f"  Max dur:   {MAX_DURATION_DAYS} days")

    t0 = time.time()

    # Load data
    log("\n[1/3] Loading daily corrected MESH75 rasters")
    dates, daily_cells = load_daily_data()

    if not dates:
        log("  ERROR: No active hail days found. Check stage 05 outputs.")
        sys.exit(1)

    # Group events
    log("\n[2/3] Identifying events")
    groups = group_events(dates, daily_cells)

    # Build catalog
    log("\n[3/3] Building catalog and sparse peak arrays")
    event_df, sparse_events = build_catalog(dates, daily_cells, groups)

    save_outputs(event_df, sparse_events)
    print_summary(event_df)

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/60:.1f} min")
    log(f"{'='*60}\n")

    ok = validate_outputs()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
