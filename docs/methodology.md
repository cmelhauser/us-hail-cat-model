# Methodology

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Overview

The model constructs a probabilistic hail hazard layer for the continental United States using radar-derived Maximum Expected Size of Hail (MESH) observations on a 0.05° grid. The model combines historical radar observations, bias correction, event identification, frequency-severity modeling, spatial pooling, stochastic simulation, and placeholder vulnerability functions.

v2.1 is an incremental methodology update to v2.0. It keeps the 15-stage architecture but improves the most important scientific and implementation risks: cross-source calibration, environmental filtering, event grouping, extreme-value threshold selection, sparse-safe stochastic simulation, topographic correction, and diagnostics.

The methodology has five main phases:

1. **Data acquisition and homogenization** — stages 01–06.
2. **Climatology and event identification** — stages 07–08.
3. **Frequency-severity modeling** — stages 09–12.
4. **Stochastic simulation** — stage 13.
5. **Vulnerability parameterization and reporting** — stages 14–15.

---

## 2. Input Data

### 2.1 MYRORSS

MYRORSS provides historical radar-derived MESH from April 1998 through December 2011. It is based on reprocessed NEXRAD data using the MRMS framework and provides spatially continuous hail estimates. Stage 01 downloads MYRORSS MESH files from public AWS storage, converts sparse native files into daily maximum rasters, and aggregates to the common 0.05° grid using block maximum.

### 2.2 GridRad and GridRad-Severe

GridRad provides 3D composited NEXRAD reflectivity fields during the gap between MYRORSS and operational MRMS. Stage 04b computes SHI from reflectivity profiles using ERA5 0°C and −20°C isotherm heights, then converts SHI to MESH75. GridRad-Severe files are preferred when available because their higher temporal resolution better captures short-lived hail cores.

### 2.3 Operational MRMS

Operational MRMS provides recent MESH products from public AWS storage. Stage 02 downloads operational MESH, accumulates daily maxima at native resolution, and aggregates to the common 0.05° grid.

### 2.4 ERA5

ERA5 provides monthly climatological isotherm heights for SHI computation and supports v2.1 conditional calibration, environmental filtering, and topographic correction. Required variables for the base workflow are 0°C and −20°C isotherm heights. Recommended v2.1 optional variables include CAPE, relative humidity, and additional thermodynamic fields.

### 2.5 SPC Reports

SPC hail reports are retained only for validation and calibration support. They are not used as the primary hazard input because of known population-density, road-network, diurnal, and report-size biases.

---

## 3. Grid and Raster Convention

All primary hazard rasters use the same grid:

| Parameter | Value |
|---|---:|
| CRS | EPSG:4326 |
| Resolution | 0.05° |
| Rows | 520 |
| Columns | 1180 |
| Extent | lon −125.005 to −66.005, lat 24.005 to 50.005 |
| Orientation | north-to-south rows, west-to-east columns |
| Units | millimeters unless otherwise noted |

MESH is a size estimate, not a count. Therefore, aggregation from native radar grids to 0.05° uses block maximum, not sum or mean.

---

## 4. Stage 05 Bias Correction and Environmental Filtering

### 4.1 MESH75 recalibration

For MYRORSS and MRMS sources that provide Witt-style MESH, v2.1 retains the MESH75 conversion:

```text
MESH75 = 15.096 × (MESH_witt / 2.54)^0.412
```

This converts warning-oriented MESH into a more appropriate hail-size estimate for climatology and catastrophe modeling.

### 4.2 GridRad calibration

v2.0 used global quantile mapping to align GridRad to the MYRORSS/MRMS scale. v2.1 keeps this as a fallback but adds a preferred conditional calibration method.

The conditional calibration model estimates corrected hail size as:

```text
MESH_corrected = f(MESH_raw, source, CAPE, freezing_level, latitude, month)
```

Recommended model choices:

1. Gradient boosted regression model for full conditional correction.
2. Quantile regression or conditional quantile mapping where interpretability is preferred.
3. Global quantile mapping as fallback when covariates are missing.

Recommended output:

```text
data/analysis/calibration/gridrad_cqm_model.pkl
data/analysis/calibration/calibration_diagnostics.csv
```

### 4.3 Probabilistic environmental filtering

v2.0 used hard filters such as a 5 mm noise floor and subtropical winter suppression. v2.1 replaces the filter philosophy with a probabilistic hail-realness score:

```text
MESH_final = MESH_corrected × P(hail_real | environment, MESH)
```

Recommended features:

