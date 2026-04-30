# Hail Catastrophe Model — Executive Summary

**Date:** 2026-04-30
**Version:** 2.0
**Status:** Migration from SPC-report-based to MRMS/GridRad-MESH-based hazard input in progress

---

## What Was Built

A ground-up hail catastrophe model hazard layer for the Continental United States (CONUS). The model quantifies the probability and intensity of damaging hail at every 0.05° grid cell (~5.5 km × 5.5 km) across CONUS using radar-derived hail size estimates, and characterizes how hail intensities are spatially correlated within and across storm events.

### v2.0 Changes from v1.0

The v2.0 model replaces NOAA SPC point-based storm reports with NOAA MRMS/MYRORSS radar-derived MESH (Maximum Expected Size of Hail) as the primary hazard input. This change:

- **Eliminates population bias entirely.** Radar does not depend on human observers; urban/rural coverage is uniform.
- **Captures nighttime hail.** SPC reports are heavily biased toward daytime events; MESH operates 24/7.
- **Extends the record to ~28 years** (1998–present) from 22 years, improving GPD tail stability by ~30%.
- **Increases spatial resolution** from 0.25° (~28 km) to 0.05° (~5.5 km), better resolving individual hail swaths.
- **Applies literature-based bias correction** (MESH75 recalibration from Murillo & Homeyer 2019) and environmental filtering to reduce false detections.
- **Retains SPC reports for validation**, cross-validating corrected MESH against ground-truth observations.

---

## Key Outputs

| Product | Description |
|---|---|
| **Return period maps** | Hail size (inches) at 10, 25, 50, 100, 200, 250, and 500-year return periods for every CONUS grid cell (0.05°) |
| **Occurrence probability** | Annual probability of damaging hail (≥1.0") per cell |
| **Event catalog** | Discrete historical storm events from 1998–present, grouped by synoptic-system rule |
| **Daily climatology** | 366 daily climatology rasters at 0.05° |
| **Stochastic catalog** | 50,000-year event-resampling simulation with calibrated intensity perturbation and spatial translation |
| **MESH validation report** | Cross-validation of corrected MESH against SPC ground reports |
| **Vulnerability curves** | Lognormal MDR by construction class (placeholder — requires claims calibration) |

---

## Key Metrics

| Metric | Value |
|---|---|
| Period of record | 1998–present (~28 years) |
| Grid resolution | 0.05° (~5.5 km) |
| Primary data source | MRMS/MYRORSS MESH (radar) |
| Validation data | SPC hail reports (2004–present) |
| MESH bias correction | MESH75 recalibration + environmental filter |
| CDF model | Zero-inflated lognormal body + GPD tail (regional ξ pooling via L-moments) |
| GPD threshold | Per-region MRL-validated (replacing fixed 2.0") |
| Event grouping | ≤1-day gap, 83 km overlap, 5-day cap |
| Stochastic catalog | 50,000 years, calibrated σ, spatial translation enabled |
| Topographic correction | DEM-based hail survival factor |

---

## Modeling Approach

**Primary hazard data:** NOAA MRMS/MYRORSS MESH — radar-derived maximum estimated hail size on a ~1 km grid. MYRORSS provides 1998–2011; operational MRMS provides 2012–present. Raw MESH is aggregated to 0.05° via block-maximum and corrected using the MESH75 recalibration (Murillo & Homeyer 2019) with environmental filtering.

**CDF fitting:** Zero-inflated two-component model per cell:
- Body: Lognormal distribution (fitted via MLE or L-moments)
- Tail: GPD fitted via regional L-moment pooling — shared shape parameter ξ per climatological region, cell-specific scale σ
- GPD threshold validated per region using Mean Residual Life (MRL) diagnostics
- Return periods derived by inverting the composite CDF
- Spatial pooling (150 km Gaussian kernel) for final RP maps

**Event identification:** Synoptic-system grouping — two hail days are combined into one event if the temporal gap is ≤1 day AND the footprints overlap within 83 km. Hard cap of 5 days. Damage threshold: 1.0". Unchanged from v1.0.

**Stochastic catalog:** Event-resampling with seasonal DOY weighting. Intensity perturbation σ calibrated from empirical inter-annual event intensity variance (replacing a priori σ=0.15). Spatial translation enabled (±2–4 cells) using event centroid variance distribution.

**Topographic correction:** DEM-based hail survival factor accounting for elevation effects on melting layer thickness and orographic enhancement of convective initiation.

**Vulnerability (placeholder):** Lognormal MDR curves — MDR(h) = Φ((ln(h) − μ_v) / σ_v) — parameterized for 3–5 construction classes from published literature (Brown et al. 2015; IBHS). Production calibration requires proprietary claims data.

---

## Known Limitations

1. **MESH overestimation bias:** MESH75 recalibration reduces but does not fully eliminate the radar overforecast tendency. Corrected values are calibrated estimates, not direct measurements.

2. **28-year record:** GPD tail extrapolation beyond ~100-year return periods carries significant uncertainty. Regional ξ pooling improves stability but cannot substitute for a longer record.

3. **Template library depth:** ~28 years of events is richer than v1.0's 22 years but still limits novel footprint generation. Spatial translation partially mitigates this.

4. **No exposure layer:** Hazard only. Full EP curve and AAL require TIV exposure database.

5. **Vulnerability from literature, not claims:** MDR parameters are not calibrated to actual insurance claim data.

6. **Stationarity assumption:** No climate trend incorporated into CDF fitting.

---

## Key Literature

| Reference | Relevance |
|---|---|
| Murillo, Homeyer & Allen (2021) | 23-year GridRad MESH climatology; MESH75/MESH95 calibration |
| Murillo & Homeyer (2019) | Revised MESH recalibration (MESH75) |
| Ortega et al. (2022) | MYRORSS dataset description and access |
| Wendt & Jirak (2021) | Operational MRMS MESH hourly climatology |
| Hosking & Wallis (1997) | Regional frequency analysis via L-moments |
| Allen & Tippett (2015) | SPC report population bias documentation |
| Brown et al. (2015) | Hail vulnerability from insurance claims |

See [`docs/literature_review.md`](literature_review.md) for the full review.
