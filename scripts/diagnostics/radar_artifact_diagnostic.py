#!/usr/bin/env python3
"""
Radar artifact diagnostic — range-from-NEXRAD structure and source-era comparison.

Quantifies spatial radar artifacts in the corrected MESH75 archive:
  - per-cell distance to nearest CONUS WSR-88D site;
  - mean annual maxima and speckle scores by radar source era (MYRORSS / GridRad / MRMS);
  - range-binned MESH statistics;
  - SPC collocated bias vs range (when validation pairs exist);
  - fitted range-debias factors for Stage 05.

Usage (repo root):
  .venv/bin/python scripts/diagnostics/radar_artifact_diagnostic.py
  .venv/bin/python scripts/diagnostics/radar_artifact_diagnostic.py --mesh-dir data/historical/mesh_0.05deg_corrected
  .venv/bin/python scripts/diagnostics/radar_artifact_diagnostic.py --pairs-csv data/historical/validation/mesh_vs_spc_pairs.csv
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts._config import NCOLS, NROWS  # noqa: E402
from scripts._io import write_geotiff  # noqa: E402
from scripts._mapping import (  # noqa: E402
    create_conus_axes,
    plot_raster_on_axis,
    save_conus_raster_map,
)
from scripts._radar_geometry import (  # noqa: E402
    CALIB_DIR,
    DEFAULT_RANGE_BIN_EDGES_KM,
    MM_PER_INCH,
    RANGE_DEBIAS_NPZ,
    classify_mesh_source,
    ensure_range_km_grid,
    fit_range_debias_factors,
    range_bin_centers,
    save_range_debias,
    write_nexrad_sites_csv,
)

CORRECTED_DIR = REPO / "data" / "historical" / "mesh_0.05deg_corrected"
OUT_DIR = REPO / "data" / "analysis" / "radar_artifacts"
PAIRS_DEFAULT = REPO / "data" / "historical" / "validation" / "mesh_vs_spc_pairs.csv"
MESH_RE = re.compile(r"mesh_(\d{8})\.tif$")
SPECKLE_THRESH = 2.5
ACTIVE_MM = 25.4


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Radar artifact and range-debias diagnostic.")
    p.add_argument("--mesh-dir", type=Path, default=CORRECTED_DIR)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--pairs-csv", type=Path, default=PAIRS_DEFAULT)
    p.add_argument("--min-date", type=str, default=None)
    p.add_argument("--max-date", type=str, default=None)
    p.add_argument("--skip-geotiff", action="store_true")
    p.add_argument("--no-fit-debias", action="store_true", help="Skip writing range_debias.npz")
    p.add_argument("--every-n-days", type=int, default=1, help="Process every Nth day (quick smoke)")
    return p.parse_args()


def iter_mesh_tifs(mesh_dir: Path, d_min: date | None, d_max: date | None):
    for path in sorted(mesh_dir.rglob("mesh_????????.tif")):
        m = MESH_RE.search(path.name)
        if not m:
            continue
        ds = m.group(1)
        day = date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        if d_min and day < d_min:
            continue
        if d_max and day > d_max:
            continue
        yield day, path


def local_median_8(data: np.ndarray) -> np.ndarray:
    """3×3 neighborhood median (center excluded in speckle test via comparison)."""
    from scipy.ndimage import median_filter

    return median_filter(data, size=3, mode="nearest")


def accumulate_era_stats(mesh_dir: Path, d_min: date | None, d_max: date | None, every_n: int = 1):
    """Scan archive; return per-era annual-max mean, speckle counts, range-binned sums."""
    sources = ("MYRORSS", "GridRad", "MRMS")
    edges = DEFAULT_RANGE_BIN_EDGES_KM
    n_bins = len(edges) - 1
    range_km = ensure_range_km_grid(CALIB_DIR / "nearest_radar_distance_km.npy")
    bin_idx = np.clip(np.digitize(range_km, edges, right=False) - 1, 0, n_bins - 1)

    era_years: dict[str, set[int]] = {s: set() for s in sources}
    annual_max: dict[str, np.ndarray] = {s: np.zeros((NROWS, NCOLS), np.float32) for s in sources}
    hail_days: dict[str, np.ndarray] = {s: np.zeros((NROWS, NCOLS), np.uint32) for s in sources}
    speckle_days: dict[str, np.ndarray] = {s: np.zeros((NROWS, NCOLS), np.uint32) for s in sources}
    bin_sum: dict[str, np.ndarray] = {s: np.zeros(n_bins, np.float64) for s in sources}
    bin_count: dict[str, np.ndarray] = {s: np.zeros(n_bins, np.uint64) for s in sources}
    bin_cells: dict[str, np.ndarray] = {s: np.zeros(n_bins, np.uint64) for s in sources}

    for bi in range(n_bins):
        mask = bin_idx == bi
        for s in sources:
            bin_cells[s][bi] = int(mask.sum())

    tifs = list(iter_mesh_tifs(mesh_dir, d_min, d_max))
    if every_n > 1:
        tifs = tifs[::every_n]
    if not tifs:
        return None

    t0 = time.time()
    for i, (day, path) in enumerate(tifs, 1):
        src = classify_mesh_source(day)
        era_years[src].add(day.year)
        with rasterio.open(path) as src_ds:
            data = src_ds.read(1).astype(np.float32)
        active = data >= ACTIVE_MM
        if np.any(active):
            hail_days[src] += active.astype(np.uint32)
            med = local_median_8(data)
            speckle = active & (data > SPECKLE_THRESH * np.maximum(med, 1.0))
            speckle_days[src] += speckle.astype(np.uint32)
            daily_peak = float(data.max())
            for bi in range(n_bins):
                cell_mask = bin_idx == bi
                if cell_mask.any():
                    bin_sum[src][bi] += daily_peak
                    bin_count[src][bi] += 1
        np.maximum(annual_max[src], data, out=annual_max[src])
        if i % 500 == 0:
            print(f"  scanned {i:,}/{len(tifs):,} rasters ({time.time() - t0:.0f}s)", flush=True)

    n_years = {s: max(1, len(era_years[s])) for s in sources}
    mean_annual = {s: annual_max[s] / n_years[s] for s in sources}
    speckle_frac = {
        s: np.divide(
            speckle_days[s].astype(np.float32),
            np.maximum(hail_days[s], 1).astype(np.float32),
        )
        for s in sources
    }
    return {
        "range_km": range_km,
        "edges": edges,
        "n_years": n_years,
        "mean_annual_max": mean_annual,
        "speckle_fraction": speckle_frac,
        "hail_days_per_year": {s: hail_days[s].astype(np.float32) / n_years[s] for s in sources},
        "bin_peak_mean": {s: bin_sum[s] / np.maximum(bin_count[s], 1) for s in sources},
        "bin_count": bin_count,
        "n_files": len(tifs),
    }


def range_binned_cell_stats(
    mean_annual: np.ndarray,
    range_km: np.ndarray,
    edges: np.ndarray,
) -> pd.DataFrame:
    n_bins = len(edges) - 1
    bin_idx = np.clip(np.digitize(range_km, edges, right=False) - 1, 0, n_bins - 1)
    rows = []
    centers = range_bin_centers(edges)
    for bi in range(n_bins):
        mask = (bin_idx == bi) & (mean_annual > 0)
        vals = mean_annual[mask]
        rows.append(
            {
                "range_bin_lo_km": float(edges[bi]),
                "range_bin_hi_km": float(edges[bi + 1]),
                "range_bin_center_km": float(centers[bi]),
                "n_active_cells": int(mask.sum()),
                "mean_annual_max_mm": round(float(vals.mean()), 2) if vals.size else 0.0,
                "p95_annual_max_mm": round(float(np.percentile(vals, 95)), 2) if vals.size else 0.0,
            }
        )
    return pd.DataFrame(rows)


def spc_bias_by_range(pairs_csv: Path, edges: np.ndarray) -> pd.DataFrame:
    if not pairs_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(pairs_csv)
    if df.empty:
        return pd.DataFrame()
    from scripts._radar_geometry import nexrad_sites_conus

    site_lats, site_lons, _ = nexrad_sites_conus()
    ranges = []
    for _, row in df.iterrows():
        lat, lon = float(row["lat"]), float(row["lon"])
        dlat = np.radians(site_lats - lat)
        dlon = np.radians(site_lons - lon)
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(np.radians(lat)) * np.cos(np.radians(site_lats)) * np.sin(dlon / 2) ** 2
        )
        dist = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))
        ranges.append(float(dist.min()))
    df = df.copy()
    df["range_km"] = ranges
    df["source"] = df["date"].astype(str).map(
        lambda d: classify_mesh_source(
            date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        )
    )
    df["mesh_bias_mm"] = df["mesh75_mm"] - df["spc_size_in"] * MM_PER_INCH
    df["mesh_report_ratio"] = (df["spc_size_in"] * MM_PER_INCH) / df["mesh75_mm"].clip(lower=0.1)
    centers = range_bin_centers(edges)
    rows = []
    for src in ("MYRORSS", "GridRad", "MRMS"):
        sub = df[(df["source"] == src) & (df["spc_size_in"] >= 1.0) & (df["mesh75_mm"] >= 5)]
        for bi in range(len(edges) - 1):
            lo, hi = edges[bi], edges[bi + 1]
            chunk = sub[(sub["range_km"] >= lo) & (sub["range_km"] < hi)]
            if len(chunk) < 10:
                continue
            rows.append(
                {
                    "source": src,
                    "range_bin_center_km": float(centers[bi]),
                    "n_pairs": len(chunk),
                    "median_bias_mm": round(float(chunk["mesh_bias_mm"].median()), 2),
                    "median_mesh_report_ratio": round(float(chunk["mesh_report_ratio"].median()), 3),
                }
            )
    return pd.DataFrame(rows)


def plot_range_distance_map(range_km: np.ndarray, out_dir: Path) -> Path:
    return save_conus_raster_map(
        range_km,
        out_dir / "map_nearest_radar_distance_km.png",
        title="Distance to nearest CONUS NEXRAD (km)",
        cbar_label="km",
        cmap="viridis",
        vmin=0,
        vmax=250,
    )


def plot_mean_annual_by_source(mean_maps: dict[str, np.ndarray], out_dir: Path) -> Path:
    fig, axes = create_conus_axes(1, 3, figsize=(14, 4.5), sharex=True, sharey=True)
    ax_list = np.atleast_1d(axes).ravel()
    vmax = 80.0
    mappable = None
    for ax, src in zip(ax_list, ("MYRORSS", "GridRad", "MRMS")):
        mappable = plot_raster_on_axis(ax, mean_maps[src], cmap="YlOrRd", vmin=0, vmax=vmax)
        ax.set_title(f"Mean annual max MESH75 — {src}")
    fig.colorbar(mappable, ax=list(ax_list), label="mm", shrink=0.7)
    fig.tight_layout()
    path = out_dir / "map_mean_annual_max_by_source.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_speckle_by_source(speckle: dict[str, np.ndarray], out_dir: Path) -> Path:
    fig, axes = create_conus_axes(1, 3, figsize=(14, 4.5), sharex=True, sharey=True)
    ax_list = np.atleast_1d(axes).ravel()
    mappable = None
    for ax, src in zip(ax_list, ("MYRORSS", "GridRad", "MRMS")):
        mappable = plot_raster_on_axis(
            ax, speckle[src], cmap="magma", vmin=0, vmax=0.5,
        )
        ax.set_title(f"Speckle fraction — {src}")
    fig.colorbar(mappable, ax=list(ax_list), label="fraction of hail days", shrink=0.7)
    fig.tight_layout()
    path = out_dir / "map_speckle_fraction_by_source.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_spc_ratio_vs_range(spc_df: pd.DataFrame, out_dir: Path) -> Path | None:
    if spc_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 5))
    for src in ("MYRORSS", "GridRad", "MRMS"):
        sub = spc_df[spc_df["source"] == src]
        if sub.empty:
            continue
        ax.plot(
            sub["range_bin_center_km"],
            sub["median_mesh_report_ratio"],
            marker="o",
            label=src,
        )
    ax.axhline(1.0, color="gray", ls="--", lw=0.8)
    ax.set_xlabel("Distance to nearest NEXRAD (km)")
    ax.set_ylabel("Median SPC report / MESH75 ratio")
    ax.set_title("SPC/MESH vs range (≥1 in reports)")
    ax.legend()
    fig.tight_layout()
    path = out_dir / "spc_mesh_ratio_vs_range.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_debias_factors(fit: dict, out_dir: Path) -> Path:
    centers = fit["range_bin_centers_km"]
    fig, ax = plt.subplots(figsize=(8, 5))
    for src, color in zip(("MYRORSS", "GridRad", "MRMS"), ("C0", "C1", "C2")):
        ax.plot(centers, fit["factors"][src], marker="o", label=src, color=color)
    ax.axhline(1.0, color="gray", ls="--")
    ax.set_xlabel("Distance to nearest NEXRAD (km)")
    ax.set_ylabel("Debias factor (multiply MESH)")
    ax.set_title("Fitted range-dependent debias factors (SPC-normalized at 125 km)")
    ax.legend()
    fig.tight_layout()
    path = out_dir / "range_debias_factors.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def write_readme(out_dir: Path, summary: dict) -> None:
    lines = [
        "# Radar artifact diagnostic",
        "",
        "Generated by `scripts/diagnostics/radar_artifact_diagnostic.py`.",
        "",
        "Diagnoses spatial radar artifacts (range-dependent bias, speckle, source-era",
        "differences) in the Stage 05 corrected MESH75 archive. Writes",
        "`data/analysis/calibration/range_debias.npz` for Stage 05 when SPC pairs exist.",
        "",
        "## Summary",
        "",
        f"- Rasters scanned: **{summary.get('n_files', 0):,}**",
        f"- Era years: MYRORSS {summary.get('years', {}).get('MYRORSS', '?')}, "
        f"GridRad {summary.get('years', {}).get('GridRad', '?')}, "
        f"MRMS {summary.get('years', {}).get('MRMS', '?')}",
        "",
        "## Key outputs",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `map_nearest_radar_distance_km.png` | Distance to nearest WSR-88D |",
        "| `map_mean_annual_max_by_source.png` | Mean annual max by radar era |",
        "| `map_speckle_fraction_by_source.png` | Isolated-spike fraction by era |",
        "| `range_binned_annual_max_by_source.csv` | Mean annual max vs range bin |",
        "| `spc_mesh_ratio_by_range_source.csv` | SPC/MESH ratio vs range (if pairs exist) |",
        "| `range_debias_factors.csv` | Fitted Stage 05 multiplicative factors |",
        "| `../calibration/range_debias.npz` | Stage 05 range debias table |",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    d_min = date.fromisoformat(args.min_date) if args.min_date else None
    d_max = date.fromisoformat(args.max_date) if args.max_date else None

    print("Radar artifact diagnostic")
    print(f"  mesh_dir: {args.mesh_dir}")
    print(f"  out_dir:  {out_dir}")

    write_nexrad_sites_csv(out_dir / "nexrad_sites_conus.csv")
    stats = accumulate_era_stats(args.mesh_dir, d_min, d_max, every_n=args.every_n_days)
    if stats is None:
        raise SystemExit(f"No mesh TIFFs under {args.mesh_dir}")

    range_km = stats["range_km"]
    edges = stats["edges"]

    if not args.skip_geotiff:
        write_geotiff(range_km.astype(np.float32), out_dir / "nearest_radar_distance_km.tif")

    plot_range_distance_map(range_km, out_dir)
    plot_mean_annual_by_source(stats["mean_annual_max"], out_dir)
    plot_speckle_by_source(stats["speckle_fraction"], out_dir)

    rb_rows = []
    for src in ("MYRORSS", "GridRad", "MRMS"):
        df = range_binned_cell_stats(stats["mean_annual_max"][src], range_km, edges)
        df.insert(0, "source", src)
        rb_rows.append(df)
    rb_df = pd.concat(rb_rows, ignore_index=True)
    rb_df.to_csv(out_dir / "range_binned_annual_max_by_source.csv", index=False)

    speckle_summary = []
    for src in ("MYRORSS", "GridRad", "MRMS"):
        sf = stats["speckle_fraction"][src]
        active = stats["hail_days_per_year"][src] > 0
        speckle_summary.append(
            {
                "source": src,
                "n_years": stats["n_years"][src],
                "mean_speckle_fraction_active_cells": round(float(sf[active].mean()), 4) if active.any() else 0.0,
                "p95_speckle_fraction": round(float(np.percentile(sf[active], 95)), 4) if active.any() else 0.0,
            }
        )
    pd.DataFrame(speckle_summary).to_csv(out_dir / "speckle_summary_by_source.csv", index=False)

    spc_df = spc_bias_by_range(args.pairs_csv, edges)
    if not spc_df.empty:
        spc_df.to_csv(out_dir / "spc_mesh_ratio_by_range_source.csv", index=False)

    fit = None
    if not args.no_fit_debias and args.pairs_csv.exists():
        pairs = pd.read_csv(args.pairs_csv).to_dict("records")
        fit = fit_range_debias_factors(pairs)
        fac_rows = []
        centers = fit["range_bin_centers_km"]
        for src in ("MYRORSS", "GridRad", "MRMS"):
            for c, f in zip(centers, fit["factors"][src]):
                fac_rows.append(
                    {
                        "source": src,
                        "range_bin_center_km": float(c),
                        "debias_factor": round(float(f), 4),
                        "n_pairs_era": fit["n_pairs"][src],
                    }
                )
        pd.DataFrame(fac_rows).to_csv(out_dir / "range_debias_factors.csv", index=False)
        save_range_debias(fit, RANGE_DEBIAS_NPZ)
        plot_debias_factors(fit, out_dir)
        print(f"  Wrote range debias: {RANGE_DEBIAS_NPZ}")
    else:
        print("  Skipped range-debias fit (no pairs CSV or --no-fit-debias)")

    # GridRad minus MYRORSS mean annual max (artifact excess map).
    diff = stats["mean_annual_max"]["GridRad"] - stats["mean_annual_max"]["MYRORSS"]
    if not args.skip_geotiff:
        write_geotiff(diff.astype(np.float32), out_dir / "gridrad_minus_myrorss_mean_annual_max.tif")
    save_conus_raster_map(
        diff,
        out_dir / "map_gridrad_minus_myrorss_mean_annual_max.png",
        title="GridRad − MYRORSS mean annual max MESH75 (mm)",
        cbar_label="mm",
        cmap="RdBu_r",
        symmetric=True,
    )

    if not spc_df.empty:
        plot_spc_ratio_vs_range(spc_df, out_dir)

    write_readme(
        out_dir,
        {
            "n_files": stats["n_files"],
            "years": stats["n_years"],
        },
    )
    print("Done.")


if __name__ == "__main__":
    main()
