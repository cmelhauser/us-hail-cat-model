# Hail Catastrophe Model — Executive Summary

**Version:** 2.2.0 (model); active dev branch `v2.2.1`  
**Status:** Convective-day daily MESH on `main`; full mesh re-ingest required after v2.1 calendar-UTC rasters  
**Primary use:** CONUS hail hazard modeling, stochastic event simulation, validation, and model-risk diagnostics

---

## 1. What Was Built

This project builds a radar-based hail catastrophe hazard layer for the continental United States. It estimates hail occurrence, hail severity, and return-period hail sizes on a 0.05° grid, approximately 5.5 km per cell.

The model uses radar-derived Maximum Expected Size of Hail (MESH) observations from MYRORSS, GridRad / GridRad-Severe, and operational MRMS. These datasets allow the model to estimate hail hazard across both populated and rural areas, including places where human reports are sparse or absent.

SPC reports remain important, but they are used only for validation and calibration support. They are not the primary hazard source because reported hail data are affected by non-meteorological factors including population density, road networks, spotter networks, time of day, and hail-size rounding.

---

## 2. What v2.1 Represents

v2.1 is not a new model generation. It is a hardening release of the v2.0 radar-based architecture.

v2.0 changed the project’s foundation by moving from report-based hail hazard to radar-based hail hazard. v2.1 improves the quality, defensibility, and operational safety of that architecture. It keeps the 15-stage pipeline but improves key areas where methodology or implementation risk could affect results.

The main goal of v2.1 is not to add complexity for its own sake. The goal is to make the model easier to review, safer to run, more transparent, and more defensible.

---

## 2.1 What v2.2 Adds

**v2.2.0** changes how a “daily” hail raster is defined: each `mesh_YYYYMMDD.tif` is the cell-wise maximum over **12 UTC → 12 UTC** (label = date at window start), not UTC calendar midnight. This reduces splitting afternoon convection across two UTC dates and is documented in `docs/methodology.md` §2.6 with literature support in `docs/literature_review.md` §3.6. v2.1 calendar-UTC production GeoTIFFs require full re-ingest from Stages 01, 02, and 04c.

---

## 3. Major v2.1 Improvements

### Bias correction

Stage 05 supports optional conditional GridRad calibration while preserving deterministic quantile-mapping fallback. This reduces the risk of applying a single global correction across meteorologically different regimes.

### Environmental filtering

v2.1 supports optional probabilistic hail-realness filtering. Hard thresholds remain as safety floors, but the preferred approach is to reduce questionable hail signals smoothly rather than removing them abruptly.

### Event grouping

Stage 08 keeps the v2.0 synoptic grouping logic but adds centroid-displacement and intensity-jump checks. These reduce the chance of merging unrelated convective systems into a single event.

### Extreme-value modeling

Stage 09 keeps the lognormal body plus GPD tail framework with regional ξ pooling. v2.1 adds automated GPD threshold diagnostics so tail selection is more auditable.

### Sparse stochastic simulation

Stage 13 is required to operate directly on sparse event arrays. This avoids reconstructing all historical templates as dense event grids and keeps the stochastic simulation memory-safe.

### Topography

Stage 12 can use elevation relative to freezing-level height for a bounded hail-survival correction. If supporting inputs are unavailable, it falls back safely.

### Testing and documentation

v2.1 includes expanded pre-run tests and synchronized documentation so future users and AI agents can understand the model without relying on chat history.

---

## 4. Principal Outputs

The model produces:

- corrected daily MESH75 rasters;
- daily climatology;
- sparse historical event catalog;
- analytical return-period maps;
- spatially smoothed return-period maps;
- occurrence probability rasters;
- stochastic return-period maps;
- occurrence and aggregate probable exceedance tables;
- validation tables and figures;
- placeholder vulnerability curves.

These outputs support hazard analysis, model comparison, portfolio screening, and technical review.

---

## 5. Key Strengths

The main strengths of the v2.1 model are:

1. **Radar-first design** — reduces dependence on biased human reports.
2. **Transparent public-data basis** — no proprietary hazard data are required.
3. **Sparse event storage** — enables high-resolution event simulation without unnecessary memory use.
4. **Regional EVT pooling** — stabilizes rare-event tails where local samples are sparse.
5. **Dual tail estimates** — analytical and stochastic return-period maps can be compared.
6. **Fallback-safe design** — optional ML artifacts improve behavior but are not required.
7. **Reviewable diagnostics** — validation, threshold diagnostics, and analytical/stochastic divergence expose model risk.

---

## 6. Known Limitations

Important limitations remain:

- Long return periods remain extrapolative.
- Spatial dependence is simplified.
- The vulnerability module is not claims-calibrated.
- No exposure layer is included.
- GridRad hourly data may miss short-lived hail peaks when GridRad-Severe is unavailable.
- Climate non-stationarity is diagnostic only and not embedded in the main hazard fit.
- SPC validation data are useful but imperfect.

These limitations do not invalidate the model, but they must be disclosed when outputs are used for underwriting, portfolio analytics, or external communication.

---

## 7. Recommended Use

v2.1 is appropriate for:

- independent hail hazard research;
- comparison with commercial model views;
- portfolio screening;
- sensitivity testing;
- development of exposure and vulnerability extensions;
- technical review of radar-based hail modeling methodology.

For underwriting or regulatory use, the model should be accompanied by:

- Stage 06 validation results;
- Stage 09 threshold diagnostics;
- Stage 13 stochastic maps;
- Stage 15 analytical-vs-stochastic comparisons;
- clear caveats regarding vulnerability and exposure.

---

## 8. Bottom Line

v2.1 preserves the successful radar-based v2.0 architecture and makes it more defensible, testable, memory-safe, and operationally ready. It is a strong transparent hazard-modeling framework, but not yet a complete production loss model.
