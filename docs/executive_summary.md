# Hail Catastrophe Model — Executive Summary

**Version:** 2.0  |  **Date:** 2026-04-30  |  **Status:** Stages 01–06 complete; stages 07–15 in progress

---

## What Was Built

A ground-up hail catastrophe model hazard layer for CONUS. Quantifies the probability and intensity of damaging hail at every 0.05° grid cell (~5.5 km) using ~28 years of radar-derived hail size estimates from three sources: MYRORSS (1998–2011), GridRad (2012–2019), and operational MRMS (2020–present).

## Key Changes from v1.0

- **Radar-based input replaces SPC reports.** Eliminates population bias, captures nighttime hail, provides uniform spatial coverage.
- **~28 years of continuous record** from three cross-calibrated radar sources.
- **0.05° grid** (~5.5 km) resolves individual hail swaths.
- **MESH75 recalibration** using corrected Murillo & Homeyer (2021) coefficients.
- **ERA5 gridded freezing levels** for accurate SHI computation in the GridRad gap-fill.
- **Quantile-mapping cross-calibration** aligns GridRad to MYRORSS using the 2005–2011 overlap.
- **SPC reports retained for validation** — not primary input.

## Data Architecture

```
data/historical/    ← Radar downloads, corrected MESH, climatology, events, validation
data/analysis/      ← CDF parameters, calibration, occurrence, topography, vulnerability
data/stochastic/    ← 50,000-yr catalog, return period maps, EP tables
```

## Pipeline (15 stages)

01–03: Data acquisition (MYRORSS, MRMS, SPC)  →  04a–04b: ERA5 isotherms + GridRad gap fill  →  05: Unified bias correction  →  06: Validation  →  07: Climatology  →  08: Event catalog  →  09–10: CDF fitting  →  11–12: Occurrence + masking  →  13: Stochastic catalog  →  14: Vulnerability  →  15: Figures

## Key Parameters

| Parameter | Value |
|---|---|
| Grid resolution | 0.05° (~5.5 km), 520 × 1180 cells |
| Record period | 1998–present (~28 years) |
| MESH calibration | MESH75 = 15.096 × SHI^0.206 |
| CDF model | Zero-inflated lognormal + GPD tail (regional ξ pooling) |
| Event grouping | ≤1-day gap, 83 km overlap, 5-day cap |
| Stochastic catalog | 50,000 years, calibrated σ, spatial translation |

## Known Limitations

1. MESH75 does not fully eliminate radar overforecast tendency
2. GridRad hourly resolution misses short-lived peaks (corrected statistically)
3. 28-year record limits tail extrapolation beyond ~100-year RP
4. Event-resampling cannot generate novel footprint geometries
5. Vulnerability curves from literature, not claims-calibrated
6. No exposure layer (hazard only)

## Key Literature

Murillo, Homeyer & Allen (2021); Murillo & Homeyer (2019/2021 corrigendum); Ortega et al. (2022); Wendt & Jirak (2021); Hosking & Wallis (1997); Allen & Tippett (2015); Brown et al. (2015). See `literature_review.md`.
