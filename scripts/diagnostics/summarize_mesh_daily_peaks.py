#!/usr/bin/env python3
"""
Scan mesh_0.05deg convective-day GeoTIFFs (12 UTC → 12 UTC labels), read
MAX_MESH75_MM tags (or raster max), write mesh_daily_peaks.csv, percentile
summary, and ECDF comparison plots.

When ``mesh_0.05deg_corrected/`` exists (Stage 05 output), also writes paired
raw-vs-calibrated peaks, percentiles, and ECDF figure.

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
CORRECTED_DIR = REPO / "data" / "historical" / "mesh_0.05deg_corrected"
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
CALIBRATION_LINE_STYLES = {
    "raw": {"ls": "--", "lw": 1.6, "alpha": 0.9},
    "calibrated": {"ls": "-", "lw": 2.0, "alpha": 1.0},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize daily max hail from mesh GeoTIFFs.")
    p.add_argument("--mesh-dir", type=Path, default=MESH_DIR)
    p.add_argument(
        "--corrected-dir",
        type=Path,
        default=CORRECTED_DIR,
        help="Stage 05 corrected rasters (paired ECDF when present)",
    )
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--min-date", type=str, default=None, help="YYYY-MM-DD inclusive")
    p.add_argument("--max-date", type=str, default=None, help="YYYY-MM-DD inclusive")
    p.add_argument(
        "--all-days",
        action="store_true",
        help="Include zero-hail days in ECDFs (default: hail days only)",
    )
    p.add_argument(
        "--skip-calibration",
        action="store_true",
        help="Skip raw-vs-calibrated comparison even if corrected dir exists",
    )
    return p.parse_args()


def classify_source(day: date) -> str:
    if day >= MRMS_START:
        return "MRMS"
    if GRIDRAD_START <= day <= GRIDRAD_END:
        return "GridRad"
    return "MYRORSS"


def peak_from_tif(path: Path, *, prefer_tags: bool = True) -> tuple[float, int, str]:
    with rasterio.open(path) as src:
        tags = src.tags() or {}
        if prefer_tags and "MAX_MESH75_MM" in tags:
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


def corrected_path_for_day(corrected_dir: Path, day: date) -> Path:
    return corrected_dir / str(day.year) / f"mesh_{day.strftime('%Y%m%d')}.tif"


def scan_mesh_peaks(
    mesh_dir: Path,
    *,
    d_min: date | None,
    d_max: date | None,
    prefer_tags: bool = True,
) -> pd.DataFrame:
    rows = []
    for day, path in iter_mesh_tifs(mesh_dir, d_min, d_max):
        try:
            peak_mm, active, tag_src = peak_from_tif(path, prefer_tags=prefer_tags)
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
            "path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date")


def build_calibration_peaks_df(
    raw_df: pd.DataFrame,
    corrected_dir: Path,
) -> pd.DataFrame:
    """Pair each raw daily peak with the Stage 05 corrected peak (same date)."""
    rows = []
    for rec in raw_df.itertuples(index=False):
        day = rec.date
        corr_path = corrected_path_for_day(corrected_dir, day)
        if not corr_path.exists():
            continue
        try:
            peak_cal, active_cal, tag_src = peak_from_tif(corr_path, prefer_tags=False)
        except Exception as e:
            print(f"WARN skip corrected {corr_path}: {e}")
            continue
        peak_raw = float(rec.peak_mm)
        rows.append({
            "date": day,
            "month": day.month,
            "source": rec.source,
            "peak_raw_mm": peak_raw,
            "peak_cal_mm": peak_cal,
            "delta_mm": peak_cal - peak_raw,
            "ratio": (peak_cal / peak_raw) if peak_raw > 0 else np.nan,
            "active_cells_raw": int(rec.active_cells),
            "active_cells_cal": active_cal,
            "raw_path": rec.path,
            "cal_path": (
                str(corr_path.relative_to(REPO))
                if corr_path.is_relative_to(REPO)
                else str(corr_path)
            ),
            "tag_source_cal": tag_src,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date")


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


def build_calibration_percentile_table(
    cal_df: pd.DataFrame,
    *,
    subset: str,
) -> pd.DataFrame:
    rows = []
    for src in SOURCE_ORDER:
        sub = cal_df[cal_df["source"] == src]
        if sub.empty:
            continue
        hail = sub[sub["peak_raw_mm"] > 0]
        raw = hail["peak_raw_mm"]
        cal = hail["peak_cal_mm"]
        rows.append({
            "subset": subset,
            "source": src,
            "n_days": len(sub),
            "n_hail_days": len(hail),
            "mean_raw_mm": float(raw.mean()) if len(raw) else 0.0,
            "mean_cal_mm": float(cal.mean()) if len(cal) else 0.0,
            "max_raw_mm": float(sub["peak_raw_mm"].max()),
            "max_cal_mm": float(sub["peak_cal_mm"].max()),
            **{
                f"p{p}_raw_mm": float(np.percentile(raw, p)) if len(raw) else 0.0
                for p in PERCENTILES
            },
            **{
                f"p{p}_cal_mm": float(np.percentile(cal, p)) if len(cal) else 0.0
                for p in PERCENTILES
            },
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


def plot_calibration_ecdf_panel(
    ax: plt.Axes,
    cal_df: pd.DataFrame,
    *,
    title: str,
    hail_only: bool,
) -> None:
    """Overlay uncalibrated (dashed) and Stage 05 calibrated (solid) ECDFs by era."""
    plot_df = cal_df[cal_df["peak_raw_mm"] > 0] if hail_only else cal_df
    if plot_df.empty:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No paired peaks", ha="center", va="center", transform=ax.transAxes)
        return

    x_max = min(
        320.0,
        float(max(plot_df["peak_raw_mm"].max(), plot_df["peak_cal_mm"].max())) * 1.02,
    )

    for src in SOURCE_ORDER:
        sub = plot_df.loc[plot_df["source"] == src]
        if sub.empty:
            continue
        color = SOURCE_STYLES[src]["color"]
        era = SOURCE_STYLES[src]["label"]

        raw_vals = np.sort(sub["peak_raw_mm"].to_numpy())
        if raw_vals.size:
            y_raw = np.arange(1, raw_vals.size + 1) / raw_vals.size
            ax.step(
                raw_vals,
                y_raw,
                where="post",
                color=color,
                label=f"{era} raw (n={raw_vals.size:,})",
                **CALIBRATION_LINE_STYLES["raw"],
            )

        cal_vals = np.sort(sub.loc[sub["peak_cal_mm"] > 0, "peak_cal_mm"].to_numpy())
        if cal_vals.size:
            y_cal = np.arange(1, cal_vals.size + 1) / cal_vals.size
            ax.step(
                cal_vals,
                y_cal,
                where="post",
                color=color,
                label=f"{era} Stage 05 (n={cal_vals.size:,})",
                **CALIBRATION_LINE_STYLES["calibrated"],
            )

    ax.axvline(25.4, color="black", ls=":", lw=1, alpha=0.55)
    ax.text(25.4, 0.02, "1 in", fontsize=8, rotation=90, va="bottom")
    ax.set_xlim(0, x_max)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("Daily max hail in raster (mm)")
    ax.set_ylabel("Fraction of days ≤ x")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=6)
    ax.grid(True, alpha=0.25)


def write_calibration_outputs(
    cal_df: pd.DataFrame,
    out_dir: Path,
    *,
    hail_only: bool,
) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "mesh_calibration_peaks.csv"
    cal_df.to_csv(csv_path, index=False)

    pct_frames = [
        build_calibration_percentile_table(cal_df, subset="all_months"),
        build_calibration_percentile_table(cal_df[cal_df["month"] == 5], subset="may_only"),
    ]
    pct_path = out_dir / "mesh_calibration_percentiles.csv"
    pd.concat(pct_frames, ignore_index=True).to_csv(pct_path, index=False)

    hail_note = "hail days only" if hail_only else "all days"
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    plot_calibration_ecdf_panel(
        axes[0],
        cal_df,
        title=f"Raw vs Stage 05 — full record ({hail_note})",
        hail_only=hail_only,
    )
    may = cal_df[cal_df["month"] == 5]
    plot_calibration_ecdf_panel(
        axes[1],
        may,
        title=f"Raw vs Stage 05 — May only ({hail_note})",
        hail_only=hail_only,
    )
    fig.suptitle(
        "Dashed = uncalibrated mesh_0.05deg; solid = mesh_0.05deg_corrected (Stage 05)",
        fontsize=9,
        y=1.02,
    )
    fig.tight_layout()
    fig_path = out_dir / "mesh_calibration_ecdf.png"
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return csv_path, pct_path, fig_path


def main() -> None:
    args = parse_args()
    d_min = datetime.strptime(args.min_date, "%Y-%m-%d").date() if args.min_date else None
    d_max = datetime.strptime(args.max_date, "%Y-%m-%d").date() if args.max_date else None
    hail_only = not args.all_days

    df = scan_mesh_peaks(args.mesh_dir, d_min=d_min, d_max=d_max, prefer_tags=True)
    if df.empty:
        print(f"No mesh TIFFs found under {args.mesh_dir}")
        return

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

    cal_paths: list[Path] = []
    if not args.skip_calibration and args.corrected_dir.is_dir():
        cal_df = build_calibration_peaks_df(df, args.corrected_dir)
        if cal_df.empty:
            print(f"\nNo paired corrected TIFFs under {args.corrected_dir}")
        else:
            cal_csv, cal_pct, cal_fig = write_calibration_outputs(
                cal_df, args.out_dir, hail_only=hail_only
            )
            cal_paths = [cal_csv, cal_pct, cal_fig]

    print(f"Scanned {len(df):,} daily TIFFs")
    print(f"  Date range: {df['date'].min()} → {df['date'].max()}")
    print(f"  By source: {df['source'].value_counts().to_dict()}")
    print(f"  Global max daily peak: {df['peak_mm'].max():.1f} mm")
    print(f"\nWrote:\n  {csv_path}\n  {pct_path}\n  {fig_path}")
    if cal_paths:
        print(f"\nCalibration comparison ({len(cal_df):,} paired days):")
        for p in cal_paths:
            print(f"  {p}")
        print("\n--- Calibration percentiles (mm, all months, hail days) ---")
        print(
            build_calibration_percentile_table(cal_df, subset="all_months").to_string(
                index=False
            )
        )
    print("\n--- Percentiles (mm, all months, hail days) ---")
    print(pct_frames[0].to_string(index=False))


if __name__ == "__main__":
    main()
