#!/usr/bin/env python3
"""
09_fit_cdf_regional.py — CDF Fitting with Regional GPD ξ Pooling
==================================================================
Fits per-cell frequency-severity distributions to the corrected MESH75
record. Uses a zero-inflated two-component model:

  1. Occurrence probability p_occ = fraction of years with hail ≥ threshold
  2. Body: Lognormal distribution (L-moment fit) for hail sizes below the
     GPD splice point
  3. Tail: Generalized Pareto Distribution (GPD) for exceedances above the
     splice point, with REGIONAL shape parameter ξ pooling

Regional GPD ξ Pooling (Hosking & Wallis 1997)
-----------------------------------------------
The key innovation over v1.0: instead of fitting GPD independently at each
cell (which fails when n_exceedances < 10), we:

  1. Cluster cells into climatologically homogeneous regions using K-means
     on (mean_hail, p_occ, latitude, longitude)
  2. Pool all exceedances within each region to estimate a shared ξ using
     L-moment ratios (stable with pooled sample sizes of hundreds)
  3. Fit cell-specific scale σ conditional on the regional ξ

This eliminates most of the 88 empirical-fallback cells from v1.0.

MRL Diagnostics
---------------
Mean Residual Life plots are computed per region to validate the GPD
splice point. If GPD is appropriate above threshold u, MRL(u) should
be approximately linear.

Return Periods
--------------
For each cell, the composite CDF is inverted to produce hail sizes at
return periods from 10 to 50,000 years. Short RPs (10–500 yr) are well
constrained by the fitted CDF. Long RPs (1,000–50,000 yr) are deep GPD
extrapolation and carry significant uncertainty — they should be compared
against empirical return periods from the 50,000-year stochastic catalog
(stage 13) as a cross-check. Divergence between analytical and stochastic
long-RP estimates flags cells where the GPD tail may be misspecified.

Input
-----
  data/historical/events/event_catalog.csv
  data/historical/events/event_peaks.npz
  data/historical/mesh_0.05deg_corrected/ (for annual max computation)

Output
------
  data/analysis/cdf/cdf_parameters.npz
      p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold,
      region_assignments, region_xi_values

  data/analysis/cdf/rp_YYYYYyr_hail.tif (11 GeoTIFFs: 10–50000 yr)
      Short RPs (10–500 yr): well-constrained by fitted CDF
      Long RPs (1000–50000 yr): GPD extrapolation, compare vs stochastic

  data/analysis/cdf/region_map.tif (region assignments)

  data/analysis/cdf/mrl_diagnostics/ (per-region MRL plots)

  data/analysis/cdf/fitting_report.csv

Usage
-----
  python scripts/09_fit_cdf_regional.py
  python scripts/09_fit_cdf_regional.py --n-regions 8
  python scripts/09_fit_cdf_regional.py --validate
"""

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=RuntimeWarning)

_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

try:
    from _config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, RP_YEARS, N_REGIONS_DEFAULT, GPD_THRESH_MM_DEFAULT, NODATA
    from _io import write_geotiff
    from _logging import get_logger
except ImportError:  # pragma: no cover - pytest importlib fallback
    from scripts._config import REPO_ROOT, DATA_ROOT, LOG_ROOT, NROWS, NCOLS, DX, LAT_MAX, LON_MIN, RP_YEARS, N_REGIONS_DEFAULT, GPD_THRESH_MM_DEFAULT, NODATA
    from scripts._io import write_geotiff
    from scripts._logging import get_logger

EVENT_DIR = DATA_ROOT / "historical" / "events"
MESH_DIR  = DATA_ROOT / "historical" / "mesh_0.05deg_corrected"
OUT_DIR   = DATA_ROOT / "analysis" / "cdf"
FIG_DIR   = REPO_ROOT / "docs" / "figures" / "analysis"
LOG_DIR   = LOG_ROOT
LOG_FILE  = LOG_DIR / "09_fit_cdf_regional.log"
THRESHOLD_SELECTION_FILE = OUT_DIR / "threshold_selection.csv"

# Return periods to compute
# Short RPs (10–500 yr) are well-constrained by the fitted CDF.
# Long RPs (1000–50000 yr) are deep GPD extrapolation from a 28-year record
# and carry significant uncertainty. The stochastic catalog (stage 13)
# provides independent empirical estimates for long RPs that should be
# compared against these analytical values.
RP_YEARS = list(RP_YEARS)  # mutable copy for legacy call sites

