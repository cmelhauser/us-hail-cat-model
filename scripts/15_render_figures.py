#!/usr/bin/env python3
"""
15_render_figures.py — Render All Figures + Validation Report
==============================================================
Generates all diagnostic and output figures for the hail cat model.

Figure Categories
-----------------
  docs/figures/historical/
    - Historical return period maps (from stage 09/10 analytical CDFs)
    - Daily climatology seasonal map
    - Event catalog summary charts

  docs/figures/stochastic/
    - Stochastic return period maps (from stage 13 empirical)
    - EP curves (OEP + AEP)
    - PET bar charts

  docs/figures/analysis/
    - Analytical vs stochastic RP comparison
    - Validation diagnostics (from stage 06)
    - Vulnerability curves (from stage 14)
    - Regional GPD parameter maps

Input
-----
  data/analysis/cdf/rp_*yr_hail_smooth.tif
  data/stochastic/maps/rp_*yr_stochastic.tif
  data/stochastic/pet/pet_*.csv
  data/historical/events/event_catalog.csv
  data/analysis/cdf/cdf_parameters.npz
  data/analysis/occurrence/p_occ_*.tif

Output
------
  docs/figures/historical/*.png
  docs/figures/stochastic/*.png
  docs/figures/analysis/*.png

Usage
-----
  python scripts/15_render_figures.py
  python scripts/15_render_figures.py --maps-only
  python scripts/15_render_figures.py --validate
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
CDF_DIR   = DATA_ROOT / "analysis" / "cdf"
STOCH_DIR = DATA_ROOT / "stochastic"
EVENT_DIR = DATA_ROOT / "historical" / "events"
OCC_DIR   = DATA_ROOT / "analysis" / "occurrence"
PET_DIR   = STOCH_DIR / "pet"

FIG_HIST  = REPO_ROOT / "docs" / "figures" / "historical"
FIG_STOCH = REPO_ROOT / "docs" / "figures" / "stochastic"
FIG_ANAL  = REPO_ROOT / "docs" / "figures" / "analysis"

LOG_DIR   = REPO_ROOT / "logs"
LOG_FILE  = LOG_DIR / "15_render_figures.log"

NROWS = 520
NCOLS = 1180
DX    = 0.05
LAT_MAX = 50.005
LON_MIN = -125.005

RP_YEARS = [10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def setup_matplotlib():
    """Configure matplotlib for headless rendering with cartopy."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 10,
    })
    return plt


def render_rp_map(tif_path, out_path, title, vmax=None):
    """Render a return period or occurrence probability map with CONUS outline."""
    import rasterio
    plt = setup_matplotlib()

    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        has_cartopy = True
    except ImportError:
        has_cartopy = False

    with rasterio.open(tif_path) as src:
        data = src.read(1)
        extent = [src.bounds.left, src.bounds.right,
                  src.bounds.bottom, src.bounds.top]

    data_inches = data / 25.4  # convert mm to inches for display
    data_inches[data_inches <= 0] = np.nan

    if has_cartopy:
        fig, ax = plt.subplots(figsize=(14, 8),
                                subplot_kw={"projection": ccrs.LambertConformal()})
        ax.set_extent([-125, -66, 24, 50], crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.STATES, linewidth=0.3, edgecolor="gray")
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        im = ax.pcolormesh(
            np.linspace(extent[0], extent[1], data.shape[1]),
            np.linspace(extent[3], extent[2], data.shape[0]),
            data_inches,
            transform=ccrs.PlateCarree(),
            cmap="YlOrRd",
            vmin=0,
            vmax=vmax or float(np.nanpercentile(data_inches, 99)),
            shading="auto",
        )
    else:
        fig, ax = plt.subplots(figsize=(14, 8))
        im = ax.imshow(data_inches, extent=extent, origin="upper",
                        cmap="YlOrRd", vmin=0,
                        vmax=vmax or float(np.nanpercentile(data_inches, 99)))

    plt.colorbar(im, ax=ax, label="Hail Size (inches)", shrink=0.6)
    ax.set_title(title)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close()
    log(f"    {out_path.name}")


def render_historical_maps():
    """Render analytical RP maps from stage 09/10."""
    log("\n  [Historical RP Maps]")
    for rp in RP_YEARS:
        tif = CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif"
        if tif.exists():
            render_rp_map(tif, FIG_HIST / f"rp_{rp:05d}yr_analytical.png",
                          f"Analytical {rp:,}-Year Return Period Hail (MESH75)")


def render_stochastic_maps():
    """Render empirical RP maps from stage 13."""
    log("\n  [Stochastic RP Maps]")
    stoch_maps = STOCH_DIR / "maps"
    for rp in RP_YEARS:
        tif = stoch_maps / f"rp_{rp:05d}yr_stochastic.tif"
        if tif.exists():
            render_rp_map(tif, FIG_STOCH / f"rp_{rp:05d}yr_stochastic.png",
                          f"Stochastic {rp:,}-Year Return Period Hail (50K-yr catalog)")


