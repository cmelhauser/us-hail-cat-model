# Methodology

**CONUS Hail Catastrophe Model v2.1**

---

## Abstract

The CONUS Hail Catastrophe Model v2.1 is a radar-first probabilistic hail hazard model for the continental United States. It estimates daily hail occurrence, hail-size severity, rare-event return levels, spatially coherent event footprints, and long synthetic event catalogs on a 0.05 degree latitude-longitude grid. The model is designed for hazard research, scenario analysis, and catastrophe-model prototyping. It is not a claims-calibrated loss model.

The central methodological choice is to use radar-derived Maximum Expected Size of Hail (MESH) fields as the primary hazard observation, while reserving SPC hail reports for validation and calibration support. That choice reflects the well-documented non-meteorological bias in human hail reports, including population density, road density, observation practices, report-size rounding, and historical changes in severe-hail reporting thresholds (Allen and Tippett 2015; Blair et al. 2011, 2017). Radar products have their own uncertainties, but they provide spatially continuous observations over rural and urban domains and are therefore better suited to gridded hazard estimation.

v2.1 is a hardening release rather than a full redesign. It preserves the 15-stage architecture while improving source provenance, deterministic fallback behavior, event grouping, tail diagnostics, sparse stochastic simulation, and documentation traceability.

---

## 0. Notation Glossary

This glossary defines symbols and abbreviations used throughout the document. Variable names in code blocks match these definitions unless a local alias is noted.

### Grid and indexing

| Symbol | Definition |
|--------|-----------|
| `i`, `j` | Row (N→S) and column (W→E) index of a 0.05° grid cell |
| `d` | Calendar day index (integer) |
| `doy` | Day-of-year (1–366) |
| `y` | Year index |
| `NROWS` | 520 — number of grid rows |
| `NCOLS` | 1180 — number of grid columns |
| `DX` | 0.05° — grid cell size (~5.5 km) |

### Hazard variable

| Symbol | Definition |
|--------|-----------|
| `H`, `h` | Hail size (mm); `H` is the random variable, `h` a specific value |
| `MESH` | Maximum Expected Size of Hail (Witt et al. 1998) |
| `MESH75` | Corrected MESH calibrated to the 75th-percentile surface-hail relationship (Murillo & Homeyer 2021) |
| `SHI` | Severe Hail Index — intermediate computation from 3-D reflectivity and ERA5 isotherms, used in GridRad processing |
| `MESH_witt` | Raw MESH in the original Witt et al. (1998) formulation |
| `MESH_corrected` | MESH75 after Stage 05 bias correction and environmental filtering |

### Occurrence and frequency

| Symbol | Definition |
|--------|-----------|
| `p_occ(i,j)` | Annual exceedance probability at cell (i,j): fraction of years with nonzero severe hail |
| `active(i,j,d)` | Indicator: 1 if `MESH75_corrected(i,j,d) ≥ 25.4 mm`, else 0 |
| `climo_doy(i,j)` | Mean MESH75 for a given day-of-year at cell (i,j), averaged across all years |
| `λ` | Mean annual event count (Poisson rate for stochastic simulation) |

### Extreme value and return periods

| Symbol | Definition |
|--------|-----------|
| `F_positive(h)` | CDF of hail size conditional on occurrence |
| `u` | GPD threshold (mm); default 50.8 mm (2 inches) |
| `x` | Exceedance above threshold: `x = h − u` |
| `ξ` (xi) | GPD shape parameter (dimensionless); controls tail heaviness |
| `σ` (sigma) | GPD scale parameter (mm) |
| `T` | Return period (years) |
| `RP_T` | Return-period hail size at return period `T` (mm) |

### Stochastic catalog