# CDF fitting parameters
MIN_YEARS_FOR_FIT   = 5     # minimum nonzero years to attempt CDF fit
MIN_EXCEEDANCES_GPD = 5     # minimum exceedances for cell-level GPD
DEFAULT_GPD_THRESHOLD_MM = GPD_THRESH_MM_DEFAULT  # 2.0 inches — default splice point
MIN_REGION_EXCEEDANCES = 50  # minimum pooled exceedances for regional ξ
DEFAULT_N_REGIONS = N_REGIONS_DEFAULT        # K-means clusters for regional pooling
THRESHOLD_DIAGNOSTICS = []

log = get_logger("09_fit_cdf_regional", LOG_ROOT).info

# ═══════════════════════════════════════════════════════════════════════════════
#  Annual Maximum Series
# ═══════════════════════════════════════════════════════════════════════════════

def build_annual_max_series() -> tuple:
    """
    Build per-cell annual maximum hail series from corrected rasters.
    Returns (annual_max, years) where annual_max has shape (n_years, nrows, ncols).
    """
    import rasterio

    log("  Scanning years in corrected rasters ...")
    year_dirs = sorted(d for d in MESH_DIR.iterdir() if d.is_dir() and d.name.isdigit())
    years = [int(d.name) for d in year_dirs]
    log(f"  Years: {years[0]}–{years[-1]} ({len(years)} years)")

    annual_max = np.zeros((len(years), NROWS, NCOLS), dtype=np.float32)

    for yi, (year, ydir) in enumerate(zip(years, year_dirs)):
        tifs = sorted(ydir.glob("mesh_????????.tif"))
        year_max = np.zeros((NROWS, NCOLS), dtype=np.float32)

        for fpath in tifs:
            with rasterio.open(fpath) as src:
                data = src.read(1)
            np.maximum(year_max, data, out=year_max)

        annual_max[yi] = year_max

        if (yi + 1) % 5 == 0:
            log(f"    Year {year}: {len(tifs)} days, peak = {year_max.max():.0f} mm")

    log(f"  Annual max array: {annual_max.shape}")
    return annual_max, years

# ═══════════════════════════════════════════════════════════════════════════════
#  L-moment Estimation
# ═══════════════════════════════════════════════════════════════════════════════

def lmom_fit_lognormal(data: np.ndarray) -> tuple:
    """Fit lognormal via L-moments. Returns (mu, sigma) of the log-transform."""
    try:
        import lmoments3 as lm
        paras = lm.distr.ln3.lmom_fit(data)
        # ln3 returns (zeta, mu, sigma) — we want the 2-param version
        if paras and "mu" in paras:
            return paras["mu"], paras["sigma"]
    except Exception:
        pass

    # Fallback: method-of-moments on log-transformed data
    log_data = np.log(data[data > 0])
    if len(log_data) < 3:
        return np.nan, np.nan
    return float(np.mean(log_data)), float(np.std(log_data, ddof=1))

def lmom_fit_gpd(exceedances: np.ndarray) -> tuple:
    """Fit GPD via L-moments. Returns (xi, sigma)."""
    try:
        import lmoments3 as lm
        paras = lm.distr.gpa.lmom_fit(exceedances)
        if paras:
            xi = paras.get("c", paras.get("shape", np.nan))
            sigma = paras.get("scale", np.nan)
            # Convention: lmoments3 may use different sign for xi
            # GPD standard: xi > 0 = heavy tail (bounded from below)
            return float(xi), float(sigma)
    except Exception:
        pass
    return np.nan, np.nan

def compute_lmoment_ratios(data: np.ndarray) -> tuple:
    """Compute L-moment ratios (L-CV, L-skewness, L-kurtosis) for a sample."""
    n = len(data)
    if n < 4:
        return np.nan, np.nan, np.nan

    x = np.sort(data)
    # PWMs (probability weighted moments)
    b0 = np.mean(x)
    b1 = np.mean(np.arange(1, n) / (n - 1) * x[1:]) if n > 1 else 0
    b2 = np.mean(np.arange(1, n - 1) * np.arange(2, n) / ((n - 1) * (n - 2)) * x[2:]) if n > 2 else 0

    l1 = b0
    l2 = 2 * b1 - b0
    l3 = 6 * b2 - 6 * b1 + b0

    if l2 == 0 or l1 == 0:
        return np.nan, np.nan, np.nan

    t = l2 / l1       # L-CV
    t3 = l3 / l2      # L-skewness
    return float(t), float(t3), float(l2)