- Corrected MESH.
- CAPE.
- Freezing level height.
- −20°C height.
- Latitude.
- Month or day-of-year.
- Optional RH or shear proxy.

The hard 5 mm floor remains as a safety floor, but it should not be the only environmental filter.

Recommended outputs:

```text
data/analysis/calibration/hail_filter_model.pkl
data/analysis/calibration/hail_filter_diagnostics.csv
```

---

## 5. Validation

Stage 06 validates corrected MESH75 against SPC hail reports. Because SPC reports are incomplete and biased, validation should focus on broad calibration diagnostics rather than treating every unmatched radar signal as a false alarm.

Core validation metrics:

- Bias by SPC report size bin.
- RMSE and MAE.
- Probability of detection for severe hail reports.
- False alarm ratio proxy, interpreted cautiously.
- Diurnal detection comparison.
- Spatial bias summaries.
- Tail-event case study checks for the largest radar events.

v2.1 adds emphasis on:

- Top 1% event validation.
- Regional validation, especially Great Plains, Front Range, Southeast, and Northeast.
- Comparison of corrected MESH distribution by source before and after calibration.

---

## 6. Climatology

Stage 07 computes daily climatology rasters for all 366 calendar days. The climatology supports seasonal diagnostics and stochastic seasonal sampling.

For each day of year:

```text
climo_DOY = mean(daily corrected MESH75 for that DOY across all years)
```

Zeros are included because the climatology represents daily expected activity, not conditional hail size.

---

## 7. Event Identification

Stage 08 identifies discrete hail events using synoptic grouping. v2.1 keeps the existing v2.0 rules but adds physical coherence checks.

### 7.1 Base grouping

Two active hail days can be merged into the same event if:

1. Temporal gap is at most one quiet day.
2. The prior footprint, dilated by approximately 83 km, overlaps the next footprint.
3. Total event duration does not exceed 5 calendar days.

### 7.2 v2.1 physical coherence checks

Before merging two candidate days or groups, v2.1 checks:

```text
centroid displacement ≤ 150 km/day
peak intensity ratio ≤ 3× between adjacent event components
```

These checks reduce physically implausible event merges without requiring a full storm-tracking rewrite.

### 7.3 Sparse event storage

Event peaks are stored as active-cell arrays:

```text
rows_event_id
cols_event_id
vals_event_id
```

This sparse format is the authoritative event representation. Dense reconstruction should be avoided inside simulation loops.

---

## 8. Frequency-Severity Modeling

Stages 09 and 10 fit per-cell hail-size distributions.

### 8.1 Zero-inflated model

Each cell has annual occurrence probability:

```text
p_occ = years_with_hail / total_years
```

Conditional on hail occurrence, hail size follows a two-component distribution:

1. Lognormal body for ordinary events.
2. GPD tail for extremes.

### 8.2 Regional GPD ξ pooling

Because many cells have limited extreme observations, v2.1 retains regional pooling of the GPD shape parameter ξ. Cells are clustered into climatologically similar regions based on mean hail, occurrence probability, latitude, and longitude. ξ is estimated from pooled exceedances, while scale remains cell-specific where possible.

### 8.3 Automated GPD threshold selection

v2.0 used MRL diagnostics to validate a default threshold. v2.1 formalizes threshold selection using an ensemble diagnostic.

For each region, candidate thresholds are scored using:

- Mean Residual Life linearity.
- ξ stability across thresholds.
- KS or Anderson-Darling goodness-of-fit.
- Minimum exceedance count.

Recommended selection rule:

```text
Choose the lowest threshold that satisfies exceedance count, stable ξ, acceptable GOF, and approximately linear MRL behavior.
```

Recommended output:

```text
data/analysis/cdf/threshold_selection.csv
```

Recommended columns:

```text
region, threshold_mm, n_exceedances, xi, sigma, mrl_score, stability_score, gof_score, selected
```

---

## 9. Spatial Pooling and Spatial Dependence

Stage 10 builds spatially pooled CDF maps using neighboring annual maxima within a 150 km radius and an exponential decay kernel.

v2.1 keeps this spatial smoothing but adds model-risk diagnostics for spatial dependence. The key concern is that independent cell-level tails can understate aggregate risk. A lightweight Gaussian-copula option can be added during stochastic sampling, but full max-stable spatial extremes are intentionally out of scope for v2.1.

Recommended v2.1 outputs:

```text
data/analysis/spatial_dependence/correlation_decay.csv
data/analysis/spatial_dependence/copula_params.npz
```

If implemented, copula sampling should be local or regional to avoid constructing large dense covariance matrices.

---

## 10. Occurrence Probabilities