| Symbol | Definition |
|--------|-----------|
| `σ_perturb` | Global intensity perturbation parameter: median monthly CV (Mar–Sep), clipped to [0.10, 0.40] |
| `σ_event` | Per-event perturbation SD, scaled by event peak percentile; clipped to [0.10, max(0.25, σ_perturb)] |
| `scale` | Lognormal multiplicative intensity factor applied to each simulated event |
| `Δrow`, `Δcol` | Integer spatial translation applied to sparse event arrays; drawn from Normal(0, `TRANSLATE_CELLS`²) |
| `TRANSLATE_CELLS` | 3 cells (≈ 16.5 km) — SD of spatial translation |
| `N_SIM_YEARS` | 50,000 — stochastic catalog length (years) |

### Topographic correction

| Symbol | Definition |
|--------|-----------|
| `factor` | Multiplicative topographic correction applied to return-period maps |
| `α` (alpha) | Correction coefficient; 0.25 (freezing-level-aware form) or 0.05 (fallback km⁻¹) |
| `elevation_km` | Cell elevation in km above sea level (from 0.05° DEM) |
| `freezing_level_km` | ERA5 monthly 0°C isotherm height in km above sea level |

### Vulnerability

| Symbol | Definition |
|--------|-----------|
| `MDR(h)` | Mean damage ratio at hail size `h` — fraction of replacement value expected to be damaged |
| `μ_v` | Log-scale location parameter of the lognormal MDR curve; `exp(μ_v)` ≈ median-damage hail size |
| `σ_v` | Log-scale dispersion parameter of the lognormal MDR curve |
| `Φ` | Standard normal CDF |

### Data sources and abbreviations

| Abbreviation | Definition |
|-------------|-----------|
| MYRORSS | Multi-Year Reanalysis of Remotely Sensed Storms — radar reanalysis, Apr 1998–Dec 2011 |
| GridRad | Three-dimensional radar analysis from NCAR — gap-fill source, Jan 2012–Oct 2019 |
| MRMS | Multi-Radar Multi-Sensor — operational NOAA product, Oct 2020–present |
| ERA5 | ECMWF Reanalysis v5 — monthly 0°C / −20°C isotherms |
| SPC | Storm Prediction Center — hail reports used for validation only |
| CONUS | Continental United States |
| DEM | Digital Elevation Model |
| GPD | Generalized Pareto Distribution |
| EVT | Extreme Value Theory |
| MDR | Mean Damage Ratio |
| CV | Coefficient of Variation (σ/μ) |
| KS | Kolmogorov–Smirnov (goodness-of-fit test) |
| MRL | Mean Residual Life (GPD threshold diagnostic) |
| RP | Return Period |
| PET | Probable Event Table |

---

## 1. Scientific Scope

The model estimates hazard, not loss. A complete insurance catastrophe model would contain:

1. an event occurrence model;
2. an event intensity and footprint model;
3. a stochastic event set;
4. an exposure model;
5. vulnerability curves;
6. financial terms;
7. uncertainty propagation.

v2.1 implements the first three elements and provides placeholder vulnerability curves for integration testing only. It does not include property exposure, policy conditions, claims-calibrated vulnerability, demand surge, repair-cost inflation, or portfolio aggregation. Any loss interpretation should therefore be treated as illustrative.

The spatial domain is CONUS and the target hazard variable is hail size in millimeters, represented as MESH75 where possible. MESH75 is interpreted as a radar-derived estimate of the 75th percentile of observed maximum hail size conditional on the storm and radar retrieval, following the corrected MESH relationships in the Murillo and Homeyer literature.

---

## 2. Modeling Philosophy

### 2.1 Radar-first hazard field

SPC and Storm Data hail reports are indispensable historical records, but they are not an unbiased sampling device. Reports depend on where people are present, where road networks permit observation, how spotters estimate size, how reports are filtered operationally, and how warning criteria changed through time. Report data are therefore suitable for validation, calibration support, and qualitative comparison, but not as the primary gridded hazard field.