# ═══════════════════════════════════════════════════════════════════════════════
#  Regional Clustering
# ═══════════════════════════════════════════════════════════════════════════════

def cluster_cells(annual_max, n_regions):
    """
    Cluster active cells into climatologically homogeneous regions using
    K-means on (mean_hail, p_occ, latitude, longitude).
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    log(f"\n  Clustering cells into {n_regions} regions ...")

    # Active cell mask: full runs require MIN_YEARS_FOR_FIT active years, but
    # smoke tests may intentionally contain fewer total years.
    n_years = annual_max.shape[0]
    p_occ = (annual_max > 0).sum(axis=0) / n_years
    min_active_years = min(MIN_YEARS_FOR_FIT, n_years)
    active = (annual_max > 0).sum(axis=0) >= min_active_years

    rows, cols = np.where(active)
    n_active = len(rows)
    log(f"  Active cells: {n_active:,} / {NROWS * NCOLS:,}")
    if n_active == 0:
        raise RuntimeError("No active hail cells found in annual maxima")

    if n_active < n_regions * 10:
        log(f"  WARNING: Too few active cells for {n_regions} regions")
        n_regions = max(1, n_active // 10)

    # Feature matrix
    lats = LAT_MAX - (rows + 0.5) * DX
    lons = LON_MIN + (cols + 0.5) * DX
    mean_hail = np.array([annual_max[:, r, c][annual_max[:, r, c] > 0].mean()
                          if np.any(annual_max[:, r, c] > 0) else 0
                          for r, c in zip(rows, cols)])

    features = np.column_stack([
        mean_hail,
        p_occ[rows, cols],
        lats,
        lons,
    ])

    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    km = KMeans(n_clusters=n_regions, n_init=10, random_state=42)
    labels = km.fit_predict(features_scaled)

    # Build region map
    region_map = np.full((NROWS, NCOLS), -1, dtype=np.int8)
    region_map[rows, cols] = labels

    for r in range(n_regions):
        n_cells = int((labels == r).sum())
        mean_lat = float(lats[labels == r].mean())
        log(f"    Region {r}: {n_cells:,} cells, mean lat = {mean_lat:.1f}°N")

    return region_map, active, rows, cols

# ═══════════════════════════════════════════════════════════════════════════════
#  MRL Diagnostics
# ═══════════════════════════════════════════════════════════════════════════════

def compute_mrl_and_threshold(exceedances: np.ndarray, region_id: int) -> float:
    from scipy import stats
    """Select a GPD threshold using v2.1 auditable diagnostics.

    Scores candidate thresholds using exceedance count, GPD fit stability,
    KS goodness-of-fit, and approximate MRL linearity. The selected threshold
    and all candidate diagnostics are written to threshold_selection.csv.
    """
    global THRESHOLD_DIAGNOSTICS
    x = np.asarray(exceedances, dtype=np.float64)
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) < 20:
        THRESHOLD_DIAGNOSTICS.append({
            "region": region_id, "candidate_threshold_mm": DEFAULT_GPD_THRESHOLD_MM,
            "selected": 1, "n_exceedances": int(len(x)), "xi": 0.0, "sigma": np.nan,
            "mrl_score": np.nan, "stability_score": np.nan, "gof_score": np.nan,
            "reason": "too_few_observations_default",
        })
        return DEFAULT_GPD_THRESHOLD_MM

    candidate_u = np.unique(np.percentile(x, np.arange(50, 91, 5))).astype(float)
    rows = []
    prev_xi = None
    for u in candidate_u:
        exc = x[x > u] - u
        n_exc = len(exc)
        if n_exc < max(10, MIN_EXCEEDANCES_GPD):
            continue
        try:
            xi, loc, sigma = stats.genpareto.fit(exc, floc=0)
            xi = float(np.clip(xi, -0.5, 0.5))
            sigma = float(max(sigma, 1e-6))
            ks = float(stats.kstest(exc, "genpareto", args=(xi, 0, sigma)).statistic)
        except Exception:
            xi, sigma, ks = np.nan, np.nan, np.inf

        # MRL linearity: fit a line to mean residual life values at/above this threshold.
        later = []
        for uu in candidate_u[candidate_u >= u]:
            e2 = x[x > uu] - uu
            if len(e2) >= 10:
                later.append((uu, float(e2.mean())))
        if len(later) >= 3:
            uu = np.array([a for a, _ in later], dtype=float)
            mm = np.array([b for _, b in later], dtype=float)
            coef = np.polyfit(uu, mm, 1)
            pred = np.polyval(coef, uu)
            mrl_score = float(np.sqrt(np.mean((mm - pred) ** 2)) / max(np.mean(mm), 1e-6))
        else:
            mrl_score = 1.0

        stability = 0.0 if prev_xi is None or not np.isfinite(prev_xi) or not np.isfinite(xi) else abs(xi - prev_xi)
        prev_xi = xi
        # Penalize very high thresholds through small sample size.
        count_penalty = 1.0 / np.sqrt(max(n_exc, 1))
        score = ks + mrl_score + stability + count_penalty
        rows.append({
            "region": region_id,
            "candidate_threshold_mm": round(float(u), 3),
            "selected": 0,
            "n_exceedances": int(n_exc),
            "xi": round(float(xi), 6) if np.isfinite(xi) else np.nan,
            "sigma": round(float(sigma), 6) if np.isfinite(sigma) else np.nan,
            "mrl_score": round(float(mrl_score), 6),
            "stability_score": round(float(stability), 6),
            "gof_score": round(float(ks), 6) if np.isfinite(ks) else np.inf,
            "score": round(float(score), 6),
            "reason": "candidate",
        })

    if not rows:
        selected = DEFAULT_GPD_THRESHOLD_MM
        rows = [{
            "region": region_id, "candidate_threshold_mm": selected, "selected": 1,
            "n_exceedances": int((x > selected).sum()), "xi": 0.0, "sigma": np.nan,
            "mrl_score": np.nan, "stability_score": np.nan, "gof_score": np.nan,
            "score": np.nan, "reason": "no_valid_candidate_default",
        }]
    else:
        best_i = int(np.nanargmin([r["score"] for r in rows]))
        rows[best_i]["selected"] = 1
        rows[best_i]["reason"] = "selected_min_score"
        selected = float(rows[best_i]["candidate_threshold_mm"])

    THRESHOLD_DIAGNOSTICS.extend(rows)
    if THRESHOLD_DIAGNOSTICS:
        THRESHOLD_SELECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = sorted({k for row in THRESHOLD_DIAGNOSTICS for k in row.keys()})
        with open(THRESHOLD_SELECTION_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(THRESHOLD_DIAGNOSTICS)

    # Preserve existing MRL plot output for visual review.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        mrl_fig_dir = OUT_DIR / "mrl_diagnostics"
        mrl_fig_dir.mkdir(parents=True, exist_ok=True)
        test_u = np.array([r["candidate_threshold_mm"] for r in rows], dtype=float)
        mrl_vals = []
        for u in test_u:
            above = x[x > u] - u
            mrl_vals.append(float(above.mean()) if len(above) else np.nan)
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(test_u, mrl_vals, "o-")
        ax.axvline(selected, color="r", ls="--", alpha=0.7, label=f"selected {selected:.1f} mm")
        ax.set_xlabel("Threshold u (mm)")
        ax.set_ylabel("Mean Residual Life (mm)")
        ax.set_title(f"MRL Plot — Region {region_id}")
        ax.legend()
        fig.savefig(mrl_fig_dir / f"mrl_region_{region_id}.png", dpi=100, bbox_inches="tight")
        plt.close()
    except Exception:
        pass
    return selected

# ═══════════════════════════════════════════════════════════════════════════════
#  Regional GPD Fitting
# ═══════════════════════════════════════════════════════════════════════════════

def fit_regional_gpd(annual_max, region_map, n_regions):
    """
    Fit GPD with regional ξ pooling.

    For each region:
    1. Pool all cell-level exceedances above the GPD threshold
    2. Fit regional ξ from pooled L-moments
    3. For each cell in the region, fit cell-specific σ given regional ξ
    """
    log(f"\n  Fitting regional GPD (ξ pooled, σ cell-specific) ...")
    n_years = annual_max.shape[0]

    # Per-cell occurrence probability
    p_occ = (annual_max > 0).sum(axis=0).astype(np.float32) / n_years

    # Storage
    lognorm_mu    = np.full((NROWS, NCOLS), np.nan, dtype=np.float32)
    lognorm_sigma = np.full((NROWS, NCOLS), np.nan, dtype=np.float32)
    gpd_xi        = np.full((NROWS, NCOLS), np.nan, dtype=np.float32)
    gpd_sigma     = np.full((NROWS, NCOLS), np.nan, dtype=np.float32)
    gpd_threshold = np.full((NROWS, NCOLS), np.nan, dtype=np.float32)
    fit_type      = np.full((NROWS, NCOLS), 0, dtype=np.int8)
    # fit_type: 0=nodata, 1=lognorm only, 2=lognorm+gpd(regional), 3=lognorm+gpd(cell)

    region_xi_values = {}
    region_thresholds = {}
    fit_report = []

    for reg in range(n_regions):
        reg_mask = region_map == reg
        reg_rows, reg_cols = np.where(reg_mask)
        n_cells = len(reg_rows)

        if n_cells == 0:
            continue

        # Collect all annual maxima from this region
        all_nz_vals = []
        for r, c in zip(reg_rows, reg_cols):
            cell_series = annual_max[:, r, c]
            nz = cell_series[cell_series > 0]
            all_nz_vals.extend(nz.tolist())

        all_nz = np.array(all_nz_vals, dtype=np.float32)

        # MRL diagnostic to determine threshold
        threshold = compute_mrl_and_threshold(all_nz, reg)
        region_thresholds[reg] = threshold

        # Pool exceedances above threshold for regional ξ
        exceedances = all_nz[all_nz > threshold] - threshold

        if len(exceedances) >= MIN_REGION_EXCEEDANCES:
            reg_xi, _ = lmom_fit_gpd(exceedances)
            # Bound ξ to physically reasonable range
            if np.isfinite(reg_xi):
                reg_xi = float(np.clip(reg_xi, -0.5, 0.5))
            else:
                reg_xi = 0.0  # Exponential tail fallback
        else:
            reg_xi = 0.0
            log(f"    Region {reg}: only {len(exceedances)} exceedances, using ξ=0 (exponential)")

        region_xi_values[reg] = reg_xi
        log(f"    Region {reg}: {n_cells:,} cells, {len(exceedances):,} pooled exceedances, "
            f"ξ = {reg_xi:.4f}, threshold = {threshold:.0f} mm")

        # Fit each cell
        n_lognorm = n_gpd = n_fallback = 0
        for r, c in zip(reg_rows, reg_cols):
            cell_series = annual_max[:, r, c]
            nz = cell_series[cell_series > 0]

            if len(nz) < MIN_YEARS_FOR_FIT:
                continue

            # Lognormal body
            mu, sig = lmom_fit_lognormal(nz)
            if np.isfinite(mu) and np.isfinite(sig) and sig > 0:
                lognorm_mu[r, c] = mu
                lognorm_sigma[r, c] = sig
                fit_type[r, c] = 1
                n_lognorm += 1
            else:
                continue

            # GPD tail
            cell_exc = nz[nz > threshold] - threshold
            if len(cell_exc) >= MIN_EXCEEDANCES_GPD:
                # Cell-specific σ with regional ξ
                # Method of moments for σ given ξ:
                # E[X] = σ / (1 - ξ) for ξ < 1
                mean_exc = float(cell_exc.mean())
                if reg_xi < 1.0:
                    cell_sigma = mean_exc * (1.0 - reg_xi)
                else:
                    cell_sigma = mean_exc  # fallback

                if cell_sigma > 0:
                    gpd_xi[r, c] = reg_xi
                    gpd_sigma[r, c] = cell_sigma
                    gpd_threshold[r, c] = threshold
                    fit_type[r, c] = 2
                    n_gpd += 1
                    n_lognorm -= 1  # upgraded from lognorm-only
            elif len(cell_exc) > 0:
                # Too few exceedances for cell-level σ — use regional σ too
                mean_exc_reg = float(exceedances.mean()) if len(exceedances) > 0 else 10.0
                cell_sigma = mean_exc_reg * (1.0 - reg_xi) if reg_xi < 1.0 else mean_exc_reg
                gpd_xi[r, c] = reg_xi
                gpd_sigma[r, c] = cell_sigma
                gpd_threshold[r, c] = threshold
                fit_type[r, c] = 2
                n_gpd += 1
                n_lognorm -= 1
                n_fallback += 1

        fit_report.append({
            "region": reg, "n_cells": n_cells, "xi": round(reg_xi, 4),
            "threshold_mm": round(threshold, 1), "pooled_exc": len(exceedances),
            "n_lognorm_only": n_lognorm, "n_lognorm_gpd": n_gpd,
            "n_regional_sigma_fallback": n_fallback,
        })

    return (p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma,
            gpd_threshold, fit_type, region_xi_values, region_thresholds,
            fit_report)

# ═══════════════════════════════════════════════════════════════════════════════
#  Return Period Computation
# ═══════════════════════════════════════════════════════════════════════════════

def compute_return_periods(p_occ, lognorm_mu, lognorm_sigma,
                            gpd_xi, gpd_sigma, gpd_threshold, fit_type):
    from scipy import stats
    """Invert the composite CDF to get hail sizes at each return period."""
    log(f"\n  Computing return period maps for {RP_YEARS} ...")

    rp_maps = {}
    for rp in RP_YEARS:
        rp_maps[rp] = np.zeros((NROWS, NCOLS), dtype=np.float32)

    # Exceedance probability for each RP
    # P(X ≥ x in any year) = p_occ × P(X ≥ x | hail occurs)
    # RP = 1 / P(X ≥ x) → P(X ≥ x | hail) = 1 / (RP × p_occ)

    active = fit_type > 0
    rows, cols = np.where(active)

    for r, c in zip(rows, cols):
        p = p_occ[r, c]
        if p <= 0:
            continue

        mu = lognorm_mu[r, c]
        sig = lognorm_sigma[r, c]

        for rp in RP_YEARS:
            target_p = 1.0 / rp  # annual exceedance probability
            # Conditional exceedance: P(X ≥ x | hail) = target_p / p_occ
            cond_exceed = target_p / p
            if cond_exceed >= 1.0:
                rp_maps[rp][r, c] = 0.0  # RP shorter than occurrence interval
                continue

            cond_nonexceed = 1.0 - cond_exceed

            if fit_type[r, c] >= 2 and np.isfinite(gpd_xi[r, c]):
                # Composite CDF: lognormal body + GPD tail
                u = gpd_threshold[r, c]
                xi = gpd_xi[r, c]
                sig_gpd = gpd_sigma[r, c]

                # Probability of being below threshold (from lognormal)
                p_below_u = stats.lognorm.cdf(u, sig, scale=np.exp(mu))

                if cond_nonexceed <= p_below_u:
                    # RP value is in lognormal body
                    val = stats.lognorm.ppf(cond_nonexceed, sig, scale=np.exp(mu))
                else:
                    # RP value is in GPD tail
                    # P(X ≤ x) = p_below_u + (1 - p_below_u) × G((x-u)/σ; ξ)
                    p_gpd = (cond_nonexceed - p_below_u) / (1.0 - p_below_u)
                    p_gpd = min(p_gpd, 0.9999)  # numerical safety

                    if abs(xi) < 1e-6:
                        # Exponential tail
                        val = u + sig_gpd * (-np.log(1.0 - p_gpd))
                    else:
                        val = u + (sig_gpd / xi) * ((1.0 - p_gpd) ** (-xi) - 1.0)
            else:
                # Lognormal only
                val = stats.lognorm.ppf(cond_nonexceed, sig, scale=np.exp(mu))

            # Bound to physical range
            # Largest recorded hailstone: ~203 mm (8 in). For very long RPs
            # (10,000+ yr), GPD extrapolation may exceed this. Cap at 300 mm
            # (~12 in) which is beyond any plausible ground-level hail.
            rp_maps[rp][r, c] = float(np.clip(val, 0, 300))

    return rp_maps

# ═══════════════════════════════════════════════════════════════════════════════
#  Output
# ═══════════════════════════════════════════════════════════════════════════════

def save_outputs(p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma,
                  gpd_threshold, fit_type, region_map, region_xi_values,
                  rp_maps, fit_report):
    """Save all CDF fitting outputs."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # CDF parameters
    np.savez_compressed(
        OUT_DIR / "cdf_parameters.npz",
        p_occ=p_occ, lognorm_mu=lognorm_mu, lognorm_sigma=lognorm_sigma,
        gpd_xi=gpd_xi, gpd_sigma=gpd_sigma, gpd_threshold=gpd_threshold,
        fit_type=fit_type, region_map=region_map,
        region_xi=np.array(list(region_xi_values.values()), dtype=np.float32),
        grid_shape=np.array([NROWS, NCOLS]),
    )
    log(f"  Saved cdf_parameters.npz")

    # Return period GeoTIFFs
    for rp, data in rp_maps.items():
        path = OUT_DIR / f"rp_{rp:05d}yr_hail.tif"
        write_geotiff(data, path)
        peak = float(data.max())
        log(f"  {path.name}: peak = {peak:.1f} mm ({peak/25.4:.2f} in)")

    # Occurrence probability
    write_geotiff(p_occ, OUT_DIR / "p_occurrence.tif")

    # Region map
    write_geotiff(region_map.astype(np.float32), OUT_DIR / "region_map.tif")

    # Fitting report
    report_path = OUT_DIR / "fitting_report.csv"
    with open(report_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fit_report[0].keys()))
        w.writeheader()
        w.writerows(fit_report)
    log(f"  Saved fitting_report.csv")

    # v2.1 threshold diagnostics
    thresh_path = THRESHOLD_SELECTION_FILE
    if THRESHOLD_DIAGNOSTICS:
        fieldnames = sorted({k for row in THRESHOLD_DIAGNOSTICS for k in row.keys()})
        with open(thresh_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(THRESHOLD_DIAGNOSTICS)
        log(f"  Saved threshold_selection.csv")

def validate_outputs() -> bool:
    errors = []
    for fname in ["cdf_parameters.npz", "p_occurrence.tif", "region_map.tif", "fitting_report.csv", "threshold_selection.csv"]:
        p = OUT_DIR / fname
        if not p.exists():
            errors.append(f"Missing: {fname}")

    for rp in RP_YEARS:
        p = OUT_DIR / f"rp_{rp:05d}yr_hail.tif"
        if not p.exists():
            errors.append(f"Missing: rp_{rp:05d}yr_hail.tif")

    if errors:
        log("Validation FAILED:")
        for e in errors:
            log(f"  ✗ {e}")
        return False
    log("Output validation passed ✓")
    return True

def main():
    parser = argparse.ArgumentParser(description="CDF fitting with regional GPD ξ pooling.")
    parser.add_argument("--n-regions", type=int, default=DEFAULT_N_REGIONS)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.validate:
        sys.exit(0 if validate_outputs() else 1)

    log(f"\n{'='*60}")
    log(f"  CDF Fitting — Stage 09")
    log(f"{'='*60}")
    log(f"  Grid:       {NROWS} × {NCOLS} @ {DX}°")
    log(f"  Regions:    {args.n_regions}")
    log(f"  GPD splice: {DEFAULT_GPD_THRESHOLD_MM} mm default, MRL-validated")
    log(f"  RPs:        {RP_YEARS}")

    t0 = time.time()

    # Build annual max series
    log("\n[1/4] Building annual maximum series")
    annual_max, years = build_annual_max_series()

    # Cluster into regions
    log("\n[2/4] Regional clustering")
    region_map, active, rows, cols = cluster_cells(annual_max, args.n_regions)

    # Fit CDFs with regional GPD pooling
    log("\n[3/4] CDF fitting (lognormal + regional GPD)")
    (p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma,
     gpd_threshold, fit_type, region_xi, region_thresholds,
     fit_report) = fit_regional_gpd(annual_max, region_map, args.n_regions)

    # Summary
    n_total = int((fit_type > 0).sum())
    n_ln_only = int((fit_type == 1).sum())
    n_ln_gpd = int((fit_type == 2).sum())
    n_nofit = int((active & (fit_type == 0)).sum())
    log(f"\n  Fit summary: {n_total:,} cells fitted")
    log(f"    Lognormal only:      {n_ln_only:,}")
    log(f"    Lognormal + GPD:     {n_ln_gpd:,}")
    log(f"    Active but no fit:   {n_nofit:,}")

    # Compute return periods
    log("\n[4/4] Computing return period maps")
    rp_maps = compute_return_periods(p_occ, lognorm_mu, lognorm_sigma,
                                      gpd_xi, gpd_sigma, gpd_threshold, fit_type)

    # Save
    save_outputs(p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma,
                  gpd_threshold, fit_type, region_map, region_xi,
                  rp_maps, fit_report)

    elapsed = time.time() - t0
    log(f"\n{'='*60}")
    log(f"  Complete in {elapsed/60:.1f} min")
    log(f"{'='*60}\n")

    ok = validate_outputs()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