Stage 11 computes annual occurrence probability for standard hail thresholds:

```text
0.25", 0.50", 1.00", 1.50", 2.00", 3.00", 4.00", 5.00"
```

At each cell:

```text
p_occ(threshold) = years with annual max ≥ threshold / total years
```

These maps are direct empirical summaries and should be used as a sanity check against fitted CDF outputs.

---

## 11. CONUS Mask and Topographic Correction

Stage 12 masks outputs to the CONUS land domain and applies topographic correction to return-period maps.

### 11.1 v2.0 method

v2.0 used:

```text
factor = 1 + 0.05 × elevation_km
```

### 11.2 v2.1 method

v2.1 replaces the fixed percent-per-km rule with a hail-survival adjustment tied to freezing level height:

```text
factor = 1 + α × elevation_km / max(freezing_level_km, ε)
factor clipped to [1.0, 1.25]
```

A practical default is:

```text
α = 0.25
```

This keeps the effect modest while making it physically interpretable: higher terrain shortens the warm-layer fall path below the melting level.

If ERA5 freezing level is unavailable, the v2.0 elevation-only correction remains the fallback.

---

## 12. Stochastic Catalog

Stage 13 generates a 50,000-year stochastic event catalog through sparse event resampling.

### 12.1 Event frequency

Annual event count is sampled using:

```text
N_events ~ Poisson(λ)
λ = historical_events / historical_years
```

### 12.2 Seasonal sampling

Simulated event dates are sampled from a smoothed historical day-of-year distribution.

### 12.3 Template selection

Historical event templates are selected using seasonal weights so that May-like events are more likely to generate May-like stochastic events.

### 12.4 Sparse-safe perturbation

v2.1 requires perturbations to operate directly on sparse arrays:

```text
rows, cols, vals = event_sparse
```

Translation:

```text
rows_new = rows + Δrow
cols_new = cols + Δcol
```

Intensity scaling:

```text
vals_new = vals × lognormal(scale_sigma)
```

Shape perturbation:

```text
optionally add neighboring sparse cells with reduced intensity
```

Dense arrays may be used only for final map outputs or small unit tests, not for full event-catalog simulation.

### 12.5 Intensity scaling

v2.1 retains data-calibrated σ but recommends percentile-dependent scaling:

```text
σ_event = 0.10 + 0.15 × event_peak_percentile
```

This allows extreme historical templates to have more tail variability than small events.

### 12.6 Spatial translation

v2.1 replaces uniform ±3-cell shifts with Gaussian displacement:

```text
Δrow, Δcol ~ Normal(0, σ_translation)
```

σ should be calibrated from historical centroid variability and clipped to the domain.

---

## 13. Vulnerability

Stage 14 remains a placeholder vulnerability layer. It builds mean damage ratio curves using a lognormal CDF:

```text
MDR(h) = Φ((ln(h) − μ_v) / σ_v)
```

The curves are useful for demonstration and downstream integration testing but are not production loss curves. Production use requires claims-calibrated vulnerability by roof material, age, region, construction class, and policy/exposure characteristics.

---

## 14. Diagnostics and Reporting

Stage 15 renders maps, curves, and diagnostic plots.

v2.1 required diagnostics:

1. Analytical return-period maps.
2. Stochastic return-period maps.
3. Analytical-vs-stochastic scatter plots.
4. Analytical-vs-stochastic difference maps:

```text
ΔRP = RP_stochastic − RP_analytical
```

5. GPD ξ maps and threshold maps.
6. Threshold stability diagnostics.
7. Validation scatter and detection plots.
8. Event catalog summaries.
9. Vulnerability curves.

Cells with large analytical-vs-stochastic divergence, unstable thresholds, or extreme ξ should be flagged as model-risk areas.

---

## 15. Non-Goals for v2.1

v2.1 deliberately avoids:

- Full max-stable spatial extremes.
- Deep learning hail correction.
- Fully generative storm physics.
- Claims-calibrated vulnerability.
- Property-level exposure modeling.
- Replacing the 15-stage pipeline.

These are possible future v3.0 directions, but they are not needed for a defensible v2.1 methodology hardening.

---

## 16. Summary

v2.1 keeps the successful radar-based design of v2.0 and improves the weak points most likely to matter in technical review:

- Conditional source calibration.
- Probabilistic filtering.
- Event-merge sanity checks.
- Automated tail-threshold selection.
- Sparse-safe stochastic simulation.
- Physically motivated topographic adjustment.
- Tail and stochastic divergence diagnostics.

The result is a more transparent, robust, and reviewable hail hazard engine.
