#!/usr/bin/env python3
"""
Per-cell severe-hail-day climatology and MESH75 threshold sensitivity diagnostic.

Counts, for each 0.05° grid cell, how many convective days per year exceed
several literature-based MESH75 thresholds on the Stage 05 corrected archive.
Also reports CONUS-wide "any-cell" hail-day totals for comparison with Stage 08
event counts and SPC report-day climatologies.

Literature thresholds follow Murillo & Homeyer (2021, MWR), Cintineo et al.
(2012, WAF), and Wendt & Jirak (2021, WAF).

Usage (from repo root):
  .venv/bin/python scripts/diagnostics/hail_day_climatology.py
  .venv/bin/python scripts/diagnostics/hail_day_climatology.py --mesh-dir data/historical/mesh_0.05deg_corrected
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts._config import LAT_MAX, LON_MIN, NCOLS, NROWS, DX  # noqa: E402
from scripts._io import write_geotiff  # noqa: E402

CORRECTED_DIR = REPO / "data" / "historical" / "mesh_0.05deg_corrected"
OUT_DIR = REPO / "data" / "analysis" / "hail_day_climatology"
MESH_RE = re.compile(r"mesh_(\d{8})\.tif$")

MRMS_START = date(2020, 10, 14)
GRIDRAD_START = date(2012, 1, 1)
GRIDRAD_END = date(2020, 10, 13)

# Murillo & Homeyer (2021) skill thresholds + conventional / significant severe.
@dataclass(frozen=True)
class ThresholdSpec:
    key: str
    mm: float
    label: str
    literature_ref: str

DEFAULT_THRESHOLDS: tuple[ThresholdSpec, ...] = (
    ThresholdSpec(
        "conv_25p4mm",
        25.4,
        "Conventional severe (1.0 in)",
        "SPC/NWS; Murillo et al. (2021) conventional",
    ),
    ThresholdSpec(
        "skill_29mm",
        29.0,
        "MRMS/Cintineo skill (~1.14 in)",
        "Cintineo et al. (2012); Wendt & Jirak (2021)",
    ),
    ThresholdSpec(
        "meshwitt_35p6mm",
        35.56,
        "MESHWitt skill (1.14 in)",
        "Murillo et al. (2021) Table 1",
    ),
    ThresholdSpec(
        "mesh75_41p9mm",
        41.91,
        "MESH75 skill (1.65 in)",
        "Murillo et al. (2021) Table 1",
    ),
    ThresholdSpec(
        "sig_50p8mm",
        50.8,
        "Significant severe (2.0 in)",
        "SPC significant severe; Murillo et al. (2021)",
    ),
    ThresholdSpec(
        "mesh95_63p3mm",
        63.25,
        "MESH95 skill (2.49 in)",
        "Murillo et al. (2021) Table 1",
    ),
)

# Cintineo et al. (2012) Great Plains reference for per-cell severe hail days.
CINTINEO_GP_MAX_DAYS = 12.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Per-cell hail-day climatology diagnostic.")
    p.add_argument("--mesh-dir", type=Path, default=CORRECTED_DIR)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--min-date", type=str, default=None)
    p.add_argument("--max-date", type=str, default=None)
    p.add_argument(
        "--thresholds",
        type=str,
        default=None,
        help="Comma-separated threshold keys (default: all literature set)",
    )
    p.add_argument("--skip-geotiff", action="store_true", help="Skip GeoTIFF map writes")
    return p.parse_args()


def classify_source(day: date) -> str:
    if day >= MRMS_START:
        return "MRMS"
    if GRIDRAD_START <= day <= GRIDRAD_END:
        return "GridRad"
    return "MYRORSS"


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


def selected_thresholds(keys: str | None) -> tuple[ThresholdSpec, ...]:
    if not keys:
        return DEFAULT_THRESHOLDS
    wanted = {k.strip() for k in keys.split(",")}
    specs = [t for t in DEFAULT_THRESHOLDS if t.key in wanted]
    if not specs:
        raise SystemExit(f"No matching thresholds for: {keys}")
    return tuple(specs)


def accumulate_hail_days(
    mesh_dir: Path,
    specs: tuple[ThresholdSpec, ...],
    d_min: date | None,
    d_max: date | None,
) -> tuple[
    dict[str, np.ndarray],
    dict[str, dict[int, int]],
    dict[int, dict[str, int]],
    list[int],
    int,
]:
    """Return cell counts, monthly national counts, annual national counts, years, n_files."""
    cell_counts = {s.key: np.zeros((NROWS, NCOLS), dtype=np.uint32) for s in specs}
    monthly_national: dict[str, dict[int, int]] = {s.key: {m: 0 for m in range(1, 13)} for s in specs}
    annual_national: dict[int, dict[str, int]] = {}
    n_files = 0

    tifs = list(iter_mesh_tifs(mesh_dir, d_min, d_max))
    if not tifs:
        return cell_counts, monthly_national, annual_national, [], 0

    for i, (day, path) in enumerate(tifs, 1):
        year_row = annual_national.setdefault(day.year, {s.key: 0 for s in specs})
        with rasterio.open(path) as src:
            data = src.read(1)
        n_files += 1
        for spec in specs:
            active = data >= spec.mm
            if np.any(active):
                year_row[spec.key] += 1
                monthly_national[spec.key][day.month] += 1
                cell_counts[spec.key] += active.astype(np.uint32)
        if i % 1000 == 0:
            print(f"  scanned {i:,}/{len(tifs):,} rasters ...")

    years = sorted(annual_national)
    return cell_counts, monthly_national, annual_national, years, n_files


def summarize_per_cell(
    counts: np.ndarray,
    n_years: int,
    spec: ThresholdSpec,
) -> dict:
    """Grid-wide distribution of mean annual hail days per cell."""
    rate = counts.astype(np.float32) / max(n_years, 1)
    active_cells = rate > 0
    n_active = int(active_cells.sum())
    nrows, ncols = rate.shape
    row_lats = LAT_MAX - (np.arange(nrows)[:, None] + 0.5) * DX
    col_lons = LON_MIN + (np.arange(ncols)[None, :] + 0.5) * DX
    gp_mask = (
        (rate > 0)
        & (row_lats >= 32.0)
        & (row_lats <= 46.0)
        & (col_lons >= -104.0)
        & (col_lons <= -94.0)
    )
    gp_rates = rate[gp_mask]
    return {
        "threshold_key": spec.key,
        "threshold_mm": spec.mm,
        "threshold_label": spec.label,
        "literature_ref": spec.literature_ref,
        "n_years": n_years,
        "cells_with_any_hail_days": n_active,
        "frac_conus_cells_active": round(n_active / (rate.shape[0] * rate.shape[1]), 4),
        "max_days_per_year_any_cell": round(float(rate.max()), 2),
        "p95_days_per_year": round(float(np.percentile(rate[active_cells], 95)), 2) if n_active else 0.0,
        "p99_days_per_year": round(float(np.percentile(rate[active_cells], 99)), 2) if n_active else 0.0,
        "mean_days_active_cells": round(float(rate[active_cells].mean()), 2) if n_active else 0.0,
        "median_days_active_cells": round(float(np.median(rate[active_cells])), 2) if n_active else 0.0,
        "gp_mean_days_per_year": round(float(gp_rates.mean()), 2) if gp_rates.size else 0.0,
        "gp_max_days_per_year": round(float(gp_rates.max()), 2) if gp_rates.size else 0.0,
        "gp_p95_days_per_year": round(float(np.percentile(gp_rates, 95)), 2) if gp_rates.size else 0.0,
        "cintineo_gp_benchmark_days": CINTINEO_GP_MAX_DAYS,
        "gp_max_vs_cintineo_ratio": round(float(gp_rates.max()) / CINTINEO_GP_MAX_DAYS, 2)
        if gp_rates.size
        else 0.0,
    }


def national_annual_dataframe(annual_national: dict[int, dict[str, int]]) -> pd.DataFrame:
    rows = [{"year": year, **counts} for year, counts in sorted(annual_national.items())]
    return pd.DataFrame(rows)


def plot_maps(
    rates: dict[str, np.ndarray],
    specs: tuple[ThresholdSpec, ...],
    out_dir: Path,
) -> list[Path]:
    """Write quick-look hail-days-per-year maps for key thresholds."""
    keys = [s.key for s in specs if s.key in ("conv_25p4mm", "skill_29mm", "mesh75_41p9mm", "sig_50p8mm")]
    paths: list[Path] = []
    lons = LON_MIN + (np.arange(NCOLS) + 0.5) * DX
    lats = LAT_MAX - (np.arange(NROWS) + 0.5) * DX
    for key in keys:
        spec = next(s for s in specs if s.key == key)
        data = rates[key]
        vmax = min(20.0, float(np.percentile(data[data > 0], 99)) if np.any(data > 0) else 1.0)
        fig, ax = plt.subplots(figsize=(10, 4.5))
        im = ax.imshow(
            data,
            origin="upper",
            extent=[lons.min(), lons.max(), lats.min(), lats.max()],
            vmin=0,
            vmax=max(vmax, 1.0),
            cmap="YlOrRd",
            aspect="auto",
        )
        ax.set_title(f"Mean annual hail days — {spec.label} ({spec.mm} mm)")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        plt.colorbar(im, ax=ax, label="days / year", shrink=0.8)
        fig.tight_layout()
        path = out_dir / f"map_hail_days_per_year_{key}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
    return paths


def plot_seasonal_curves(monthly_df: pd.DataFrame, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4))
    months = list(range(1, 13))
    labels = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for _, row in monthly_df.iterrows():
        per_day = [row[f"month_{m:02d}"] / days_in_month[m - 1] for m in months]
        ax.plot(months, per_day, marker="o", ms=4, label=row["threshold_label"])
    ax.set_xticks(months)
    ax.set_xticklabels(labels)
    ax.set_ylabel("CONUS any-cell hail days / calendar day")
    ax.set_title("Seasonal cycle by MESH75 threshold (national any-cell counts)")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = out_dir / "seasonal_national_hail_days_by_threshold.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def write_readme(out_dir: Path, summary: pd.DataFrame) -> None:
    lines = [
        "# Hail-day climatology diagnostic",
        "",
        "Generated by `scripts/diagnostics/hail_day_climatology.py`.",
        "",
        "Per-cell **hail days per year** count convective days when daily peak",
        "MESH75 at that 0.05° cell meets the threshold. National **any-cell**",
        "counts increment once per day if any CONUS cell exceeds the threshold",
        "(comparable to Stage 08 event-definition sensitivity).",
        "",
        "## Literature benchmarks",
        "",
        "| Reference | Metric | Typical value |",
        "|-----------|--------|---------------|",
        "| Cintineo et al. (2012) | Max severe hail days / year (GP, MESH≥29 mm) | ~11–12 |",
        "| Murillo et al. (2021) | Per 80 km cell; conventional 25.4 mm inflates vs reports | 2–4× reports locally |",
        "| Wendt & Jirak (2021) | MRMS MESH vs Storm Data hail hours/days | MESH 2–4× reports |",
        "",
        "## Latest threshold summary",
        "",
        "```",
        summary.to_string(index=False),
        "```",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    specs = selected_thresholds(args.thresholds)
    d_min = datetime.strptime(args.min_date, "%Y-%m-%d").date() if args.min_date else None
    d_max = datetime.strptime(args.max_date, "%Y-%m-%d").date() if args.max_date else None

    if not args.mesh_dir.is_dir():
        raise SystemExit(f"Mesh directory not found: {args.mesh_dir}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"Scanning {args.mesh_dir} ...")
    cell_counts, monthly_national, annual_national, years, n_files = accumulate_hail_days(
        args.mesh_dir, specs, d_min, d_max
    )
    if n_files == 0:
        raise SystemExit(f"No mesh TIFFs under {args.mesh_dir}")

    n_years = len(years)
    print(f"  {n_files:,} rasters over {n_years} years ({years[0]}–{years[-1]})")

    rates = {k: v.astype(np.float32) / n_years for k, v in cell_counts.items()}
    summary_rows = [summarize_per_cell(cell_counts[s.key], n_years, s) for s in specs]
    summary_df = pd.DataFrame(summary_rows)
    summary_path = args.out_dir / "threshold_benchmark_summary.csv"
    summary_df.to_csv(summary_path, index=False)

    national_df = national_annual_dataframe(annual_national)
    national_path = args.out_dir / "national_annual_hail_days.csv"
    national_df.to_csv(national_path, index=False)

    monthly_rows = []
    for spec in specs:
        row = {
            "threshold_key": spec.key,
            "threshold_mm": spec.mm,
            "threshold_label": spec.label,
        }
        for m in range(1, 13):
            row[f"month_{m:02d}"] = monthly_national[spec.key][m]
        monthly_rows.append(row)
    monthly_df = pd.DataFrame(monthly_rows)
    monthly_path = args.out_dir / "monthly_national_hail_days.csv"
    monthly_df.to_csv(monthly_path, index=False)

    if not args.skip_geotiff:
        for spec in specs:
            out_tif = args.out_dir / f"hail_days_per_year_{spec.key}.tif"
            write_geotiff(
                rates[spec.key],
                out_tif,
                tags={
                    "THRESHOLD_MM": str(spec.mm),
                    "THRESHOLD_KEY": spec.key,
                    "N_YEARS": str(n_years),
                    "UNITS": "hail_days_per_year",
                },
            )

    map_paths = plot_maps(rates, specs, args.out_dir)
    seasonal_path = plot_seasonal_curves(monthly_df, args.out_dir)
    write_readme(args.out_dir, summary_df)

    elapsed = time.time() - t0
    print(f"\nWrote diagnostics to {args.out_dir}/ ({elapsed:.0f}s)")
    print("\n--- Threshold benchmark summary ---")
    print(
        summary_df[
            [
                "threshold_key",
                "threshold_mm",
                "gp_max_days_per_year",
                "gp_mean_days_per_year",
                "max_days_per_year_any_cell",
                "median_days_active_cells",
            ]
        ].to_string(index=False)
    )
    if "conv_25p4mm" in national_df.columns:
        print(
            f"\nNational any-cell hail days/yr (25.4 mm): "
            f"mean={national_df['conv_25p4mm'].mean():.1f}  "
            f"median={national_df['conv_25p4mm'].median():.0f}"
        )
    for p in [summary_path, national_path, monthly_path, seasonal_path, *map_paths]:
        print(f"  {p}")


if __name__ == "__main__":
    main()
