#!/usr/bin/env python3
"""
Scan mesh_0.05deg daily GeoTIFFs, read MAX_MESH75_MM tags (or raster max),
write mesh_daily_peaks.csv, percentile summary, and ECDF comparison plots.

Usage (from repo root):
  .venv/bin/python scripts/diagnostics/summarize_mesh_daily_peaks.py
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

REPO = Path(__file__).resolve().parents[2]
MESH_DIR = REPO / "data" / "historical" / "mesh_0.05deg"
OUT_DIR = REPO / "data" / "analysis" / "mesh_daily_peaks"
MESH_RE = re.compile(r"mesh_(\d{8})\.tif$")

MRMS_START = date(2020, 10, 14)
GRIDRAD_START = date(2012, 1, 1)
GRIDRAD_END = date(2020, 10, 13)

SOURCE_ORDER = ("MYRORSS", "GridRad", "MRMS")
SOURCE_STYLES = {
    "MYRORSS": {"color": "#2c7bb6", "label": "MYRORSS (1998–2011)"},
    "GridRad": {"color": "#d7191c", "label": "GridRad gap-fill (2012–2020-10-13)"},
    "MRMS": {"color": "#1a9641", "label": "MRMS (2020-10-14–present)"},
}

PERCENTILES = (50, 75, 90, 95, 99)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize daily max hail from mesh GeoTIFFs.")
    p.add_argument("--mesh-dir", type=Path, default=MESH_DIR)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--min-date", type=str, default=None, help="YYYY-MM-DD inclusive")
    p.add_argument("--max-date", type=str, default=None, help="YYYY-MM-DD inclusive")
    p.add_argument(
        "--all-days",
        action="store_true",
        help="Include zero-hail days in ECDFs (default: hail days only)",
    )
    return p.parse_args()


def classify_source(day: date) -> str:
    if day >= MRMS_START:
        return "MRMS"
    if GRIDRAD_START <= day <= GRIDRAD_END:
        return "GridRad"
    return "MYRORSS"


def peak_from_tif(path: Path) -> tuple[float, int, str]:
    with rasterio.open(path) as src:
        tags = src.tags() or {}
        if "MAX_MESH75_MM" in tags:
            peak = float(tags["MAX_MESH75_MM"])
            active = int(tags.get("ACTIVE_CELLS", 0))
            return peak, active, "tag"
        data = src.read(1)
    active = data[(data > 0) & np.isfinite(data)]
    return (
        float(active.max()) if active.size else 0.0,
        int(active.size),
        "raster",
    )


def iter_mesh_tifs(mesh_dir: Path, d_min: date | None, d_max: date | None):
    for path in sorted(mesh_dir.rglob("mesh_????????.tif")):
        m = MESH_RE.search(path.name)
        if not m:
            continue
        day = datetime.strptime(m.group(1), "%Y%m%d").date()
        if d_min and day < d_min:
            continue
        if d_max and day > d_max:
            continue
        yield day, path


def build_percentile_table(df: pd.DataFrame, *, subset: str) -> pd.DataFrame:
    rows = []
    for src in SOURCE_ORDER:
        sub = df[df["source"] == src]
        if sub.empty:
            continue
        hail = sub[sub["peak_mm"] > 0]["peak_mm"]
        rows.append({
            "subset": subset,
            "source": src,
            "n_days": len(sub),
            "n_hail_days": len(hail),
            "mean_mm": float(hail.mean()) if len(hail) else 0.0,
            "max_mm": float(sub["peak_mm"].max()),
            **{f"p{p}_mm": float(np.percentile(hail, p)) if len(hail) else 0.0 for p in PERCENTILES},
        })
    return pd.DataFrame(rows)


def plot_ecdf_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    *,
    title: str,
    hail_only: bool,
) -> None:
    plot_df = df[df["peak_mm"] > 0] if hail_only else df
    x_max = min(320.0, float(plot_df["peak_mm"].max()) * 1.02) if len(plot_df) else 100.0

    for src in SOURCE_ORDER:
        vals = np.sort(plot_df.loc[plot_df["source"] == src, "peak_mm"].to_numpy())
        if vals.size == 0:
            continue
        y = np.arange(1, vals.size + 1) / vals.size
        style = SOURCE_STYLES[src]
        ax.step(
            vals,
            y,
            where="post",
            color=style["color"],
            linewidth=1.8,
            label=f"{style['label']} (n={vals.size:,})",
        )

    ax.axvline(25.4, color="black", ls="--", lw=1, alpha=0.55)
    ax.text(25.4, 0.02, "1 in", fontsize=8, rotation=90, va="bottom")
    ax.set_xlim(0, x_max)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("Daily max hail in raster (mm)")
    ax.set_ylabel("Fraction of days ≤ x")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=7)
    ax.grid(True, alpha=0.25)


def main() -> None:
    args = parse_args()
    d_min = datetime.strptime(args.min_date, "%Y-%m-%d").date() if args.min_date else None
    d_max = datetime.strptime(args.max_date, "%Y-%m-%d").date() if args.max_date else None
    hail_only = not args.all_days

    rows = []
    for day, path in iter_mesh_tifs(args.mesh_dir, d_min, d_max):
        try:
            peak_mm, active, tag_src = peak_from_tif(path)
        except Exception as e:
            print(f"WARN skip {path}: {e}")
            continue
        rows.append({
            "date": day,
            "month": day.month,
            "source": classify_source(day),
            "peak_mm": peak_mm,
            "peak_in": peak_mm / 25.4,
            "active_cells": active,
            "tag_source": tag_src,
            "path": str(path.relative_to(REPO)),
        })

    if not rows:
        print(f"No mesh TIFFs found under {args.mesh_dir}")
        return

    df = pd.DataFrame(rows).sort_values("date")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.out_dir / "mesh_daily_peaks.csv"
    df.to_csv(csv_path, index=False)

    pct_frames = [
        build_percentile_table(df, subset="all_months"),
        build_percentile_table(df[df["month"] == 5], subset="may_only"),
    ]
    pct_path = args.out_dir / "mesh_daily_peak_percentiles.csv"
    pd.concat(pct_frames, ignore_index=True).to_csv(pct_path, index=False)

    hail_note = "hail days only" if hail_only else "all days"
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    plot_ecdf_panel(
        axes[0],
        df,
        title=f"Daily peak ECDF — full record ({hail_note})",
        hail_only=hail_only,
    )
    may = df[df["month"] == 5]
    plot_ecdf_panel(
        axes[1],
        may,
        title=f"Daily peak ECDF — May only ({hail_note})",
        hail_only=hail_only,
    )
    fig.suptitle(
        "Compare radar eras by fraction of days, not raw counts "
        "(MYRORSS/MRMS = MESH mm; GridRad = MESH75)",
        fontsize=9,
        y=1.02,
    )
    fig.tight_layout()
    fig_path = args.out_dir / "mesh_daily_peak_ecdf.png"
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    old_hist = args.out_dir / "mesh_daily_peak_distribution.png"
    if old_hist.exists():
        old_hist.unlink()

    print(f"Scanned {len(df):,} daily TIFFs")
    print(f"  Date range: {df['date'].min()} → {df['date'].max()}")
    print(f"  By source: {df['source'].value_counts().to_dict()}")
    print(f"  Global max daily peak: {df['peak_mm'].max():.1f} mm")
    print(f"\nWrote:\n  {csv_path}\n  {pct_path}\n  {fig_path}")
    print("\n--- Percentiles (mm, all months, hail days) ---")
    print(pct_frames[0].to_string(index=False))


if __name__ == "__main__":
    main()
