# Hail Catastrophe Model — Executive Summary

**Version:** 2.1  
**Date:** 2026-05-01  
**Status:** v2.0 pipeline methodology hardened for v2.1 implementation  
**Primary use:** CONUS hail hazard modeling, stochastic event simulation, and model-risk diagnostics

---

## What Was Built

This project builds a radar-based hail catastrophe hazard layer for the continental United States. It estimates hail intensity and exceedance probability on a 0.05° grid, approximately 5.5 km, using nearly three decades of radar-derived MESH observations from MYRORSS, GridRad, and operational MRMS.

The model replaces SPC-report-driven hazard estimation with spatially continuous radar input. SPC reports remain important, but only as a validation and calibration reference. This design substantially reduces population-density bias, reporting-time bias, road-network bias, and report-size rounding artifacts.

---

## What v2.1 Changes

v2.1 is an incremental hardening of v2.0. It does not replace the 15-stage pipeline. It improves the most important methodological weaknesses:

1. **Bias correction:** GridRad calibration is upgraded from global quantile mapping to conditional calibration using environmental covariates where available.
2. **Environmental filtering:** Fixed thresholds are augmented with probabilistic filtering using MESH, CAPE, freezing level, latitude, month, and optional RH/shear features.
3. **Event catalog:** Synoptic grouping keeps the v2.0 overlap/gap rules but adds centroid continuity and intensity consistency checks to reduce false merges.
4. **Extreme-value fitting:** GPD threshold selection is automated and documented using MRL, parameter stability, and goodness-of-fit diagnostics.
5. **Spatial dependence:** v2.1 introduces a lightweight dependence diagnostic and optional Gaussian-copula sampling layer for extremes.
6. **Stochastic catalog:** The simulation is made sparse-safe; event translation, intensity scaling, and shape perturbations operate on `(rows, cols, vals)` arrays instead of dense event cubes.
7. **Topographic correction:** The fixed 5% per km correction is replaced by an elevation/freezing-level hail-survival factor when ERA5 fields are available.
8. **Diagnostics:** Analytical-vs-stochastic divergence maps and tail-stability flags are added for model-risk review.

---

## Data Architecture

```text
data/historical/    Radar downloads, corrected MESH, SPC reports, climatology, events
data/analysis/      Calibration models, CDF parameters, occurrence probabilities, topography, vulnerability
data/stochastic/    50,000-year catalog, empirical return-period maps, exceedance tables
```

The model uses a common 0.05° CONUS grid:

| Parameter | Value |
|---|---:|
| Resolution | 0.05° × 0.05° |
| Approximate cell size | ~5.5 km |
| Dimensions | 520 rows × 1180 columns |
| Total cells | 613,600 |
| CRS | EPSG:4326 |

---

## Pipeline Summary

| Phase | Stages | Description |
|---|---|---|
| Data acquisition | 01–04b | Download MYRORSS/MRMS/SPC/ERA5 and compute GridRad MESH75 |
| Homogenization | 05–06 | Correct MESH, apply filtering, validate against SPC |
| Historical hazard | 07–12 | Build climatology, events, CDFs, occurrence, mask, topography |
| Stochastic hazard | 13 | Simulate 50,000 years using sparse event resampling |
| Vulnerability + reporting | 14–15 | Build placeholder MDR curves and render diagnostics |

---

## Key Parameters

| Parameter | v2.1 Value / Method |
|---|---|
| Primary hazard input | Radar-derived MESH / MESH75 |
| Grid | 0.05° CONUS grid |
| Bias correction | MESH75 recalibration + conditional GridRad calibration |
| Environmental filtering | Probabilistic hail-realness weighting plus safety floors |
| Event threshold | 25.4 mm / 1 inch |
| Event grouping | ≤1 quiet day, 83 km buffered overlap, 5-day cap, centroid/intensity checks |
| CDF model | Zero-inflated lognormal body + GPD tail |
| GPD ξ | Regionally pooled |
| GPD threshold | Region-specific automated stability selection |
| Spatial smoothing | 150 km pooling radius, 75 km decay |
| Stochastic catalog | 50,000 years, sparse event resampling |
| Stochastic perturbation | Data-calibrated intensity scaling, Gaussian translation, light shape perturbation |
| Physical cap | 250–300 mm depending on stage and use case |
| Vulnerability | Literature-based placeholder MDR curves |

---

## Key Strengths

- Uses radar-based observations rather than human reports as the primary hazard input.
- Maintains a continuous, gridded hazard view over CONUS.
- Uses regional frequency analysis to stabilize extreme-value tails.
- Produces both analytical and stochastic return-period estimates.
- Stores events sparsely, enabling 0.05° resolution without dense event cubes.
- Includes validation, diagnostics, and model-risk indicators required for defensible technical review.

---

## Known Limitations

1. **Long return periods remain uncertain.** A 28-year historical record cannot fully constrain 10,000- or 50,000-year return levels without strong EVT assumptions.
2. **SPC validation is imperfect.** SPC reports are biased and should not be interpreted as complete truth.
3. **Event resampling is not fully generative.** v2.1 adds sparse perturbations but does not create entirely novel storm physics.
4. **Vulnerability is not claims-calibrated.** Stage 14 provides placeholder MDR curves for methodology scaffolding only.
5. **Topography is first-order.** ERA5 melting-layer support improves it, but a full melt model is not implemented.
6. **Spatial dependence is lightweight.** v2.1 avoids computationally expensive max-stable fields; this is appropriate for an incremental update but should be revisited for production vendor-grade modeling.

---

## Recommended Interpretation

Use v2.1 as a transparent, public-data-based hail hazard model suitable for research, portfolio screening, model comparison, and technical exploration. For underwriting or regulatory use, long-return-period outputs should always be accompanied by:

- Stage 06 validation summary.
- Stage 09 GPD threshold diagnostics.
- Stage 13 empirical stochastic RP maps.
- Stage 15 analytical-vs-stochastic divergence plots.
- A clear statement that vulnerability/exposure are not production-calibrated.

---

## Bottom Line

v2.1 strengthens v2.0 without turning it into a new model generation. It preserves the radar-based hazard architecture and sparse event framework while improving statistical defensibility, tail diagnostics, event realism, and reproducibility.
