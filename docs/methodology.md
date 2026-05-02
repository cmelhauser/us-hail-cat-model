# Methodology

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Purpose and Scope

The CONUS Hail Catastrophe Model v2.1 constructs a probabilistic hail hazard layer for the continental United States. It uses radar-derived Maximum Expected Size of Hail (MESH) observations rather than human storm reports as the primary hazard input. The model estimates hail occurrence, hail-size frequency, rare-event return periods, and stochastic event behavior on a 0.05° spatial grid.

v2.1 is an incremental hardening of v2.0. It preserves the 15-stage pipeline while improving the weakest technical points:

- source calibration;
- environmental filtering;
- event grouping;
- tail threshold diagnostics;
- sparse stochastic simulation;
- topographic correction;
- validation and diagnostics;
- testability and reproducibility.

The model produces hazard only. It does not include property exposure, policy terms, or claims-calibrated vulnerability.

---

## 2. Modeling Philosophy

The model follows five principles.

### 2.1 Radar-first hazard

SPC hail reports are not used as the primary hazard field because they are affected by population density, road density, report timing, and report-size rounding. Radar-derived MESH provides a spatially continuous view of storms over both populated and rural areas.

### 2.2 Homogeneous grid

All hazard inputs are transformed to a common 0.05° grid. This makes downstream CDF fitting, event construction, and stochastic simulation consistent.

### 2.3 Sparse event representation

Historical events are stored as sparse active-cell arrays. This is essential because a dense event cube over hundreds or thousands of events at 520 × 1180 resolution would be unnecessarily memory intensive.

### 2.4 Dual tail estimation

The model produces two independent rare-event views:

1. analytical EVT return-period maps;
2. empirical return-period maps from stochastic simulation.

Agreement between the two increases confidence. Divergence is a model-risk signal.

### 2.5 Deterministic fallback

Optional ML artifacts may improve calibration or filtering, but the model must run without them. Deterministic logic remains the baseline fallback.

---

## 3. Input Data

### 3.1 MYRORSS

MYRORSS provides historical radar-derived MESH from April 1998 through December 2011. Stage 01 downloads sparse native MYRORSS files, including both plain `.netcdf` and gzipped `.netcdf.gz` archive objects, accumulates daily maximum MESH at native resolution, subsets the CONUS domain, aggregates to 0.05°, and writes daily GeoTIFF files.

Stage 01 also writes a source-coverage manifest. This is important because a daily GeoTIFF with all-zero values can represent two different conditions: no MYRORSS source files existed for that day, or source files existed but contained no valid hail pixels over CONUS. The manifest records this distinction using statuses such as `missing_source`, `no_hail_pixels`, and `ok`; downstream scientific QA should use the manifest rather than inferring source availability from raster values alone.

### 3.2 Operational MRMS

Operational MRMS provides recent MESH data from October 2020 onward. Stage 02 downloads MRMS GRIB2 files, extracts the CONUS subset, flips the native orientation into the common north-to-south grid, accumulates daily maximum values, and writes daily GeoTIFFs.

### 3.3 GridRad and GridRad-Severe

GridRad fills the gap between MYRORSS and operational MRMS. Stage 04b computes Severe Hail Index (SHI) from 3D radar reflectivity profiles and ERA5 freezing-level fields, then converts SHI to MESH75. GridRad-Severe is preferred when available because higher temporal resolution better captures short-lived hail cores.

### 3.4 ERA5

ERA5 provides monthly 0°C and −20°C isotherm heights for SHI computation. v2.1 also allows ERA5-derived variables such as CAPE, relative humidity, or freezing-level height to support conditional calibration and probabilistic filtering.

### 3.5 SPC reports

SPC hail reports are used for validation and calibration support. They are not treated as complete truth. A missing SPC report does not necessarily mean a radar hail signal is false.

### 3.6 DEM

A DEM may be used for Stage 12 topographic correction. If no DEM is present, the model applies a neutral correction factor.