Radar-derived MESH is also imperfect. It is sensitive to radar calibration, beam height, range, vertical sampling, hydrometeor classification, and empirical MESH-to-hail-size relationships. The advantage is that these errors are more directly physical and can be diagnosed as measurement and algorithmic uncertainty. The model therefore treats radar as the primary spatial hazard measurement and reports as a partial, biased observation of surface outcomes.

### 2.2 Common grid and reproducible transformations

All daily products are transformed to a common 520 x 1180 grid at 0.05 degree resolution in EPSG:4326. This is coarse enough to keep multi-decade processing tractable but fine enough to preserve mesoscale hail corridors and event footprints. Because hail is a local maximum process rather than an additive quantity, all spatial aggregation from native grids uses block maximum:

```text
MESH_0.05(i, j) = max(MESH_native cells inside output cell i, j)
```

A mean would dilute compact hail cores; a sum would be physically meaningless for hail size.

### 2.3 Sparse event representation

Most cells are inactive for most events. Stage 08 therefore stores each event as sparse active-cell vectors:

```text
rows_event, cols_event, vals_event
```

This is not an implementation convenience; it is part of the model definition. The stochastic catalog must perturb and resample sparse events without reconstructing the entire historical event library as dense 520 x 1180 rasters. Dense annual maxima may be used where necessary for final return-period maps, but event templates themselves remain sparse.

### 2.4 Dual tail estimation

The model produces two complementary views of rare hail size:

1. analytical return-period maps from a zero-inflated body-tail severity model;
2. empirical return-period maps from a long stochastic event catalog.

These outputs are intentionally redundant. Agreement between them increases confidence that the fitted marginal tails and the event-resampling process are mutually consistent. Divergence is a model-risk signal requiring manual review, especially at 1,000-year and longer return periods.

### 2.5 Fallback safety

Optional machine-learning artifacts may improve calibration or environmental filtering, but they are not required for a valid run. The model must remain executable with deterministic logic under `--skip-ml`. This protects reproducibility and prevents undeclared binary artifacts from becoming hidden dependencies.

---

## 3. Data Sources and Their Roles

### 3.1 MYRORSS historical radar reanalysis

MYRORSS provides the early radar backbone from April 1998 through December 2011. The archive contains sparse radar-derived NetCDF objects at high temporal frequency and supports a spatially continuous historical hail field. Stage 01 reads both plain `.netcdf` and gzipped `.netcdf.gz` archive objects, accumulates native daily maximum MESH, subsets CONUS, aggregates by block maximum, and writes daily GeoTIFFs.

Stage 01 also writes:

```text
data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv
```

This manifest is a scientific data product. It records whether each day had missing source files, valid source files with no hail pixels, valid source files with active cells, or read errors. An all-zero GeoTIFF alone cannot distinguish a meteorologically quiet day from a missing-source day; the manifest carries that distinction.

### 3.2 Operational MRMS

MRMS supplies the recent operational era from October 2020 onward. It provides national multi-radar products with consistent gridded severe-weather fields. Stage 02 extracts MESH GRIB2 products, handles native orientation and longitude conventions, computes daily maxima, and writes the same 0.05 degree GeoTIFF format used by MYRORSS.

MRMS is not assumed identical to MYRORSS. Differences in processing chain, radar network state, temporal update frequency, quality control, and algorithm evolution can create source-transition artifacts. v2.1 addresses those artifacts through Stage 05 calibration and Stage 06 source diagnostics.

### 3.3 GridRad and GridRad-Severe

GridRad fills the gap between MYRORSS and operational MRMS. Stage 04b computes Severe Hail Index (SHI) from three-dimensional radar reflectivity and ERA5 isotherm fields, then converts SHI to MESH75. GridRad-Severe is preferred where available because higher temporal sampling better resolves short-lived hail cores.

GridRad-derived hail estimates are treated as a gap-fill source, not as automatically homogeneous with MYRORSS or MRMS. The model therefore applies source-specific calibration and requires transition diagnostics.

### 3.4 ERA5 environmental fields