def render_ep_curves():
    """Render OEP and AEP curves from PET tables."""
    plt = setup_matplotlib()
    log("\n  [EP Curves]")

    occ_path = PET_DIR / "pet_occurrence.csv"
    if not occ_path.exists():
        log("    Skipping — PET files not found")
        return

    import pandas as pd
    occ = pd.read_csv(occ_path)

    FIG_STOCH.mkdir(parents=True, exist_ok=True)

    # OEP curve
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.semilogy(occ["peak_hail_in"], occ["return_period_yr"], "o-", color="#1565c0", linewidth=2)
    ax.set_xlabel("Peak Hail Size (inches)")
    ax.set_ylabel("Return Period (years)")
    ax.set_title("Occurrence Exceedance Probability (OEP) — Peak Hail")
    ax.grid(True, alpha=0.3, which="both")
    ax.set_ylim(1, 100000)
    fig.savefig(FIG_STOCH / "oep_curve.png")
    plt.close()
    log(f"    oep_curve.png")


def render_analytical_vs_stochastic():
    """Compare analytical (stage 09/10) vs stochastic (stage 13) RPs."""
    plt = setup_matplotlib()
    log("\n  [Analytical vs Stochastic Comparison]")

    import rasterio

    rps_to_compare = [100, 500, 1000, 10000]
    data_pairs = []

    for rp in rps_to_compare:
        anal = CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif"
        stoch = STOCH_DIR / "maps" / f"rp_{rp:05d}yr_stochastic.tif"
        if anal.exists() and stoch.exists():
            with rasterio.open(anal) as s1:
                d1 = s1.read(1).flatten()
            with rasterio.open(stoch) as s2:
                d2 = s2.read(1).flatten()
            mask = (d1 > 0) & (d2 > 0)
            if mask.sum() > 100:
                data_pairs.append((rp, d1[mask] / 25.4, d2[mask] / 25.4))

    if not data_pairs:
        log("    Skipping — insufficient data for comparison")
        return

    FIG_ANAL.mkdir(parents=True, exist_ok=True)
    n = len(data_pairs)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 5))
    if n == 1:
        axes = [axes]

    for ax, (rp, anal, stoch) in zip(axes, data_pairs):
        ax.hexbin(anal, stoch, gridsize=40, cmap="YlOrRd", mincnt=1)
        lim = max(anal.max(), stoch.max()) * 1.1
        ax.plot([0, lim], [0, lim], "k--", alpha=0.5)
        ax.set_xlabel("Analytical (inches)")
        ax.set_ylabel("Stochastic (inches)")
        ax.set_title(f"{rp:,}-yr RP")
        ax.set_xlim(0, lim)
        ax.set_ylim(0, lim)

    fig.suptitle("Analytical vs Stochastic Return Period Comparison")
    fig.savefig(FIG_ANAL / "analytical_vs_stochastic_rp.png")
    plt.close()
    log(f"    analytical_vs_stochastic_rp.png")


def render_event_summary():
    """Render event catalog summary charts."""
    plt = setup_matplotlib()
    log("\n  [Event Summary]")

    cat_path = EVENT_DIR / "event_catalog.csv"
    if not cat_path.exists():
        log("    Skipping — event catalog not found")
        return

    import pandas as pd
    df = pd.read_csv(cat_path, parse_dates=["start_date"])

    FIG_HIST.mkdir(parents=True, exist_ok=True)

    # Annual event counts
    annual = df.groupby(df["start_date"].dt.year).size()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(annual.index, annual.values, color="#1565c0")
    ax.set_xlabel("Year")
    ax.set_ylabel("Events")
    ax.set_title("Annual Hail Event Count")
    fig.savefig(FIG_HIST / "annual_event_counts.png")
    plt.close()

    # Monthly distribution
    monthly = df.groupby(df["start_date"].dt.month).size()
    fig, ax = plt.subplots(figsize=(10, 5))
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ax.bar(months, [monthly.get(m, 0) for m in range(1, 13)], color="#43a047")
    ax.set_ylabel("Events")
    ax.set_title("Monthly Hail Event Distribution")
    fig.savefig(FIG_HIST / "monthly_event_distribution.png")
    plt.close()

    log(f"    annual_event_counts.png, monthly_event_distribution.png")


def validate_outputs() -> bool:
    errors = []
    for d in [FIG_HIST, FIG_STOCH, FIG_ANAL]:
        pngs = list(d.glob("*.png")) if d.exists() else []
        if not pngs:
            errors.append(f"No figures in {d.relative_to(REPO_ROOT)}")

    if errors:
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True


def main():
    parser = argparse.ArgumentParser(description="Render all figures.")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--maps-only", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  Figure Renderer — Stage 15")
    log(f"{'='*60}")

    t0 = time.time()

    log("\n[1/5] Historical maps")
    render_historical_maps()

    log("\n[2/5] Stochastic maps")
    render_stochastic_maps()

    if not args.maps_only:
        log("\n[3/5] EP curves")
        render_ep_curves()

        log("\n[4/5] Analytical vs stochastic comparison")
        render_analytical_vs_stochastic()

        log("\n[5/5] Event summary charts")
        render_event_summary()

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/60:.1f} min")
    log(f"{'='*60}\n")

    ok = validate_outputs()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
