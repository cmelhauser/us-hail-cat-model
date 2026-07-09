#!/usr/bin/env python3
"""
Render PNAS manuscript figures and a metrics summary from completed pipeline outputs.

Reads manifests, mesh daily peaks, hail-day climatology, validation, event catalog,
and analytical return-period maps. Writes PNGs to docs/figures/pnas/ and a JSON
metrics file for manuscript insertion.

Usage (repo root):
  .venv/bin/python scripts/diagnostics/render_pnas_article_figures.py
"""

from __future__ import annotations

import json
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

from scripts._config import MODEL_VERSION, RP_MAP_CBAR_VMAX_IN
from scripts._mapping import (
    create_conus_axes,
    load_conus_raster_for_map,
    plot_raster_on_axis,
    save_conus_map_from_tif,
    save_conus_raster_map,
)
from scripts.diagnostics._diagnostic_io import warn_skip

MESH_DIR = REPO / "data" / "historical" / "mesh_0.05deg"
CORRECTED_DIR = REPO / "data" / "historical" / "mesh_0.05deg_corrected"
OUT_FIG = REPO / "docs" / "figures" / "pnas"
OUT_METRICS = REPO / "data" / "analysis" / "pnas_article_metrics.json"
MASK_TIF = REPO / "data" / "analysis" / "conus_mask" / "conus_mask.tif"
STOCH_MAP_DIR = REPO / "data" / "stochastic" / "maps"

MANIFESTS = {
    "MYRORSS": MESH_DIR / "manifest_stage01_myrorss.csv",
    "GridRad": MESH_DIR / "manifest_stage04c_gridrad.csv",
    "MRMS": MESH_DIR / "manifest_stage02_mrms.csv",
}
PEAKS_CSV = REPO / "data" / "analysis" / "mesh_daily_peaks" / "mesh_daily_peaks.csv"
CAL_PEAKS_CSV = REPO / "data" / "analysis" / "mesh_daily_peaks" / "mesh_calibration_peaks.csv"
HAIL_CLIM_DIR = REPO / "data" / "analysis" / "hail_day_climatology"
VALID_DIR = REPO / "data" / "historical" / "validation"
EVENT_CSV = REPO / "data" / "historical" / "events" / "event_catalog.csv"
CDF_DIR = REPO / "data" / "analysis" / "cdf"

MRMS_START = date(2020, 10, 14)
GRIDRAD_START = date(2012, 1, 1)
GRIDRAD_END = date(2020, 10, 13)

SOURCE_COLORS = {
    "MYRORSS": "#2c7bb6",
    "GridRad": "#d7191c",
    "MRMS": "#1a9641",
}
STATUS_COLORS = {
    "ok": "#1a9641",
    "ok_with_read_errors": "#a6d96a",
    "no_hail_pixels": "#ffffbf",
    "missing_source": "#d7191c",
    "error": "#7b3294",
}


def setup_plt():
    plt.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 10,
    })


def run_figure(step: str, fn, *args, default=None, **kwargs):
    """Run one figure step; warn and skip when inputs are missing."""
    try:
        return fn(*args, **kwargs)
    except FileNotFoundError as exc:
        warn_skip(step, str(exc))
        return default
    except OSError as exc:
        warn_skip(step, str(exc))
        return default


def classify_source(day: date) -> str:
    if day >= MRMS_START:
        return "MRMS"
    if GRIDRAD_START <= day <= GRIDRAD_END:
        return "GridRad"
    return "MYRORSS"