ERA5 supplies 0 C and -20 C isotherm heights for SHI computation and may supply environmental covariates such as CAPE, relative humidity, freezing-level height, and seasonal indicators for optional conditional calibration or filtering. Monthly isotherm fields are a pragmatic compromise. They reduce data volume and provide climatological thermodynamic context, but they do not resolve storm-hour variability.

### 3.5 SPC hail reports

SPC reports are used for validation, source sanity checks, and qualitative review. They are not used as the complete truth table. A report without radar hail may indicate radar underestimation, spatial mismatch, timing mismatch, or report error. A radar hail signal without an SPC report may indicate underreporting, rural occurrence, timing, or a false radar signature. Validation must keep both possibilities open.

### 3.6 DEM and terrain information

Terrain affects hail environments through orographic lifting, boundary-layer structure, freezing-level-relative melting depth, and storm initiation. Stage 12 uses DEM information for a bounded topographic correction. This is a first-order empirical adjustment, not a microphysical hail-melting model.

---

## 4. Grid Convention

All primary gridded outputs use:

| Parameter | Value |
|---|---:|
| CRS | EPSG:4326 |
| Resolution | 0.05 degree x 0.05 degree |
| Rows | 520 |
| Columns | 1180 |
| Total cells | 613,600 |
| Row orientation | north-to-south |
| Column orientation | west-to-east |
| Units | millimeters unless stated otherwise |
| Standard raster dtype | float32 |

The grid convention is a versioned model assumption. Changing resolution, extent, orientation, or coordinate reference system requires downstream regeneration and should be treated as a new model version.

---

## 5. Hail-Size Calibration and Environmental Filtering

### 5.1 MESH and MESH75

The original MESH formulation was designed for operational hail detection and warning support. Catastrophe modeling requires a climatologically stable size estimate, so v2.1 converts Witt-style MESH products to corrected MESH75 where applicable:

```text
MESH75 = 15.096 * (MESH_witt / 2.54)^0.412
```

This conversion is empirical and carries residual error. It should be understood as a calibrated radar-size estimator, not a direct observation of every surface hailstone.

### 5.2 GridRad calibration

GridRad-derived MESH75 is affected by temporal sampling, vertical reflectivity structure, and source differences. v2.1 supports conditional calibration:

```text
MESH_corrected = f(MESH_raw, CAPE, freezing_level, latitude, longitude, month, source)
```

The preferred optional artifact is:

```text
data/analysis/calibration/gridrad_cqm_model.pkl
```

If unavailable, Stage 05 uses deterministic quantile mapping. This fallback is intentionally conservative: it aligns source distributions without requiring an opaque model artifact.

### 5.3 Environmental filtering

Small radar-derived hail signatures can reflect noise, bright band contamination, marginal severe-hail environments, or hydrometeors unlikely to survive to the ground. v2.1 frames filtering probabilistically:

```text
MESH_final = MESH_corrected * P(hail_real | environment, MESH_corrected)
```

The optional artifact is:

```text
data/analysis/calibration/hail_filter_model.pkl
```

If absent, Stage 05 applies deterministic safety floors. The deterministic path is not a second-class mode; it is the reproducible baseline. Hard filters are deliberately simple and should be reviewed as part of the uncertainty budget.

### 5.4 Source homogeneity

The final corrected daily archive combines MYRORSS, GridRad, and MRMS. The model assumes that Stage 05 reduces source-transition artifacts enough for pooled tail estimation. Stage 06 diagnostics should check this assumption through source-stratified distributions, regional summaries, and top-event review. Any visible discontinuity at 2012 or 2020 should be treated as a first-order model risk.

---

## 6. Validation Framework

Stage 06 validates corrected MESH75 against SPC reports. The purpose is not to produce a binary confusion matrix against perfect truth. Instead, validation asks whether the radar climatology is consistent with independent observations after allowing for known report incompleteness.

Core diagnostics include:

- size-bin bias by SPC report magnitude;
- RMSE, MAE, and robust median absolute error;
- probability of detection by threshold and region;
- false-alarm proxy, labelled explicitly as a proxy;
- diurnal and seasonal consistency;
- spatial bias at coarse resolution;
- source-era comparisons;
- review of the top 1 percent radar events;
- case review for extreme or spatially suspicious days.

Validation outputs should be interpreted alongside the literature on report bias and radar retrieval error. A perfect match to reports would be suspicious because reports are not spatially complete. Conversely, broad mismatch, severe regional drift, or systematic source-era differences indicate a calibration issue.

---

## 7. Daily and Annual Climatology

Stage 07 computes day-of-year climatology:

```text
climo_doy(i, j) = mean_y[MESH75_corrected(y, doy, i, j)]
```

Zeros are included because the climatology estimates expected daily hail activity, not hail size conditional on occurrence. This distinction matters: conditional hail size answers "how large when hail occurs"; expected daily activity answers "what average daily hazard is present at this place and season." The latter is the appropriate diagnostic for seasonal gradients and source continuity.

Leap day is represented explicitly as day 366. Downstream smoothing or calendar-day comparisons should handle day 366 rather than silently dropping it.

---

## 8. Event Identification

Stage 08 converts daily rasters into event footprints. The model uses a 25.4 mm damage threshold:

```text
active(i, j, d) = 1 if MESH75_corrected(i, j, d) >= 25.4 mm
```

### 8.1 Base merge rules

Two active days may be grouped into one event when:

1. the temporal gap is no more than one quiet day;
2. the previous footprint, dilated by the configured spatial buffer, overlaps the next footprint;
3. the total event duration does not exceed five calendar days.

These rules approximate the continuity of synoptic and mesoscale convective systems while preventing multi-week active periods from collapsing into one event.

### 8.2 Physical coherence checks

v2.1 adds two coherence checks before merging:

```text
centroid displacement <= 150 km/day
peak intensity ratio <= 3
```

The centroid constraint limits merges between unrelated storms that happen to occur in broad regional proximity. The intensity-ratio constraint reduces merges where a weak remnant and an independent intense system are connected only by a marginal footprint bridge.

### 8.3 Event representation

For each event, Stage 08 stores a sparse event peak field:

```text
rows_event_id
cols_event_id
vals_event_id
```

The event peak is the maximum hail size at each active cell during the event. Duration, start/end date, maximum size, active-cell count, and other event metadata are recorded in `event_catalog.csv`.

---

## 9. Frequency-Severity Modeling

Stages 09 and 10 estimate return-period hail sizes. The marginal model is zero-inflated because most cell-years have no severe hail:

```text
P(H = 0) = 1 - p_occ
P(H <= h | H > 0) = F_positive(h)
```

where:

```text
p_occ(i, j) = years_with_nonzero_hail(i, j) / total_years
```

### 9.1 Body-tail distribution

Conditional positive hail sizes are represented by:

1. a lognormal body;
2. a generalized Pareto distribution (GPD) tail above threshold `u`.

For exceedance `x = h - u`, the GPD survival function is:

```text
P(X > x | X > 0) = (1 + xi * x / sigma)^(-1 / xi), xi != 0
P(X > x | X > 0) = exp(-x / sigma), xi = 0
```

This peaks-over-threshold structure is justified by extreme value theory, but only asymptotically. The threshold must be high enough for the GPD approximation to be credible and low enough to retain adequate sample size. That bias-variance tradeoff is one of the most important uncertainty sources in the model.

### 9.2 Regional tail pooling

Cell-level exceedance counts are often too small for stable GPD shape estimation. v2.1 clusters cells into climatologically similar pooling regions using features such as mean hail, occurrence probability, latitude, and longitude. Within each region, exceedances are pooled to estimate a shared GPD shape parameter `xi`; scale can remain cell-specific where data permit.