---

## 4. Grid Convention

All primary outputs use:

| Parameter | Value |
|---|---:|
| CRS | EPSG:4326 |
| Resolution | 0.05° |
| Rows | 520 |
| Columns | 1180 |
| Row orientation | north-to-south |
| Column orientation | west-to-east |
| Units | millimeters unless stated otherwise |

MESH is a hail-size estimate. Therefore, aggregation from native grids uses block maximum rather than sum or mean.

---

## 5. Bias Correction and Filtering

### 5.1 MESH75 recalibration

For MYRORSS and MRMS sources that provide Witt-style MESH, the model applies the corrected MESH75 relationship:

```text
MESH75 = 15.096 × (MESH_witt / 2.54)^0.412
```

This converts warning-oriented MESH to a hail-size estimate better suited for climatology and catastrophe modeling.

### 5.2 GridRad calibration

GridRad-derived MESH75 is affected by temporal resolution, reflectivity smoothing, and data-source differences. v2.0 used global quantile mapping. v2.1 preserves quantile mapping as a fallback and supports optional conditional calibration.

Preferred form:

```text
MESH_corrected = f(MESH_raw, CAPE, freezing_level, latitude, month, source)
```

The optional artifact path is:

```text
data/analysis/calibration/gridrad_cqm_model.pkl
```

If this model is absent, Stage 05 uses quantile mapping.

### 5.3 Environmental filtering

v2.0 used hard filters: a noise floor and subtropical winter suppression. v2.1 reframes environmental filtering as probability-weighted:

```text
MESH_final = MESH_corrected × P(hail_real | environment, MESH)
```

Optional artifact path:

```text
data/analysis/calibration/hail_filter_model.pkl
```

Hard thresholds remain safety floors. They prevent tiny residual values from propagating as hail.

### 5.4 Required fallback behavior

Stage 05 must run when optional ML artifacts are absent. `--skip-ml` must force deterministic fallback behavior.

---

## 6. Validation

Stage 06 validates corrected MESH75 against SPC hail reports. Validation should be interpreted as a consistency check, not a definitive truth table.

Core metrics:

- bias by SPC size bin;
- RMSE and MAE;
- probability of detection for severe reports;
- false-alarm proxy, interpreted cautiously;
- diurnal detection comparison;
- spatial bias summaries;
- top-event case reviews.

Recommended v2.1 additions:

- source distribution comparison;
- top 1% radar event review;
- regional validation summaries.

---

## 7. Climatology

Stage 07 computes daily climatology rasters for days 1–366. For each day of year:

```text
climo_DOY = mean(corrected daily MESH75 for that calendar day across all years)
```

Zeros are included because the output represents expected daily activity, not hail size conditional on occurrence.

---

## 8. Event Identification

Stage 08 groups daily hail footprints into events. The damage threshold is 25.4 mm, or 1 inch.

### 8.1 Base grouping

Two active hail days may be grouped if:

1. temporal gap is no more than one quiet day;
2. the previous footprint, dilated by approximately 83 km, overlaps the next footprint;
3. the event duration does not exceed five calendar days.

### 8.2 v2.1 physical coherence checks

Before merging, v2.1 requires:

```text
centroid displacement ≤ 150 km/day
peak intensity ratio ≤ 3×
```

These constraints reduce false merges between unrelated convective systems.

### 8.3 Sparse storage

For each event, Stage 08 stores:

```text
rows_<event_id>
cols_<event_id>
vals_<event_id>
```

The sparse event representation is authoritative for Stage 13.

---

## 9. Frequency-Severity Modeling

Stages 09 and 10 estimate hail-size return periods.

### 9.1 Zero-inflated occurrence model

At each cell:

```text
p_occ = years_with_nonzero_hail / total_years
```

### 9.2 Conditional severity model

Conditional on hail occurrence, the size distribution has:

1. a lognormal body;
2. a GPD tail.

### 9.3 Regional GPD pooling

Individual cells often have too few exceedances for stable tail estimation. The model clusters cells into climatologically similar regions and pools exceedances to estimate a regional GPD shape parameter ξ. Scale may remain cell-specific where possible.

### 9.4 Automated threshold diagnostics

v2.1 requires threshold diagnostics for the GPD splice point. Candidate thresholds are evaluated using:

- exceedance count;
- MRL behavior;
- ξ stability;
- goodness-of-fit score;
- numerical stability.

The output is:

```text
data/analysis/cdf/threshold_selection.csv
```

---

## 10. Spatial Smoothing and Dependence

Stage 10 rebuilds smoothed return-period maps by pooling neighboring annual maxima within a spatial radius using a distance-decay kernel. This reduces noisy cell-level artifacts and produces more coherent hazard gradients.

v2.1 recognizes that independent cell-level tails can understate aggregate risk. It does not implement full max-stable spatial extremes, but it does require diagnostics comparing analytical and stochastic results.

---

## 11. Occurrence Probabilities

Stage 11 computes empirical occurrence probabilities for thresholds:

```text
0.25", 0.50", 1.00", 1.50", 2.00", 3.00", 4.00", 5.00"
```

At each cell:

```text
p_occ(threshold) = years with annual max ≥ threshold / total years
```

These maps are direct empirical summaries and should be used to sanity-check fitted CDF outputs.

---

## 12. CONUS Mask and Topographic Correction

Stage 12 applies a CONUS land mask and a topographic correction.

v2.1 preferred correction:

```text
factor = 1 + α × elevation_km / max(freezing_level_km, ε)
factor = clip(factor, 1.0, 1.25)
```

Fallback correction:

```text
factor = 1 + 0.05 × elevation_km
factor = clip(factor, 1.0, 1.20)
```

If DEM is unavailable, the factor is 1.0.

This remains a first-order hail-survival adjustment, not a full melting model.

---

## 13. Stochastic Catalog

Stage 13 generates a stochastic catalog, normally 50,000 years.

### 13.1 Event frequency

```text
N_events ~ Poisson(λ)
λ = historical_events / historical_years
```

### 13.2 Seasonal sampling

Event days are sampled from a smoothed historical day-of-year distribution.

### 13.3 Template selection

Historical templates are selected using seasonal similarity weights.

### 13.4 Sparse perturbation

v2.1 requires operating directly on sparse arrays:

```text
rows_new = rows + Δrow
cols_new = cols + Δcol
vals_new = vals × scale
```

Intensity scale is lognormal and should be calibrated from historical variation. Spatial translation should be bounded to the model domain. Shape perturbation may add neighboring cells with reduced intensity.

### 13.5 Prohibited production behavior

The stochastic simulation must not reconstruct all templates into a dense cube.

---

## 14. Vulnerability

Stage 14 builds placeholder mean-damage-ratio curves:

```text
MDR(h) = Φ((ln(h) − μ_v) / σ_v)
```

These curves are for demonstration and integration testing. They are not claims-calibrated.

---

## 15. Figures and Diagnostics

Stage 15 renders:

- analytical RP maps;
- stochastic RP maps;
- validation figures;
- event summaries;
- analytical-vs-stochastic comparison;
- vulnerability curves;
- GPD and tail diagnostics.

v2.1 requires analytical-vs-stochastic divergence review for long return periods.

---

## 16. Non-Goals

v2.1 intentionally does not include:

- property-level exposure;
- production loss simulation;
- claims-calibrated vulnerability;
- full spatial max-stable EVT;
- fully generative storm physics;
- non-stationary climate-conditioned tails.

---

## 17. Summary

v2.1 keeps the radar-based v2.0 design and makes it more defensible. The most important practical changes are deterministic fallback safety, sparse-safe stochastic simulation, automated tail diagnostics, and clearer validation requirements.
