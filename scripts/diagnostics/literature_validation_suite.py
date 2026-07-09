#!/usr/bin/env python3
"""
Literature-aligned validation suite for the CONUS hail pipeline.

Runs optional post-hoc checks motivated by ``docs/literature_review.md`` and
``docs/methodology.md``. Each check writes CSV/PNG artifacts under
``data/analysis/literature_validation/`` and a machine-readable summary JSON.

Checks (warn and skip when inputs are missing):
  1. Source-transition daily-peak QA (MYRORSS/GridRad/MRMS splices)
  2. SPC report-size rounding and detection-by-size (Blair et al. 2017)
  3. Radar vs SPC seasonal cycle alignment (Allen & Tippett 2015)
  4. SPC rural–urban reporting bias proxy (Allen & Tippett 2015)
  5. CONUS annual-max Mann–Kendall trend (stationarity assumption)
  6. Stage 08 event-count Poisson dispersion (stochastic catalog literature)
  7. Negative-binomial vs Poisson event counts (overdispersion sensitivity)
  8. Stage 09 GPD threshold diagnostic rollup (Coles 2001; Hosking & Wallis)
  9. Pilot bootstrap CI on GPD 100-yr return levels (Coles 2001)
  10. Analytical RP map monotonicity (EVT return levels)
  11. Analytical vs stochastic RP divergence (structural tail diagnostic)
  12. Pilot tail-dependence / extremogram on pooled annual max (spatial extremes)
  13. GridRad upstream ingest QA from Stage 04c manifest (Murillo et al. 2021)
  14. Per-cell hail-day benchmarks vs Murillo/Cintineo thresholds
  15. Optional ML hail-filter artifact presence (Brier/reliability — future replay)

Usage (from repo root):
  .venv/bin/python scripts/diagnostics/literature_validation_suite.py
  .venv/bin/python scripts/diagnostics/literature_validation_suite.py --only source_transition,poisson_dispersion
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts._config import (
    ANALYSIS,
    DAMAGE_THRESH_MM,
    EVENT_ACTIVE_THRESH_MM,
    HISTORICAL,
    LAT_MAX,
    LON_MIN,
    DX,
    MODEL_VERSION,
    NCOLS,
    NROWS,
    RP_YEARS,
)
from scripts._io import haversine_km
from scripts.diagnostics._diagnostic_io import count_mesh_tifs

OUT_DIR = ANALYSIS / "literature_validation"
PEAKS_CSV = ANALYSIS / "mesh_daily_peaks" / "mesh_daily_peaks.csv"
PAIRS_CSV = HISTORICAL / "validation" / "mesh_vs_spc_pairs.csv"
EVENT_CSV = HISTORICAL / "events" / "event_catalog.csv"
THRESH_CSV = ANALYSIS / "cdf" / "threshold_selection.csv"
HAIL_CLIM_DIR = ANALYSIS / "hail_day_climatology"
CORRECTED_DIR = HISTORICAL / "mesh_0.05deg_corrected"
CDF_DIR = ANALYSIS / "cdf"
CDF_NPZ = CDF_DIR / "cdf_parameters.npz"
STOCH_MAP_DIR = REPO / "data" / "stochastic" / "maps"
MESH_DIR = HISTORICAL / "mesh_0.05deg"
GRIDRAD_MANIFEST = MESH_DIR / "manifest_stage04c_gridrad.csv"
HAIL_FILTER_PKL = ANALYSIS / "calibration" / "hail_filter_model.pkl"

MRMS_START = date(2020, 10, 14)
GRIDRAD_START = date(2012, 1, 1)
GRIDRAD_END = date(2020, 10, 13)

MESH_RE = re.compile(r"mesh_(\d{8})\.tif$")

# Murillo et al. (2021) order-of-magnitude Great Plains hail-day context (coarser grid).
MURILLO_GP_HAIL_DAYS_YR_REF = (8.0, 14.0)  # approximate literature band at skill thresholds
CINTINEO_SKILL_DAYS_YR_REF = (9.0, 13.0)

# Major CONUS metro centroids for rural–urban reporting-bias proxy (Allen & Tippett 2015).
US_METRO_CENTROIDS: tuple[tuple[str, float, float], ...] = (
    ("NYC", 40.71, -74.01),
    ("LA", 34.05, -118.24),
    ("Chicago", 41.88, -87.63),
    ("Houston", 29.76, -95.37),
    ("Phoenix", 33.45, -112.07),
    ("Philadelphia", 39.95, -75.17),
    ("San Antonio", 29.42, -98.49),
    ("Dallas", 32.78, -96.80),
    ("Austin", 30.27, -97.74),
    ("Jacksonville", 30.33, -81.66),
    ("Denver", 39.74, -104.99),
    ("Columbus", 39.96, -82.99),
    ("Indianapolis", 39.77, -86.16),
    ("Charlotte", 35.23, -80.84),
    ("Seattle", 47.61, -122.33),
    ("Nashville", 36.16, -86.78),
    ("Oklahoma City", 35.47, -97.52),
    ("Kansas City", 39.10, -94.58),
    ("Atlanta", 33.75, -84.39),
    ("Miami", 25.76, -80.19),
    ("Minneapolis", 44.98, -93.27),
    ("Detroit", 42.33, -83.05),
    ("St. Louis", 38.63, -90.20),
    ("Cincinnati", 39.10, -84.51),
    ("Albuquerque", 35.08, -106.65),
)
RURAL_METRO_KM = 75.0


@dataclass
class CheckResult:
    name: str
    status: str  # pass | warn | fail | skip
    literature: str
    message: str
    metrics: dict


def classify_source(day: date) -> str:
    if day >= MRMS_START:
        return "MRMS"
    if GRIDRAD_START <= day <= GRIDRAD_END:
        return "GridRad"
    return "MYRORSS"


def mann_kendall_statistic(x: np.ndarray) -> tuple[float, float]:
    """Simple Mann–Kendall S statistic and two-sided normal-approx p-value."""
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 8:
        return float("nan"), float("nan")
    s = 0.0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += np.sign(x[j] - x[i])
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0
    from scipy.stats import norm

    p = 2.0 * (1.0 - norm.cdf(abs(z)))
    return float(s), float(p)


def _load_peaks() -> pd.DataFrame | None:
    if PEAKS_CSV.exists():
        df = pd.read_csv(PEAKS_CSV, parse_dates=["date"])
        if "peak_mm" not in df.columns and "peak_mesh_mm" in df.columns:
            df = df.rename(columns={"peak_mesh_mm": "peak_mm"})
        return df
    if not CORRECTED_DIR.exists():
        return None
    rows = []
    for path in sorted(CORRECTED_DIR.rglob("mesh_????????.tif")):
        m = MESH_RE.search(path.name)
        if not m:
            continue
        ds = m.group(1)
        d = date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        try:
            import rasterio

            with rasterio.open(path) as src:
                arr = src.read(1)
            peak = float(np.nanmax(arr))
        except Exception:
            continue
        rows.append({"date": pd.Timestamp(d), "peak_mm": peak})
    if not rows:
        return None
    return pd.DataFrame(rows)


def check_source_transition(peaks: pd.DataFrame | None) -> CheckResult:
    """Murillo/GridRad literature: era splice should not show order-of-magnitude jumps."""
    lit = "Murillo et al. (2021); literature_review.md §3"
    if peaks is None or peaks.empty:
        return CheckResult("source_transition", "skip", lit, "No daily peak table", {})
    df = peaks.copy()
    df["source"] = df["date"].apply(lambda t: classify_source(t.date()))
    df = df[df["peak_mm"] > 0]
    windows = {
        "MYRORSS_2010_2011": (("MYRORSS", 2010, 2011)),
        "GridRad_2012_2013": (("GridRad", 2012, 2013)),
        "GridRad_2016_2019": (("GridRad", 2016, 2019)),
        "MRMS_2021_2023": (("MRMS", 2021, 2023)),
    }
    metrics: dict[str, float] = {}
    medians: dict[str, float] = {}
    for key, (src, y0, y1) in windows.items():
        sub = df[(df["source"] == src) & (df["date"].dt.year.between(y0, y1))]
        if sub.empty:
            continue
        med = float(sub["peak_mm"].median())
        medians[key] = med
        metrics[f"{key}_median_mm"] = round(med, 2)
        metrics[f"{key}_n"] = int(len(sub))
    ratio_gr_myo = None
    if "GridRad_2012_2013_median_mm" in metrics and "MYRORSS_2010_2011_median_mm" in metrics:
        ratio_gr_myo = metrics["GridRad_2012_2013_median_mm"] / max(
            metrics["MYRORSS_2010_2011_median_mm"], 1.0
        )
        metrics["gridrad_myrorss_median_ratio_2012"] = round(ratio_gr_myo, 3)
    status = "pass"
    msg = "Era medians within expected range"
    if ratio_gr_myo is not None and (ratio_gr_myo > 2.5 or ratio_gr_myo < 0.4):
        status = "warn"
        msg = f"Large MYRORSS→GridRad median peak ratio ({ratio_gr_myo:.2f}×)"
    out = OUT_DIR / "source_transition_daily_peaks.csv"
    pd.DataFrame(
        [{"window": k, "median_mm": medians[k], "n_days": metrics.get(f"{k}_n", 0)} for k in medians]
    ).to_csv(out, index=False)
    return CheckResult("source_transition", status, lit, msg, metrics)


def check_spc_detection_and_rounding() -> CheckResult:
    """Blair et al. (2017): detection should rise with report size; reports cluster on round sizes."""
    lit = "Blair et al. (2017); literature_review.md §1"
    if not PAIRS_CSV.exists():
        return CheckResult("spc_detection_rounding", "skip", lit, "mesh_vs_spc_pairs.csv missing", {})
    df = pd.read_csv(PAIRS_CSV)
    if df.empty:
        return CheckResult("spc_detection_rounding", "skip", lit, "No SPC pairs", {})
    spc = df["spc_size_in"].to_numpy(dtype=np.float64)
    mesh = df["mesh75_mm"].to_numpy(dtype=np.float64) / 25.4
    bins = [0, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 99.0]
    labels = ["<0.75", "0.75-1", "1-1.25", "1.25-1.5", "1.5-2", "2-3", ">=3"]
    rows = []
    for lo, hi, lab in zip(bins[:-1], bins[1:], labels):
        m = (spc >= lo) & (spc < hi)
        n = int(m.sum())
        if n < 20:
            continue
        pod = float(np.mean(mesh[m] > 0))
        rows.append({"size_bin": lab, "n_pairs": n, "pod_mesh_detect": round(pod, 4)})
    det = pd.DataFrame(rows)
    det.to_csv(OUT_DIR / "spc_detection_by_size_bin.csv", index=False)
    # rounding: fraction within 0.02 in of quarter-inch
    quarter = np.round(spc * 4) / 4
    frac_round = float(np.mean(np.abs(spc - quarter) < 0.02))
    severe = spc >= 1.0
    pod_severe = float(np.mean(mesh[severe] >= DAMAGE_THRESH_MM / 25.4)) if severe.any() else float("nan")
    metrics = {
        "fraction_quarter_inch_rounded": round(frac_round, 3),
        "pod_severe_reports": round(pod_severe, 3),
        "n_pairs": int(len(df)),
    }
    status = "pass"
    msg = "SPC validation pairs processed"
    if det.shape[0] >= 2 and det["pod_mesh_detect"].iloc[-1] < det["pod_mesh_detect"].iloc[0]:
        status = "warn"
        msg = "Detection does not increase with report size (unexpected vs Blair et al.)"
    return CheckResult("spc_detection_rounding", status, lit, msg, metrics)


def check_seasonality_radar_vs_spc(peaks: pd.DataFrame | None) -> CheckResult:
    """Allen & Tippett (2015): radar any-cell seasonality vs SPC report-day peaks."""
    lit = "Allen & Tippett (2015); methodology.md §5.6"
    if peaks is None or not PAIRS_CSV.exists():
        return CheckResult("seasonality_alignment", "skip", lit, "Need peaks + SPC pairs", {})
    radar = peaks[peaks["peak_mm"] >= EVENT_ACTIVE_THRESH_MM].copy()
    radar["doy"] = radar["date"].dt.dayofyear
    r_hist = radar.groupby("doy").size()
    r_hist = r_hist / r_hist.sum()
    spc = pd.read_csv(PAIRS_CSV, parse_dates=["date"])
    spc["doy"] = spc["date"].dt.dayofyear
    s_hist = spc.groupby("doy").size()
    s_hist = s_hist / s_hist.sum()
    aligned = pd.DataFrame({"doy": range(1, 367)})
    aligned["radar_share"] = aligned["doy"].map(r_hist).fillna(0)
    aligned["spc_share"] = aligned["doy"].map(s_hist).fillna(0)
    aligned.to_csv(OUT_DIR / "seasonality_radar_vs_spc_doy.csv", index=False)
    # correlation on overlapping DOY (Apr–Aug emphasis)
    spring = aligned[(aligned["doy"] >= 90) & (aligned["doy"] <= 244)]
    corr = float(spring["radar_share"].corr(spring["spc_share"])) if len(spring) > 10 else float("nan")
    metrics = {"doy_correlation_apr_aug": round(corr, 3)}
    status = "pass" if corr >= 0.5 else "warn"
    msg = f"Apr–Aug DOY correlation radar vs SPC = {corr:.2f}"
    return CheckResult("seasonality_alignment", status, lit, msg, metrics)


def check_mann_kendall_annual_max(peaks: pd.DataFrame | None) -> CheckResult:
    """Stationarity: Mann–Kendall on CONUS annual maximum daily peak (methodology §13)."""
    lit = "literature_review.md §11; uncertainty.md"
    if peaks is None or peaks.empty:
        return CheckResult("mann_kendall_annual_max", "skip", lit, "No peak series", {})
    annual = peaks.groupby(peaks["date"].dt.year)["peak_mm"].max()
    s, p = mann_kendall_statistic(annual.to_numpy())
    metrics = {
        "n_years": int(len(annual)),
        "mk_s": round(s, 2) if np.isfinite(s) else None,
        "mk_pvalue": round(p, 4) if np.isfinite(p) else None,
        "first_year": int(annual.index.min()),
        "last_year": int(annual.index.max()),
    }
    status = "pass"
    msg = "No significant CONUS annual-max trend (supports stationary tail assumption)"
    if np.isfinite(p) and p < 0.05:
        status = "warn"
        msg = f"Significant Mann–Kendall trend in CONUS annual max (p={p:.4f})"
    pd.DataFrame({"year": annual.index, "conus_max_mm": annual.values}).to_csv(
        OUT_DIR / "conus_annual_max_series.csv", index=False
    )
    return CheckResult("mann_kendall_annual_max", status, lit, msg, metrics)


def check_poisson_dispersion() -> CheckResult:
    """Stage 08 λ: index of dispersion >> 1 ⇒ Poisson under-dispersed (literature_review §9)."""
    lit = "literature_review.md §9; pnas_article §Results"
    if not EVENT_CSV.exists():
        return CheckResult("poisson_dispersion", "skip", lit, "event_catalog.csv missing", {})
    ec = pd.read_csv(EVENT_CSV, parse_dates=["start_date"])
    annual = ec.groupby(ec["start_date"].dt.year).size()
    mean = float(annual.mean())
    var = float(annual.var())
    iod = var / mean if mean > 0 else float("nan")
    metrics = {
        "n_events": int(len(ec)),
        "mean_events_per_year": round(mean, 2),
        "var_events_per_year": round(var, 2),
        "index_of_dispersion": round(iod, 2),
    }
    annual.to_csv(OUT_DIR / "annual_event_counts.csv", header=["n_events"])
    status = "pass"
    msg = f"Index of dispersion = {iod:.2f} (document Poisson limitation if ≫1)"
    if iod > 3.0:
        status = "warn"
    return CheckResult("poisson_dispersion", status, lit, msg, metrics)


def check_gpd_threshold_summary() -> CheckResult:
    """Coles (2001): rollup of automated Stage 09 threshold diagnostics."""
    lit = "Coles (2001); Hosking & Wallis (1997); methodology.md §9"
    if not THRESH_CSV.exists():
        return CheckResult("gpd_threshold_summary", "skip", lit, "threshold_selection.csv missing", {})
    df = pd.read_csv(THRESH_CSV)
    if df.empty:
        return CheckResult("gpd_threshold_summary", "skip", lit, "Empty threshold table", {})
    cols = [c for c in df.columns if c in ("xi", "sigma", "n_exceed", "mrl_score", "ks_stat")]
    summary = {
        "n_cells": int(len(df)),
        "median_xi": round(float(df["xi"].median()), 4) if "xi" in df else None,
        "p95_xi": round(float(df["xi"].quantile(0.95)), 4) if "xi" in df else None,
        "fraction_positive_xi": round(float((df["xi"] > 0).mean()), 4) if "xi" in df else None,
    }
    if "mrl_score" in df:
        summary["median_mrl_score"] = round(float(df["mrl_score"].median()), 4)
    df.describe().to_csv(OUT_DIR / "gpd_threshold_summary_stats.csv")
    status = "pass"
    msg = "GPD threshold diagnostics summarized"
    if summary.get("fraction_positive_xi") is not None and summary["fraction_positive_xi"] > 0.85:
        status = "warn"
        msg = "High fraction of cells with ξ>0 — review heavy-tail assumption"
    return CheckResult("gpd_threshold_summary", status, lit, msg, summary)


def check_rp_monotonicity() -> CheckResult:
    """Return-period maps should increase (or tie) with return period."""
    lit = "Coles (2001); technical_documentation.md §13"
    paths = {rp: CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif" for rp in RP_YEARS}
    missing = [rp for rp, p in paths.items() if not p.exists()]
    if len(missing) == len(paths):
        return CheckResult("rp_monotonicity", "skip", lit, "No analytical RP GeoTIFFs", {})
    try:
        import rasterio
    except ImportError:
        return CheckResult("rp_monotonicity", "skip", lit, "rasterio unavailable", {})
    maxima = {}
    for rp, path in paths.items():
        if not path.exists():
            continue
        with rasterio.open(path) as src:
            d = src.read(1)
        maxima[rp] = float(np.nanmax(d))
    rps = sorted(maxima)
    violations = []
    for i in range(len(rps) - 1):
        if maxima[rps[i + 1]] + 0.5 < maxima[rps[i]]:
            violations.append((rps[i], rps[i + 1]))
    metrics = {f"max_mm_rp_{rp}yr": round(maxima[rp], 2) for rp in rps}
    metrics["n_violations"] = len(violations)
    status = "pass" if not violations else "fail"
    msg = "Analytical RP maxima monotonic" if not violations else f"Monotonicity violations: {violations}"
    return CheckResult("rp_monotonicity", status, lit, msg, metrics)


def check_analytical_vs_stochastic() -> CheckResult:
    """Structural diagnostic: empirical stochastic RP vs analytical GPD maps."""
    lit = "literature_review.md §7; methodology.md §13"
    rp = 100
    ana = CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif"
    sto = STOCH_MAP_DIR / f"rp_{rp:05d}yr_stochastic.tif"
    if not ana.exists() or not sto.exists():
        return CheckResult("analytical_vs_stochastic", "skip", lit, f"Need analytical + stochastic {rp}-yr maps", {})
    try:
        import rasterio
    except ImportError:
        return CheckResult("analytical_vs_stochastic", "skip", lit, "rasterio unavailable", {})
    with rasterio.open(ana) as sa, rasterio.open(sto) as ss:
        a = sa.read(1)
        s = ss.read(1)
    mask = (a > 0) | (s > 0)
    if not mask.any():
        return CheckResult("analytical_vs_stochastic", "skip", lit, "Empty RP maps", {})
    ratio = np.where(mask, s / np.maximum(a, 1e-3), np.nan)
    metrics = {
        "rp_years": rp,
        "median_ratio_stoch_over_analytical": round(float(np.nanmedian(ratio)), 3),
        "p95_ratio": round(float(np.nanpercentile(ratio, 95)), 3),
        "fraction_stoch_gt_1p5x_analytical": round(float(np.nanmean(ratio > 1.5)), 4),
    }
    status = "pass"
    msg = f"{rp}-yr median stochastic/analytical = {metrics['median_ratio_stoch_over_analytical']}"
    if metrics["fraction_stoch_gt_1p5x_analytical"] > 0.25:
        status = "warn"
        msg += " — review GPD tail / perturbation σ"
    return CheckResult("analytical_vs_stochastic", status, lit, msg, metrics)


def check_rp_ring_energy() -> CheckResult:
    """Range-bin CV on 100-yr analytical RP map — lower suggests less range-ring structure."""
    lit = "methodology.md §5.5; docs/radar_artifact_ml_plan.md"
    rp = 100
    tif = CDF_DIR / f"rp_{rp:05d}yr_hail_smooth.tif"
    if not tif.exists():
        return CheckResult("rp_ring_energy", "skip", lit, f"Missing analytical {rp}-yr map", {})
    try:
        import rasterio
        from scripts._radar_geometry import DEFAULT_RANGE_BIN_EDGES_KM, ensure_range_km_grid
    except ImportError:
        return CheckResult("rp_ring_energy", "skip", lit, "rasterio unavailable", {})
    with rasterio.open(tif) as src:
        data = src.read(1).astype(np.float32)
    range_km = ensure_range_km_grid()
    edges = DEFAULT_RANGE_BIN_EDGES_KM
    profile = []
    for bi in range(len(edges) - 1):
        mask = (range_km >= edges[bi]) & (range_km < edges[bi + 1]) & (data > 0)
        if mask.any():
            profile.append(float(np.mean(data[mask])))
    if len(profile) < 4:
        return CheckResult("rp_ring_energy", "skip", lit, "Insufficient range bins", {})
    prof = np.array(profile, dtype=np.float64)
    cv = float(np.std(prof) / max(np.mean(prof), 1e-3))
    metrics = {"rp_years": rp, "range_profile_cv": round(cv, 4), "n_bins": len(profile)}
    status = "pass" if cv < 0.45 else "warn"
    msg = f"100-yr RP range-profile CV = {cv:.3f} (lower → less ring structure)"
    return CheckResult("rp_ring_energy", status, lit, msg, metrics)


def check_literature_hail_day_benchmarks() -> CheckResult:
    """Murillo/Cintineo per-cell hail-day rate benchmarks (hail_day_climatology outputs)."""
    lit = "Murillo et al. (2021); Cintineo et al. (2012); hail_day_climatology.py"
    bench = HAIL_CLIM_DIR / "threshold_benchmark_summary.csv"
    if not bench.exists():
        return CheckResult("literature_hail_day_benchmarks", "skip", lit, "Run hail_day_climatology.py first", {})
    df = pd.read_csv(bench)
    row29 = df[df["threshold_key"] == "skill_29mm"]
    if row29.empty:
        return CheckResult("literature_hail_day_benchmarks", "skip", lit, "skill_29mm row missing", {})
    gp_max = float(row29["gp_max_days_per_year"].iloc[0])
    metrics = {
        "gp_max_days_per_year_29mm": round(gp_max, 2),
        "murillo_ref_lo": MURILLO_GP_HAIL_DAYS_YR_REF[0],
        "murillo_ref_hi": MURILLO_GP_HAIL_DAYS_YR_REF[1],
        "cintineo_ref_lo": CINTINEO_SKILL_DAYS_YR_REF[0],
        "cintineo_ref_hi": CINTINEO_SKILL_DAYS_YR_REF[1],
    }
    status = "pass"
    msg = f"GP max {gp_max:.1f} days/yr at 29 mm"
    if gp_max > MURILLO_GP_HAIL_DAYS_YR_REF[1] * 1.5:
        status = "warn"
        msg += " — exceeds Murillo-era reference band"
    return CheckResult("literature_hail_day_benchmarks", status, lit, msg, metrics)


def _nearest_metro_km(lat: float, lon: float) -> float:
    return min(haversine_km(lat, lon, mlat, mlon) for _, mlat, mlon in US_METRO_CENTROIDS)


def _cell_latlon(row: int, col: int) -> tuple[float, float]:
    lat = LAT_MAX - (row + 0.5) * DX
    lon = LON_MIN + (col + 0.5) * DX
    return lat, lon


def _preferred_mesh_dir() -> Path | None:
    for d in (CORRECTED_DIR, MESH_DIR):
        if count_mesh_tifs(d) >= 30:
            return d
    return None


def _pooled_annual_max(mesh_dir: Path, years: tuple[int, ...]) -> np.ndarray:
    """Max over selected calendar years (pilot spatial-extremes diagnostic)."""
    import rasterio

    max_arr = np.zeros((NROWS, NCOLS), dtype=np.float32)
    for y in years:
        year_dir = mesh_dir / str(y)
        if not year_dir.is_dir():
            continue
        for path in sorted(year_dir.glob("mesh_*.tif")):
            with rasterio.open(path) as src:
                d = src.read(1).astype(np.float32)
            np.maximum(max_arr, d, out=max_arr)
    return max_arr


def _composite_rp_mm(
    r: int,
    c: int,
    rp: int,
    p_occ: np.ndarray,
    lognorm_mu: np.ndarray,
    lognorm_sigma: np.ndarray,
    gpd_xi: np.ndarray,
    gpd_sigma: np.ndarray,
    gpd_threshold: np.ndarray,
    fit_type: np.ndarray,
    *,
    p_override: float | None = None,
    xi_override: float | None = None,
    sigma_override: float | None = None,
) -> float:
    """Invert composite CDF at one cell (mirrors Stage 09 ``compute_return_periods``)."""
    from scipy import stats

    p = float(p_override if p_override is not None else p_occ[r, c])
    if p <= 0:
        return 0.0
    target_p = 1.0 / rp
    cond_exceed = target_p / p
    if cond_exceed >= 1.0:
        return 0.0
    cond_nonexceed = 1.0 - cond_exceed
    mu = float(lognorm_mu[r, c])
    sig = float(lognorm_sigma[r, c])
    if fit_type[r, c] >= 2 and np.isfinite(gpd_xi[r, c]):
        u = float(gpd_threshold[r, c])
        xi = float(xi_override if xi_override is not None else gpd_xi[r, c])
        sig_gpd = float(sigma_override if sigma_override is not None else gpd_sigma[r, c])
        p_below_u = stats.lognorm.cdf(u, sig, scale=np.exp(mu))
        if cond_nonexceed <= p_below_u:
            val = stats.lognorm.ppf(cond_nonexceed, sig, scale=np.exp(mu))
        else:
            p_gpd = (cond_nonexceed - p_below_u) / (1.0 - p_below_u)
            p_gpd = min(p_gpd, 0.9999)
            if abs(xi) < 1e-6:
                val = u + sig_gpd * (-np.log(1.0 - p_gpd))
            else:
                val = u + (sig_gpd / xi) * ((1.0 - p_gpd) ** (-xi) - 1.0)
    else:
        val = stats.lognorm.ppf(cond_nonexceed, sig, scale=np.exp(mu))
    return float(np.clip(val, 0, 300))


def check_spc_rural_urban_bias() -> CheckResult:
    """Allen & Tippett (2015): rural reports under-represented vs radar; metro proxy POD."""
    lit = "Allen & Tippett (2015); literature_review.md §1"
    if not PAIRS_CSV.exists():
        return CheckResult("spc_rural_urban_bias", "skip", lit, "mesh_vs_spc_pairs.csv missing", {})
    df = pd.read_csv(PAIRS_CSV)
    if df.empty or "lat" not in df.columns:
        return CheckResult("spc_rural_urban_bias", "skip", lit, "No SPC pairs with lat/lon", {})
    df = df.copy()
    df["metro_km"] = df.apply(lambda row: _nearest_metro_km(row["lat"], row["lon"]), axis=1)
    df["zone"] = np.where(df["metro_km"] <= RURAL_METRO_KM, "urban", "rural")
    severe = df["spc_size_in"] >= 1.0
    rows = []
    for zone in ("urban", "rural"):
        sub = df[severe & (df["zone"] == zone)]
        if len(sub) < 30:
            continue
        pod = float(np.mean(sub["mesh75_mm"] >= DAMAGE_THRESH_MM))
        rows.append({"zone": zone, "n_pairs": len(sub), "pod_severe": round(pod, 4)})
    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUT_DIR / "spc_pod_urban_vs_rural.csv", index=False)
    if out_df.shape[0] < 2:
        return CheckResult("spc_rural_urban_bias", "skip", lit, "Insufficient urban/rural pairs", {})
    urban = float(out_df.loc[out_df["zone"] == "urban", "pod_severe"].iloc[0])
    rural = float(out_df.loc[out_df["zone"] == "rural", "pod_severe"].iloc[0])
    ratio = urban / max(rural, 1e-6)
    metrics = {
        "pod_urban_severe": round(urban, 3),
        "pod_rural_severe": round(rural, 3),
        "urban_over_rural_pod_ratio": round(ratio, 3),
        "metro_threshold_km": RURAL_METRO_KM,
    }
    status = "pass"
    msg = f"Urban/rural severe POD ratio = {ratio:.2f} (Allen & Tippett: expect urban ≥ rural)"
    if ratio < 0.9:
        status = "warn"
        msg += " — rural POD exceeds urban (check pairing or metro proxy)"
    return CheckResult("spc_rural_urban_bias", status, lit, msg, metrics)


def check_gridrad_upstream_qc() -> CheckResult:
    """Murillo et al. (2021): upstream volume exclusion; Stage 04c manifest rollup."""
    lit = "Murillo et al. (2021); literature_review.md §3.7; Stage 04c manifest"
    if not GRIDRAD_MANIFEST.is_file():
        return CheckResult("gridrad_upstream_qc", "skip", lit, "manifest_stage04c_gridrad.csv missing", {})
    df = pd.read_csv(GRIDRAD_MANIFEST)
    if df.empty or "status" not in df.columns:
        return CheckResult("gridrad_upstream_qc", "skip", lit, "Empty or invalid manifest", {})
    counts = df["status"].value_counts().to_dict()
    n = int(len(df))
    frac_missing = float(counts.get("missing_source", 0)) / n
    frac_error = float(counts.get("error", 0)) / n
    metrics = {
        "n_days": n,
        **{f"status_{k}": int(v) for k, v in counts.items()},
        "fraction_missing_source": round(frac_missing, 4),
        "fraction_error": round(frac_error, 4),
    }
    pd.DataFrame([{"status": k, "count": v} for k, v in counts.items()]).to_csv(
        OUT_DIR / "gridrad_manifest_status_counts.csv", index=False
    )
    status = "pass"
    msg = f"GridRad manifest: {n:,} days; missing_source={frac_missing:.1%}"
    if frac_missing > 0.05 or frac_error > 0.01:
        status = "warn"
        msg += " — elevated ingest failures (Murillo excluded ~0.5% volumes manually)"
    return CheckResult("gridrad_upstream_qc", status, lit, msg, metrics)


def check_negative_binomial_events() -> CheckResult:
    """Overdispersion sensitivity: NB vs Poisson on annual event counts (literature_review §9)."""
    lit = "literature_review.md §9; Cameron & Trivedi (1998)"
    if not EVENT_CSV.exists():
        return CheckResult("negative_binomial_dispersion", "skip", lit, "event_catalog.csv missing", {})
    ec = pd.read_csv(EVENT_CSV, parse_dates=["start_date"])
    annual = ec.groupby(ec["start_date"].dt.year).size().to_numpy(dtype=np.float64)
    if len(annual) < 5:
        return CheckResult("negative_binomial_dispersion", "skip", lit, "Too few years of events", {})
    mean = float(annual.mean())
    var = float(annual.var())
    iod = var / mean if mean > 0 else float("nan")
    from scipy.stats import poisson

    loglik_pois = float(np.sum(poisson.logpmf(annual, mean)))
    from scipy.special import gammaln

    nb_r = mean**2 / max(var - mean, 1e-6) if var > mean else float("inf")
    nb_p = nb_r / (nb_r + mean) if np.isfinite(nb_r) else 1.0
    if np.isfinite(nb_r) and nb_r > 0:
        loglik_nb = float(
            np.sum(
                gammaln(annual + nb_r)
                - gammaln(nb_r)
                - gammaln(annual + 1)
                + nb_r * np.log(nb_p)
                + annual * np.log(1.0 - nb_p + 1e-12)
            )
        )
    else:
        loglik_nb = loglik_pois
    metrics = {
        "n_years": int(len(annual)),
        "mean_events_per_year": round(mean, 2),
        "var_events_per_year": round(var, 2),
        "index_of_dispersion": round(iod, 2),
        "nb_dispersion_r": round(nb_r, 2) if np.isfinite(nb_r) else None,
        "delta_loglik_nb_minus_pois": round(loglik_nb - loglik_pois, 2),
    }
    pd.DataFrame({"year": ec.groupby(ec["start_date"].dt.year).size().index, "n_events": annual}).to_csv(
        OUT_DIR / "annual_event_counts_nb_check.csv", index=False
    )
    status = "pass"
    msg = f"NB improves log-likelihood by {metrics['delta_loglik_nb_minus_pois']:.1f} vs Poisson (IoD={iod:.2f})"
    if iod > 3.0:
        status = "warn"
        msg += " — consider NB catalog in v3.0 (Poisson limitation documented)"
    return CheckResult("negative_binomial_dispersion", status, lit, msg, metrics)


def check_bootstrap_rp_ci() -> CheckResult:
    """Coles (2001): pilot parametric-bootstrap CI on 100-yr composite return levels."""
    lit = "Coles (2001); methodology.md §9"
    if not CDF_NPZ.exists():
        return CheckResult("bootstrap_rp_ci", "skip", lit, "cdf_parameters.npz missing", {})
    z = np.load(CDF_NPZ)
    fit_type = z["fit_type"]
    active = fit_type > 0
    rows, cols = np.where(active)
    if len(rows) < 80:
        return CheckResult("bootstrap_rp_ci", "skip", lit, "Too few fitted cells", {})
    rng = np.random.default_rng(42)
    idx = rng.choice(len(rows), size=min(150, len(rows)), replace=False)
    rp = 100
    point_vals = []
    for i in idx:
        r, c = rows[i], cols[i]
        v = _composite_rp_mm(
            r,
            c,
            rp,
            z["p_occ"],
            z["lognorm_mu"],
            z["lognorm_sigma"],
            z["gpd_xi"],
            z["gpd_sigma"],
            z["gpd_threshold"],
            fit_type,
        )
        if v > 0:
            point_vals.append(v)
    if len(point_vals) < 30:
        return CheckResult("bootstrap_rp_ci", "skip", lit, "Too few positive 100-yr levels", {})
    boot_medians = []
    for _ in range(250):
        sample = rng.choice(idx, size=len(idx), replace=True)
        vals = []
        for i in sample:
            r, c = rows[i], cols[i]
            p_j = float(np.clip(z["p_occ"][r, c] * (1.0 + 0.05 * rng.normal()), 1e-6, 1.0))
            xi_j = float(z["gpd_xi"][r, c] * (1.0 + 0.12 * rng.normal()))
            sig_j = float(z["gpd_sigma"][r, c] * (1.0 + 0.12 * rng.normal()))
            v = _composite_rp_mm(
                r,
                c,
                rp,
                z["p_occ"],
                z["lognorm_mu"],
                z["lognorm_sigma"],
                z["gpd_xi"],
                z["gpd_sigma"],
                z["gpd_threshold"],
                fit_type,
                p_override=p_j,
                xi_override=xi_j,
                sigma_override=sig_j,
            )
            if v > 0:
                vals.append(v)
        if vals:
            boot_medians.append(float(np.median(vals)))
    if len(boot_medians) < 50:
        return CheckResult("bootstrap_rp_ci", "skip", lit, "Bootstrap failed to converge", {})
    ci_lo, ci_hi = np.percentile(boot_medians, [2.5, 97.5])
    med = float(np.median(point_vals))
    width = float(ci_hi - ci_lo)
    rel_width = width / max(med, 1.0)
    metrics = {
        "rp_years": rp,
        "n_cells_sampled": int(len(point_vals)),
        "median_100yr_mm": round(med, 2),
        "bootstrap_ci_lo_mm": round(float(ci_lo), 2),
        "bootstrap_ci_hi_mm": round(float(ci_hi), 2),
        "relative_ci_width": round(rel_width, 3),
    }
    pd.DataFrame({"bootstrap_median_mm": boot_medians}).to_csv(
        OUT_DIR / "bootstrap_rp100_median_samples.csv", index=False
    )
    status = "pass"
    msg = f"100-yr median {med:.1f} mm; bootstrap 95% CI [{ci_lo:.1f}, {ci_hi:.1f}] mm"
    if rel_width > 0.5:
        status = "warn"
        msg += " — wide CI (short record / tail uncertainty)"
    return CheckResult("bootstrap_rp_ci", status, lit, msg, metrics)


def check_tail_dependence_pilot() -> CheckResult:
    """Pilot spatial tail dependence on pooled annual max (Schlather 2002; Davis & Mikosch 2009)."""
    lit = "Schlather (2002); Davis & Mikosch (2009); spatial extremes literature"
    mesh_dir = _preferred_mesh_dir()
    if mesh_dir is None:
        return CheckResult("tail_dependence_pilot", "skip", lit, "Need ≥30 mesh TIFFs", {})
    try:
        import rasterio
    except ImportError:
        return CheckResult("tail_dependence_pilot", "skip", lit, "rasterio unavailable", {})
    years = (2014, 2015, 2016)
    amax = _pooled_annual_max(mesh_dir, years)
    u = 50.0
    pool_thresh = 25.4
    active = np.argwhere(amax >= pool_thresh)
    if len(active) < 40:
        return CheckResult(
            "tail_dependence_pilot", "skip", lit, f"Too few cells ≥{pool_thresh} mm in {years}", {}
        )
    rng = np.random.default_rng(7)
    if len(active) > 400:
        pick = rng.choice(len(active), size=400, replace=False)
        active = active[pick]
    lats = np.array([_cell_latlon(r, c)[0] for r, c in active])
    lons = np.array([_cell_latlon(r, c)[1] for r, c in active])
    vals = np.array([amax[r, c] for r, c in active])
    exceed = vals >= u
    p_exceed = float(exceed.mean())
    bins = [(50, 150), (150, 300), (300, 600)]
    rows = []
    for d_lo, d_hi in bins:
        joint = 0
        marg = 0
        pairs = 0
        n = len(active)
        for i in range(n):
            for j in range(i + 1, n):
                d = haversine_km(lats[i], lons[i], lats[j], lons[j])
                if d_lo <= d < d_hi:
                    pairs += 1
                    if exceed[i] and exceed[j]:
                        joint += 1
                    if exceed[i] or exceed[j]:
                        marg += 1
        chi = (joint / pairs) / max(p_exceed**2, 1e-9) if pairs > 0 else float("nan")
        rows.append(
            {
                "distance_km_lo": d_lo,
                "distance_km_hi": d_hi,
                "n_pairs": pairs,
                "chi_u": round(float(chi), 4) if np.isfinite(chi) else None,
            }
        )
    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUT_DIR / "tail_dependence_pilot_chi.csv", index=False)
    chi_near = out_df.loc[out_df["distance_km_lo"] == 50, "chi_u"]
    chi_far = out_df.loc[out_df["distance_km_lo"] == 300, "chi_u"]
    metrics = {
        "threshold_mm": u,
        "years_pooled": list(years),
        "n_cells_sampled": int(len(active)),
        "p_exceed": round(p_exceed, 4),
        "chi_50_150km": float(chi_near.iloc[0]) if len(chi_near) else None,
        "chi_300_600km": float(chi_far.iloc[0]) if len(chi_far) else None,
    }
    status = "pass"
    msg = "Pilot extremogram: tail dependence should decay with distance (v3.0: full catalog)"
    if metrics["chi_50_150km"] and metrics["chi_300_600km"]:
        if metrics["chi_300_600km"] > metrics["chi_50_150km"]:
            status = "warn"
            msg += " — distant pairs show higher χ(u) than near pairs (small sample)"
    return CheckResult("tail_dependence_pilot", status, lit, msg, metrics)


def check_ml_filter_reliability() -> CheckResult:
    """Brier / reliability for optional Stage 05 ML hail filter (Gneiting et al. 2005)."""
    lit = "Gneiting et al. (2005); Murphy (1973); methodology.md §5.4"
    diag_path = ANALYSIS / "calibration" / "hail_filter_diagnostics.csv"
    if not HAIL_FILTER_PKL.exists():
        return CheckResult(
            "ml_filter_reliability",
            "skip",
            lit,
            "No hail_filter_model.pkl (deterministic --skip-ml baseline)",
            {"model_present": False},
        )
    metrics: dict[str, float | bool | None] = {"model_present": True}
    if not diag_path.is_file():
        return CheckResult(
            "ml_filter_reliability",
            "warn",
            lit,
            "ML model on disk but hail_filter_diagnostics.csv missing — retrain with --retrain-models",
            metrics,
        )
    diag = pd.read_csv(diag_path)
    if diag.empty:
        return CheckResult("ml_filter_reliability", "skip", lit, "Empty filter diagnostics", metrics)
    row = diag.iloc[-1]
    for col in ("brier_score", "auc", "calibration_slope", "precision", "recall"):
        if col in row and pd.notna(row[col]):
            metrics[col] = round(float(row[col]), 4)
    diag.to_csv(OUT_DIR / "ml_filter_diagnostics_copy.csv", index=False)
    status = "pass"
    brier = metrics.get("brier_score")
    msg = f"ML filter diagnostics loaded (Brier={brier})" if brier is not None else "ML filter diagnostics loaded"
    if brier is not None and brier > 0.25:
        status = "warn"
        msg += " — elevated Brier score; review reliability diagram"
    return CheckResult("ml_filter_reliability", status, lit, msg, metrics)


CHECKS = {
    "source_transition": lambda peaks: check_source_transition(peaks),
    "spc_detection_rounding": lambda _peaks: check_spc_detection_and_rounding(),
    "seasonality_alignment": lambda peaks: check_seasonality_radar_vs_spc(peaks),
    "spc_rural_urban_bias": lambda _peaks: check_spc_rural_urban_bias(),
    "mann_kendall_annual_max": lambda peaks: check_mann_kendall_annual_max(peaks),
    "poisson_dispersion": lambda _peaks: check_poisson_dispersion(),
    "negative_binomial_dispersion": lambda _peaks: check_negative_binomial_events(),
    "gpd_threshold_summary": lambda _peaks: check_gpd_threshold_summary(),
    "bootstrap_rp_ci": lambda _peaks: check_bootstrap_rp_ci(),
    "rp_monotonicity": lambda _peaks: check_rp_monotonicity(),
    "analytical_vs_stochastic": lambda _peaks: check_analytical_vs_stochastic(),
    "rp_ring_energy": lambda _peaks: check_rp_ring_energy(),
    "tail_dependence_pilot": lambda _peaks: check_tail_dependence_pilot(),
    "gridrad_upstream_qc": lambda _peaks: check_gridrad_upstream_qc(),
    "literature_hail_day_benchmarks": lambda _peaks: check_literature_hail_day_benchmarks(),
    "ml_filter_reliability": lambda _peaks: check_ml_filter_reliability(),
}


def write_readme(results: list[CheckResult]) -> None:
    lines = [
        "# Literature validation suite",
        "",
        f"Model **{MODEL_VERSION}**. Generated by `scripts/diagnostics/literature_validation_suite.py`.",
        "",
        "Each check maps to citations in `docs/literature_review.md`. Status codes:",
        "`pass`, `warn` (review), `fail`, `skip` (inputs not ready).",
        "",
        "| Check | Status | Literature | Message |",
        "|-------|--------|------------|---------|",
    ]
    for r in results:
        lines.append(f"| {r.name} | **{r.status}** | {r.literature} | {r.message} |")
    lines.extend(
        [
            "",
            "## Recommended run order",
            "",
            "1. After Stage 05: `summarize_mesh_daily_peaks.py`, `hail_day_climatology.py`, `radar_artifact_diagnostic.py`",
            "2. After Stage 06: re-run suite (SPC checks incl. rural–urban bias)",
            "3. After Stages 08–09: dispersion, NB, GPD, bootstrap RP CI",
            "4. After Stages 09–13: RP monotonicity, analytical vs stochastic, tail-dependence pilot",
            "5. After Stage 04c: GridRad manifest upstream QC",
            "",
            "Missing inputs emit `WARNING: SKIP` and continue (see `scripts/diagnostics/_diagnostic_io.py`).",
            "",
            "Full suite: `.venv/bin/python scripts/diagnostics/literature_validation_suite.py`",
        ]
    )
    (OUT_DIR / "README.md").write_text("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Literature-aligned pipeline validation suite.")
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated check names (default: all)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    global OUT_DIR
    OUT_DIR = args.out_dir
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print("Literature validation suite")
    print(f"  out_dir: {OUT_DIR}")
    peaks = _load_peaks()
    if peaks is not None:
        print(f"  daily peaks: {len(peaks):,} rows")
    names = list(CHECKS)
    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
    results: list[CheckResult] = []
    for name in names:
        fn = CHECKS.get(name)
        if fn is None:
            print(f"  WARN: unknown check {name!r}")
            continue
        res = fn(peaks)
        results.append(res)
        print(f"  [{res.status:4}] {res.name}: {res.message}")
    summary = {
        "model_version": MODEL_VERSION,
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.time() - t0, 1),
        "checks": [asdict(r) for r in results],
    }
    (OUT_DIR / "validation_summary.json").write_text(json.dumps(summary, indent=2))
    write_readme(results)
    print(f"Done in {summary['elapsed_s']:.1f}s → {OUT_DIR}")


if __name__ == "__main__":
    main()