This follows the logic of regional frequency analysis: sacrifice some local independence to gain stable tail parameters under an assumption of approximate regional homogeneity. The assumption should be checked through regional diagnostics and sensitivity to the number of regions.

### 9.3 Threshold diagnostics

Stage 09 writes:

```text
data/analysis/cdf/threshold_selection.csv
```

Candidate thresholds are evaluated using:

- exceedance count;
- mean residual life behavior;
- stability of `xi`;
- goodness-of-fit score;
- numerical stability;
- selected-flag audit trail.

Long return periods are extrapolations from a short radar record. Even if the fitted maps are smooth and monotonic, uncertainty grows rapidly for 1,000-year and longer return periods.

---

## 10. Spatial Smoothing and Dependence

Stage 10 rebuilds smoothed return-period maps by pooling neighboring annual maxima with distance-decay weights. The purpose is to reduce sampling artifacts in cell-level CDFs and produce spatially coherent hazard gradients.

This is not a full spatial extremes model. It smooths marginal return levels but does not explicitly estimate an extremal dependence function, max-stable process, or tail-dependence copula. Therefore, smoothed maps should be interpreted as improved marginal hazard surfaces, not as a complete model of joint spatial extremes.

The analytical-vs-stochastic comparison in Stage 15 partly addresses this limitation. If stochastic event maps differ substantially from smoothed analytical maps, either the marginal tails, event resampling, or spatial smoothing assumptions require review.

---

## 11. Empirical Occurrence Probabilities

Stage 11 computes empirical occurrence probabilities for fixed thresholds:

```text
0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00 inches
```

At each cell:

```text
p_occ(threshold) = count(years with annual max >= threshold) / total_years
```

These maps are intentionally simple. They are not tail extrapolations and should be used as empirical sanity checks for fitted return-period products. Higher thresholds must have lower or equal occurrence probability than lower thresholds at every cell.

---

## 12. CONUS Mask and Topographic Correction

Stage 12 applies a CONUS land mask and a bounded topographic correction. The preferred form is freezing-level-aware:

```text
factor = 1 + alpha * elevation_km / max(freezing_level_km, epsilon)
factor = clip(factor, 1.0, 1.25)
```

Fallback form:

```text
factor = 1 + 0.05 * elevation_km
factor = clip(factor, 1.0, 1.20)
```

If no DEM is available, the factor is `1.0`. The correction is deliberately bounded because hail survival, melting, and terrain effects are nonlinear and not resolved by this simple adjustment. It should be treated as a first-order terrain-context correction and tested in sensitivity analysis before high-stakes interpretation in complex terrain.

---

## 13. Stochastic Catalog

Stage 13 generates a stochastic catalog, normally 50,000 years, using historical sparse event templates.

### 13.1 Event frequency

The annual event count is sampled as:

```text
N_events ~ Poisson(lambda)
lambda = historical_events / historical_years
```

This assumes independent annual counts with variance equal to the mean. Severe-convective activity can be overdispersed because active synoptic regimes cluster in time. The Poisson model is therefore a transparent baseline. A future negative-binomial extension should be considered if the observed index of dispersion materially exceeds one.

### 13.2 Seasonal occurrence

Event day-of-year is drawn from a smoothed wrapped historical day-of-year distribution. The implementation smooths the empirical 366-day histogram with a Gaussian kernel and wraps the endpoints so that late December and early January remain adjacent.

### 13.3 Template selection

Historical templates are sampled with seasonal similarity weights:

```text
weight(template) proportional to exp(-abs(doy_sim - doy_template) / 30)
```

This preserves the observed seasonality of hail regimes while allowing stochastic variation across the catalog.

### 13.4 Intensity perturbation

The implementation calibrates the global intensity perturbation parameter from historical event peaks:

```text
CV_month = std(event_peak_mm in month) / mean(event_peak_mm in month)
sigma_perturb = median(CV_month for March through September with >= 10 events)
sigma_perturb = clip(sigma_perturb, 0.10, 0.40)
```