def load_manifest(path: Path, source: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["source"] = source
    return df


def fig_data_source_timeline(out: Path) -> None:
    """Figure 1: radar-era timeline and splice dates."""
    fig, ax = plt.subplots(figsize=(10, 2.2))
    eras = [
        ("MYRORSS", 1998.25, 2011.99, "1998–2011"),
        ("GridRad gap-fill", 2012.0, 2020.72, "2012–2020-10-13"),
        ("MRMS", 2020.73, 2026.5, "2020-10-14–present"),
    ]
    for i, (name, x0, x1, label) in enumerate(eras):
        color = SOURCE_COLORS.get(name.split()[0], "#888888")
        ax.barh(0, x1 - x0, left=x0, height=0.5, color=color, alpha=0.85, label=name)
        ax.text((x0 + x1) / 2, 0, label, ha="center", va="center", fontsize=9, color="white", fontweight="bold")
    ax.axvline(2012.0, color="k", ls="--", lw=0.8, alpha=0.5)
    ax.axvline(2020 + 287 / 365.25, color="k", ls="--", lw=0.8, alpha=0.5)
    ax.set_yticks([])
    ax.set_xlim(1998, 2026.6)
    ax.set_xlabel("Year")
    ax.set_title("Radar data sources (convective-day MESH archive)")
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_manifest_coverage(manifests: dict[str, Path], out: Path) -> pd.DataFrame:
    """Figure 2: stacked manifest status by year."""
    available = {s: p for s, p in manifests.items() if p.is_file()}
    if not available:
        warn_skip("fig02_manifest_coverage", "no manifest CSVs found")
        return pd.DataFrame()
    frames = [load_manifest(p, s) for s, p in available.items()]
    all_df = pd.concat(frames, ignore_index=True)
    pivot = (
        all_df.groupby(["year", "status"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    statuses = [s for s in STATUS_COLORS if s in pivot.columns]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    bottom = np.zeros(len(pivot))
    years = pivot.index.to_numpy()
    for status in statuses:
        vals = pivot[status].to_numpy()
        ax.bar(years, vals, bottom=bottom, label=status, color=STATUS_COLORS[status], width=0.85)
        bottom += vals
    ax.set_xlabel("Year")
    ax.set_ylabel("Convective days")
    ax.set_title("Source-coverage manifest status by year")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return pivot


def fig_source_transition_peaks(out: Path) -> dict:
    """Figure 3: daily peak distributions at source splice windows (literature transition QA)."""
    if not PEAKS_CSV.is_file():
        warn_skip("fig03_source_transition", f"required file not found: {PEAKS_CSV}")
        return {}
    df = pd.read_csv(PEAKS_CSV, parse_dates=["date"])
    df["source"] = df["date"].apply(lambda d: classify_source(d.date()))
    df["year"] = df["date"].dt.year
    windows = {
        "MYRORSS→GridRad (2010–2013)": (2010, 2013),
        "GridRad core (2014–2017)": (2014, 2017),
        "GridRad→MRMS (2019–2022)": (2019, 2022),
    }
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    stats = {}
    for ax, (title, (y0, y1)) in zip(axes, windows.items()):
        sub = df[(df["year"] >= y0) & (df["year"] <= y1) & (df["peak_mm"] > 0)]
        for src in ("MYRORSS", "GridRad", "MRMS"):
            s = sub[sub["source"] == src]["peak_mm"]
            if s.empty:
                continue
            ax.hist(
                s,
                bins=40,
                range=(0, 120),
                alpha=0.55,
                density=True,
                label=f"{src} (n={len(s):,})",
                color=SOURCE_COLORS[src],
            )
            stats[f"{title}:{src}"] = {
                "n_hail_days": int(len(s)),
                "median_mm": round(float(s.median()), 1),
                "p95_mm": round(float(s.quantile(0.95)), 1),
            }
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("Daily CONUS peak MESH (mm)")
        ax.legend(fontsize=7)
    axes[0].set_ylabel("Density")
    fig.suptitle("Source-transition diagnostic: daily peak hail distributions", y=1.02)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return stats


def fig_calibration_ecdf(out: Path) -> dict:
    """Figure 4: raw vs era-pooled calibrated daily peaks by source."""
    if not CAL_PEAKS_CSV.exists():
        warn_skip("fig04_calibration_ecdf", f"required file not found: {CAL_PEAKS_CSV}")
        return {}
    df = pd.read_csv(CAL_PEAKS_CSV)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    stats = {}
    for src in ("MYRORSS", "GridRad", "MRMS"):
        sub = df[(df["source"] == src) & (df["peak_raw_mm"] > 0)]
        if sub.empty:
            continue
        raw = np.sort(sub["peak_raw_mm"].to_numpy())
        cal = np.sort(sub["peak_cal_mm"].to_numpy())
        y = np.linspace(0, 1, len(raw), endpoint=False)
        ax.plot(raw, y, ls="--", color=SOURCE_COLORS[src], alpha=0.7, label=f"{src} raw")
        ax.plot(cal, y, ls="-", color=SOURCE_COLORS[src], lw=2, label=f"{src} calibrated")
        stats[src] = {
            "median_raw_mm": round(float(np.median(raw)), 1),
            "median_cal_mm": round(float(np.median(cal)), 1),
            "p95_raw_mm": round(float(np.percentile(raw, 95)), 1),
            "p95_cal_mm": round(float(np.percentile(cal, 95)), 1),
        }
    ax.set_xlabel("Daily CONUS peak MESH (mm)")
    ax.set_ylabel("ECDF (hail days only)")
    ax.set_title("Era-pooled calibration: raw vs corrected MESH75 daily peaks")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return stats


def _mask_path() -> Path | None:
    return MASK_TIF if MASK_TIF.is_file() else None


def _render_rp_map_png(
    tif: Path,
    out: Path,
    *,
    title: str,
    inches: bool = True,
) -> bool:
    """Render a Lambert CONUS map from a model-grid GeoTIFF."""
    if not tif.is_file():
        return False
    preview = load_conus_raster_for_map(
        tif,
        mask_path=_mask_path(),
        scale=(1.0 / 25.4) if inches else 1.0,
        zero_to_nan=inches,
    )
    finite = preview[np.isfinite(preview)]
    if inches:
        vmax = RP_MAP_CBAR_VMAX_IN
        cbar_label = "Hail size (inches)"
    else:
        vmax = min(80.0, float(np.percentile(finite[finite > 0], 99)) if np.any(finite > 0) else 20.0)
        vmax = max(vmax, 1.0)
        cbar_label = "mm"
    save_conus_map_from_tif(
        tif,
        out,
        title=title,
        cbar_label=cbar_label,
        cmap="YlOrRd",
        vmin=0,
        vmax=vmax,
        mask_path=_mask_path(),
        scale=(1.0 / 25.4) if inches else 1.0,
        zero_to_nan=inches,
        figsize=(12, 6.5),
    )
    return True


def fig_seasonal_thresholds(out: Path) -> None:
    """Figure 5: national seasonal cycle by literature threshold (Cintineo/Wendt benchmark)."""
    monthly_path = HAIL_CLIM_DIR / "monthly_national_hail_days.csv"
    if not monthly_path.is_file():
        warn_skip("fig05_seasonal_thresholds", f"required file not found: {monthly_path}")
        return
    monthly = pd.read_csv(monthly_path)
    fig, ax = plt.subplots(figsize=(9, 4))
    months = list(range(1, 13))
    labels = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    dim = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for _, row in monthly.iterrows():
        per_day = [row[f"month_{m:02d}"] / dim[m - 1] for m in months]
        ax.plot(months, per_day, marker="o", ms=4, label=row["threshold_label"])
    ax.set_xticks(months)
    ax.set_xticklabels(labels)
    ax.set_ylabel("National any-cell hail days / calendar day")
    ax.set_title("Seasonal cycle by MESH75 threshold (corrected archive)")
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_hail_days_map(out: Path) -> None:
    """Figure 6: per-cell mean annual hail days at 29 mm skill threshold (Lambert)."""
    tif = HAIL_CLIM_DIR / "hail_days_per_year_skill_29mm.tif"
    if not tif.is_file():
        warn_skip("fig06_hail_days_map", f"required file not found: {tif}")
        return
    data = load_conus_raster_for_map(tif, mask_path=_mask_path())
    vmax = min(15.0, float(np.percentile(data[data > 0], 99)) if np.any(data > 0) else 5)
    save_conus_raster_map(
        data,
        out,
        title="Mean annual hail days — 29 mm skill threshold",
        cbar_label="days / year",
        cmap="YlOrRd",
        vmin=0,
        vmax=max(vmax, 1),
    )


def fig_validation_by_bin(out: Path) -> dict:
    """Figure 7: SPC validation bias and POD by report-size bin."""
    cal_path = VALID_DIR / "calibration_report.csv"
    if not cal_path.is_file():
        warn_skip("fig07_validation_by_bin", f"required file not found: {cal_path}")
        return {}
    cal = pd.read_csv(cal_path)
    cal = cal[cal["n"] > 0]
    fig, ax1 = plt.subplots(figsize=(7, 4))
    x = np.arange(len(cal))
    ax1.bar(x - 0.2, cal["bias_in"], width=0.4, label="Bias (MESH−SPC, in)", color="#2c7bb6")
    ax1.axhline(0, color="k", lw=0.6)
    ax1.set_ylabel("Bias (inches)")
    ax2 = ax1.twinx()
    ax2.bar(x + 0.2, cal["pod"], width=0.4, label="POD", color="#d7191c", alpha=0.8)
    ax2.set_ylabel("Probability of detection")
    ax2.set_ylim(0, 1)
    ax1.set_xticks(x)
    ax1.set_xticklabels(cal["bin"], rotation=25, ha="right", fontsize=8)
    ax1.set_title("MESH75 vs SPC hail reports by size bin")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    summary_path = VALID_DIR / "validation_summary.txt"
    text = summary_path.read_text() if summary_path.exists() else ""
    return {"validation_summary_excerpt": text[:800]}


def fig_rp_maps(out_100: Path, out_1000: Path) -> dict:
    """Figures 8–9: analytical return-period maps (Lambert Conformal)."""
    stats = {}
    for rp, out in ((100, out_100), (1000, out_1000)):
        tif = CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif"
        if _render_rp_map_png(
            tif,
            out,
            title=f"Analytical {rp:,}-year return period hail (MESH75)",
        ):
            with rasterio.open(tif) as s:
                d = s.read(1)
            pos = d[d > 0]
            stats[f"rp_{rp}yr"] = {
                "max_mm": round(float(pos.max()), 1),
                "p99_mm": round(float(np.percentile(pos, 99)), 1),
                "cells_ge_25mm": int((d >= 25.4).sum()),
            }
        else:
            warn_skip(f"fig_rp_{rp}", f"required file not found: {tif}")
    return stats


def fig_stochastic_rp(out: Path) -> None:
    """Figure 12: stochastic 100-year empirical return-period map (Lambert)."""
    tif = STOCH_MAP_DIR / "rp_00100yr_stochastic.tif"
    if not _render_rp_map_png(
        tif,
        out,
        title="Stochastic 100-year return period hail (50k-yr catalog)",
    ):
        warn_skip("fig12_stochastic_rp", f"required file not found: {tif}")


def fig_analytical_vs_stochastic(out: Path) -> None:
    """Figure 13: side-by-side 100-yr analytical vs stochastic Lambert maps."""
    anal_tif = CDF_DIR / "rp_00100yr_hail_smooth.tif"
    stoch_tif = STOCH_MAP_DIR / "rp_00100yr_stochastic.tif"
    if not anal_tif.is_file() or not stoch_tif.is_file():
        warn_skip(
            "fig13_analytical_vs_stochastic",
            f"missing RP GeoTIFFs ({anal_tif.name} / {stoch_tif.name})",
        )
        return

    panels = [
        (anal_tif, "Analytical 100-year RP"),
        (stoch_tif, "Stochastic 100-year RP"),
    ]
    preview = [
        load_conus_raster_for_map(
            tif,
            mask_path=_mask_path(),
            scale=1.0 / 25.4,
            zero_to_nan=True,
        )
        for tif, _ in panels
    ]
    vmax = RP_MAP_CBAR_VMAX_IN

    fig, axes = create_conus_axes(1, 2, figsize=(14, 5.5))
    ax_list = np.atleast_1d(axes).ravel()
    mappable = None
    for ax, (tif, title), data in zip(ax_list, panels, preview):
        mappable = plot_raster_on_axis(ax, data, cmap="YlOrRd", vmin=0, vmax=vmax)
        ax.set_title(title)
    if mappable is not None:
        fig.colorbar(mappable, ax=list(ax_list), label="Hail size (inches)", shrink=0.75)
    fig.suptitle("Analytical vs stochastic return period comparison", y=1.02)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)


def fig_event_dispersion(out: Path) -> dict:
    """Figure 10: annual event counts and index of dispersion (literature Poisson benchmark)."""
    if not EVENT_CSV.is_file():
        warn_skip("fig10_event_dispersion", f"required file not found: {EVENT_CSV}")
        return {}
    ec = pd.read_csv(EVENT_CSV, parse_dates=["start_date"])
    annual = ec.groupby(ec["start_date"].dt.year).size()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.bar(annual.index, annual.values, color="#2c7bb6", alpha=0.85)
    ax.axhline(annual.mean(), color="#d7191c", ls="--", label=f"Mean = {annual.mean():.0f} yr⁻¹")
    ax.set_xlabel("Year")
    ax.set_ylabel("Historical events (≥ 29 mm active cells)")
    ax.set_title("Annual sparse event counts (Stage 08)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    iod = float(annual.var() / annual.mean())
    return {
        "n_events": int(len(ec)),
        "mean_events_per_year": round(float(annual.mean()), 1),
        "std_events_per_year": round(float(annual.std()), 1),
        "index_of_dispersion": round(iod, 2),
    }


def fig_ai_workflow(out: Path) -> None:
    """Figure 11: human-directed AI development loop (schematic)."""
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis("off")
    boxes = [
        (0.2, 1.0, "Scientific\nintent", "#ffffcc"),
        (2.2, 1.0, "AI-assisted\nimplementation", "#cce5ff"),
        (4.4, 1.0, "Automated\nvalidation", "#d5f5e3"),
        (6.4, 1.0, "Human\nreview", "#fdebd0"),
        (8.2, 1.0, "Documented\npipeline", "#e8daef"),
    ]
    for i, (x, y, text, color) in enumerate(boxes):
        ax.add_patch(plt.Rectangle((x, y), 1.6, 1.0, fc=color, ec="k", lw=1))
        ax.text(x + 0.8, y + 0.5, text, ha="center", va="center", fontsize=9)
        if i < len(boxes) - 1:
            ax.annotate("", xy=(boxes[i + 1][0], 1.5), xytext=(x + 1.6, 1.5),
                        arrowprops=dict(arrowstyle="->", lw=1.2))
    ax.annotate("", xy=(0.2, 2.3), xytext=(9.8, 2.3),
                arrowprops=dict(arrowstyle="->", lw=1.0, connectionstyle="arc3,rad=-0.25"))
    ax.text(5, 2.55, "iterative hardening", ha="center", fontsize=8, style="italic")
    ax.set_title("Human-directed AI-assisted model construction loop")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def collect_metrics(manifest_pivot: pd.DataFrame, extra: dict) -> dict:
    """Assemble JSON metrics for manuscript insertion."""
    metrics: dict = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_version": MODEL_VERSION,
        **extra,
    }
    if CORRECTED_DIR.is_dir():
        metrics["total_daily_rasters"] = sum(1 for _ in CORRECTED_DIR.rglob("mesh_????????.tif"))
    for key, path in MANIFESTS.items():
        if not path.is_file():
            warn_skip(f"metrics_manifest_{key}", f"required file not found: {path}")
            continue
        m = load_manifest(path, key)
        metrics[f"{key.lower()}_days"] = int(len(m))
        if "manifest_status" not in metrics:
            metrics["manifest_status"] = {}
        metrics["manifest_status"][key.lower()] = m["status"].value_counts().to_dict()
        if key == "GridRad":
            metrics["gridrad_missing_source"] = int((m["status"] == "missing_source").sum())
    bench_path = HAIL_CLIM_DIR / "threshold_benchmark_summary.csv"
    nat_path = HAIL_CLIM_DIR / "national_annual_hail_days.csv"
    if bench_path.is_file() and nat_path.is_file():
        thresh = pd.read_csv(bench_path)
        t29 = thresh[thresh["threshold_key"] == "skill_29mm"]
        if not t29.empty:
            nat = pd.read_csv(nat_path)
            row = t29.iloc[0]
            metrics["hail_day_climatology_29mm"] = {
                "gp_max_days_per_year": float(row["gp_max_days_per_year"]),
                "gp_mean_days_per_year": float(row["gp_mean_days_per_year"]),
                "national_any_cell_days_per_year": round(float(nat["skill_29mm"].mean()), 1),
            }
    else:
        warn_skip("metrics_hail_day_climatology", "hail_day_climatology outputs missing")
    return metrics


def main() -> None:
    setup_plt()
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print("Rendering PNAS article figures →", OUT_FIG)

    manifest_pivot = run_figure(
        "fig02_manifest_coverage",
        fig_manifest_coverage,
        MANIFESTS,
        OUT_FIG / "fig02_manifest_coverage_by_year.png",
        default=pd.DataFrame(),
    )
    run_figure("fig01_data_source_timeline", fig_data_source_timeline, OUT_FIG / "fig01_data_source_timeline.png")
    transition = run_figure(
        "fig03_source_transition",
        fig_source_transition_peaks,
        OUT_FIG / "fig03_source_transition_daily_peaks.png",
        default={},
    )
    calibration = run_figure(
        "fig04_calibration_ecdf",
        fig_calibration_ecdf,
        OUT_FIG / "fig04_calibration_ecdf_by_source.png",
        default={},
    )
    run_figure("fig05_seasonal_thresholds", fig_seasonal_thresholds, OUT_FIG / "fig05_seasonal_national_hail_days.png")
    run_figure("fig06_hail_days_map", fig_hail_days_map, OUT_FIG / "fig06_hail_days_per_year_29mm.png")
    validation = run_figure(
        "fig07_validation_by_bin",
        fig_validation_by_bin,
        OUT_FIG / "fig07_validation_by_size_bin.png",
        default={},
    )
    rp_stats = run_figure(
        "fig08_09_rp_maps",
        fig_rp_maps,
        OUT_FIG / "fig08_rp_100yr_analytical.png",
        OUT_FIG / "fig09_rp_1000yr_analytical.png",
        default={},
    )
    events = run_figure(
        "fig10_event_dispersion",
        fig_event_dispersion,
        OUT_FIG / "fig10_annual_event_counts.png",
        default={},
    )
    run_figure("fig11_ai_workflow", fig_ai_workflow, OUT_FIG / "fig11_ai_development_workflow.png")
    run_figure("fig12_stochastic_rp", fig_stochastic_rp, OUT_FIG / "fig12_rp_100yr_stochastic.png")
    run_figure(
        "fig13_analytical_vs_stochastic",
        fig_analytical_vs_stochastic,
        OUT_FIG / "fig13_analytical_vs_stochastic.png",
    )

    # Stage 06 scatter (non-geographic; copy if present)
    scatter_src = REPO / "docs" / "figures" / "analysis" / "mesh_vs_spc_scatter.png"
    if scatter_src.exists():
        import shutil
        shutil.copy2(scatter_src, OUT_FIG / "fig07b_mesh_vs_spc_scatter.png")

    metrics = collect_metrics(
        manifest_pivot,
        {
            "source_transition": transition,
            "calibration_ecdf": calibration,
            "validation": validation,
            "return_period_maps": rp_stats,
            "event_catalog": events,
        },
    )
    OUT_METRICS.parent.mkdir(parents=True, exist_ok=True)
    OUT_METRICS.write_text(json.dumps(metrics, indent=2))
    print(f"Wrote {len(list(OUT_FIG.glob('*.png')))} figures in {time.time()-t0:.1f}s")
    print("Metrics →", OUT_METRICS)

    try:
        from scripts.diagnostics.render_pnas_publication_md import main as render_publication_md

        render_publication_md()
    except Exception as exc:
        warn_skip("render_pnas_publication_md", str(exc))


if __name__ == "__main__":
    main()