During simulation, each event receives a lognormal scale factor. The code uses a percentile-aware event sigma:

```text
sigma_event = clip(0.10 + 0.15 * event_peak_percentile, 0.10, max(0.25, sigma_perturb))
scale = exp(sigma_event * Z), Z ~ Normal(0, 1)
hail_new = hail_template * scale
```

Values are capped by a physical ceiling in the implementation. This approach keeps weak events from receiving unrealistically large relative perturbations while allowing stronger historical templates to express more tail variability.

### 13.5 Sparse translation and shape perturbation

Spatial translation is applied directly to sparse arrays:

```text
rows_new = rows + Delta_row
cols_new = cols + Delta_col
```

where `Delta_row` and `Delta_col` are Gaussian integer shifts with standard deviation `TRANSLATE_CELLS = 3`, clipped to the model domain. A light sparse shape perturbation may add a one-cell neighbor shell at reduced intensity. The event library is never expanded into a dense event cube.

### 13.6 Empirical return periods

For each simulated year, annual maxima are updated on the compact active-cell index. Empirical return-period maps are then estimated from the simulated annual maxima. These maps are independent of the GPD tail fit and therefore useful as an out-of-sample structural diagnostic.

---

## 14. Vulnerability Placeholder

Stage 14 constructs illustrative mean-damage-ratio curves:

```text
MDR(h) = Phi((ln(h) - mu_v) / sigma_v)
```

These curves are literature-informed priors for demonstration and integration testing. They are not calibrated to insurance claims. Production vulnerability modeling would require claims, exposure attributes, roof material, age, construction class, repair-cost normalization, deductibles, limits, and a formal validation framework.

---

## 15. Figures and Diagnostics

Stage 15 renders:

- analytical return-period maps;
- stochastic return-period maps;
- validation figures;
- event summaries;
- analytical-vs-stochastic comparison;
- vulnerability curves;
- GPD and tail diagnostics.

Figure review is a required scientific QA step. Maps should be checked for source-transition artifacts, grid-orientation errors, excessive smoothing, physically implausible gradients, boundary artifacts, and unexpected maxima outside known hail corridors. Analytical-vs-stochastic divergence at long return periods should be recorded, not waved away.

---

## 16. Uncertainty and Limitations

The major uncertainty categories are:

- measurement uncertainty in radar reflectivity and MESH retrievals;
- algorithmic uncertainty from source processing, calibration, filtering, and aggregation;
- sampling uncertainty from the short radar record;
- model uncertainty from GPD threshold, regional pooling, smoothing, and stationarity assumptions;
- stochastic uncertainty from event-count and perturbation assumptions;
- vulnerability uncertainty because Stage 14 is not claims-calibrated.

The model is stationary. It does not condition the tail distribution on climate covariates or future climate scenarios. Trend diagnostics are recommended, but v2.1 does not force non-stationarity into the tail model because the homogeneous radar record is short for long-return-period estimation.

---

## 17. Non-Goals

v2.1 intentionally does not implement:

- property-level exposure;
- production financial loss simulation;
- claims-calibrated vulnerability;
- full spatial max-stable EVT;
- a generative storm-dynamics model;
- non-stationary climate-conditioned tails;
- uncertainty intervals on every return-period map.

These are valid future directions, but they are outside the scope of this hardening release.

---

## 18. References

Allen, J. T. and M. K. Tippett, 2015: The characteristics of United States hail reports: 1955-2014. *Electronic Journal of Severe Storms Meteorology*, 10(3), 1-31.

Allen, J. T., M. K. Tippett, and A. H. Sobel, 2015: An empirical model relating U.S. monthly hail occurrence to large-scale meteorological environment. *Journal of Advances in Modeling Earth Systems*, 7(1), 226-243.

Andrews, M. S., and coauthors, 2024: Climatology of the elevated mixed layer over the contiguous United States and Northern Mexico using ERA5: 1979-2021. *Journal of Climate*, 37, 1833-1851.

Balkema, A. A. and L. de Haan, 1974: Residual life time at great age. *Annals of Probability*, 2(5), 792-804.

Blair, S. F., et al., 2011: A radar-based assessment of the detectability of giant hail. *Electronic Journal of Severe Storms Meteorology*, 6(7), 1-30.

Blair, S. F., et al., 2017: High-resolution hail observations: implications for NWS warning operations. *Weather and Forecasting*, 32, 1101-1119.

Bringi, V. N. and V. Chandrasekar, 2001: *Polarimetric Doppler Weather Radar: Principles and Applications.* Cambridge University Press.

Brown, T. M., et al., 2015: Evaluating hail damage using property insurance claims data. *Weather, Climate, and Society*, 7(3), 197-210.

Coles, S., 2001: *An Introduction to Statistical Modeling of Extreme Values.* Springer.

Cooley, D., D. Nychka, and P. Naveau, 2007: Bayesian spatial modeling of extreme precipitation return levels. *Journal of the American Statistical Association*, 102(479), 824-840.

Davison, A. C., S. A. Padoan, and M. Ribatet, 2012: Statistical modeling of spatial extremes. *Statistical Science*, 27(2), 161-186.

Gneiting, T., A. E. Raftery, A. H. Westveld III, and T. Goldman, 2005: Calibrated probabilistic forecasting using ensemble model output statistics and minimum CRPS estimation. *Monthly Weather Review*, 133(5), 1098-1118.

Grossi, P. and H. Kunreuther, 2005: *Catastrophe Modeling: A New Approach to Managing Risk.* Springer.

Hosking, J. R. M. and J. R. Wallis, 1997: *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press.

Li, F., D. R. Chavas, K. A. Reed, N. Rosenbloom, and D. T. Dawson, 2021: The role of elevated terrain and the Gulf of Mexico in the production of severe local storm environments over North America. *Journal of Climate*, 34, 7799-7819.

Miralles, O., A. C. Davison, and T. Schmid, 2023: Bayesian modeling of insurance claims for hail damage. *arXiv:2308.04926*.

Mitchell-Wallace, K., M. Jones, J. Hillier, and M. Foote, 2017: *Natural Catastrophe Risk Management and Modelling: A Practitioner's Guide.* Wiley.

Murillo, E. M. and C. R. Homeyer, 2019: Severe hail fall and hailstorm detection using remote sensing observations. *Journal of Applied Meteorology and Climatology*, 58, 947-970; corrigendum and corrected MESH relationships.

Murillo, E. M., C. R. Homeyer, and J. T. Allen, 2021: A 23-year severe hail climatology using GridRad MESH observations. *Monthly Weather Review*, 149, 945-958.

Ortega, K. L., 2018: Evaluating multi-radar, multi-sensor products for surface hailfall estimation. *Electronic Journal of Severe Storms Meteorology*, 13(1), 1-36.

Pickands, J., 1975: Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119-131.

Rasmussen, R. M. and A. J. Heymsfield, 1987: Melting and shedding of graupel and hail. *Journal of the Atmospheric Sciences*, 44, 2754-2763.

Scarrott, C. and A. MacDonald, 2012: A review of extreme value threshold estimation and uncertainty quantification. *REVSTAT*, 10(1), 33-60.

Smith, T. M., et al., 2016: Multi-Radar Multi-Sensor severe weather and aviation products: initial operating capabilities. *Bulletin of the American Meteorological Society*, 97, 1617-1630.

Wendt, N. A. and I. L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Weather and Forecasting*, 36, 645-659.

Williams, S. S., K. L. Ortega, T. M. Smith, and coauthors, 2022: Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms. *Bulletin of the American Meteorological Society*, 103, E838-E854.

Witt, A., et al., 1998: An enhanced hail detection algorithm for the WSR-88D. *Weather and Forecasting*, 13, 286-303.
