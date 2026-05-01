# Data Dictionary

**CONUS Hail Catastrophe Model v2.1**

---

## General Conventions

| Convention | Value |
|---|---|
| CRS | EPSG:4326 |
| Grid | 520 rows × 1180 columns |
| Resolution | 0.05° |
| Raster dtype | float32 unless otherwise noted |
| Hail size units | millimeters unless filename or column explicitly says inches |
| NoData for hazard rasters | 0.0 |
| NoData for probability rasters | usually -1.0 outside domain or 0.0 when masked |
| Compression | LZW tiled GeoTIFF |

---

## `data/historical/`

### `mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`

Raw daily maximum MESH raster before Stage 05 correction.

- **Type:** single-band GeoTIFF.
- **Shape:** 520 × 1180.
- **Units:** mm.
- **Sources:** MYRORSS, GridRad-derived MESH75, or operational MRMS.
- **Meaning:** maximum estimated hail size observed that day in each grid cell.

### `mesh_0.05deg/gridrad_days.txt`

List of dates whose `mesh_YYYYMMDD.tif` files came from GridRad or GridRad-Severe processing.

- **Type:** plain text.
- **Format:** one `YYYYMMDD` date per line.
- **Used by:** Stage 05 source-specific correction.

### `mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif`

Bias-corrected and environmentally filtered daily MESH75 raster.

- **Type:** single-band GeoTIFF.
- **Shape:** 520 × 1180.
- **Units:** mm MESH75.
- **Created by:** Stage 05.
- **v2.1 meaning:** calibrated hail size after source correction and probabilistic environmental filtering.

### `mesh_0.05deg_climo/climo_DOY.tif`

Daily climatological mean of corrected MESH75 for each day of year.

- **Files:** `climo_001.tif` through `climo_366.tif`.
- **Units:** mm.
- **Zeros included:** yes.
- **Purpose:** seasonal diagnostics and stochastic seasonal weighting.

### `mesh_0.05deg_climo/annual_mean_mesh75.tif`

Mean annual corrected MESH75 activity summary.

- **Units:** mm aggregated over climatology workflow.
- **Purpose:** diagnostic only.

### `mesh_0.05deg_climo/annual_hail_days.tif`

Mean annual number of hail-active days per cell.

- **Units:** days/year.
- **Purpose:** climatological occurrence diagnostic.

### `events/event_catalog.csv`

Historical hail event catalog.

Recommended v2.1 columns:

| Column | Description |
|---|---|
| `event_id` | integer event identifier |
| `start_date` | first date in event |
| `end_date` | last date in event |
| `duration_days` | event duration |
| `n_active_cells` | number of cells ≥ 25.4 mm |
| `footprint_area_km2` | approximate footprint area |
| `peak_hail_mm` | maximum event hail size |
| `peak_hail_in` | maximum event hail size in inches |
| `mean_hail_mm` | mean hail size over active event cells |
| `centroid_lat` | intensity-weighted centroid latitude |
| `centroid_lon` | intensity-weighted centroid longitude |
| `doy` | start-date day of year |
| `centroid_speed_km_day` | v2.1 optional merge diagnostic |
| `max_intensity_jump_ratio` | v2.1 optional merge diagnostic |
| `merge_quality_flag` | v2.1 optional quality flag |

### `events/event_peaks.npz`

Sparse per-event peak hail arrays.

Arrays:

| Array | Description |
|---|---|
| `rows_<event_id>` | row indices of active cells |
| `cols_<event_id>` | column indices of active cells |
| `vals_<event_id>` | peak hail values in mm |
| `event_ids` | integer event IDs |
| `n_events` | number of stored events |
| `grid_shape` | `[520, 1180]` |

Important: v2.1 treats this sparse format as authoritative. Dense event cubes should not be used in production simulation.

### `validation/mesh_vs_spc_pairs.csv`

Co-located SPC report and corrected MESH75 pairs.

Columns:

```text
date, lat, lon, spc_size_in, mesh75_mm, mesh75_in, grid_row, grid_col, hour
```

### `validation/calibration_report.csv`

Calibration statistics by SPC size bin.

### `validation/spatial_bias_1deg.csv`

Mean and median MESH/SPC ratio by 1° cell.

### `validation/validation_summary.txt`

Human-readable validation report.

### `validation/source_bias_summary.csv`

v2.1 recommended output comparing corrected distributions by source.

### `validation/top_event_validation.csv`

v2.1 recommended output summarizing the largest radar events and corresponding SPC evidence.

### `spc/YYYY/YYMMDD_rpts_hail.csv`

Raw SPC hail report CSVs used for validation/calibration.

### `era5/era5_monthly_isotherms_conus.nc`

ERA5 monthly 0°C and −20°C isotherm height climatology.

Variables:

| Variable | Units | Description |
|---|---|---|
| `h_0C_km` | km AGL | monthly mean 0°C isotherm height |
| `h_m20C_km` | km AGL | monthly mean −20°C isotherm height |

v2.1 optional additions may include CAPE, RH, or other environmental predictors.

---

## `data/analysis/`

### `calibration/gridrad_quantile_map.npz`

v2.0 fallback GridRad-to-MYRORSS quantile mapping.

Arrays:

```text
percentiles
gridrad_quantiles
myrorss_quantiles
correction_type
n_gridrad
n_myrorss
```

### `calibration/gridrad_cqm_model.pkl`

v2.1 conditional calibration model.

- **Type:** serialized regression or conditional quantile model.
- **Purpose:** condition GridRad correction on environmental and seasonal features.
- **Required features:** should be documented in `calibration_diagnostics.csv` or model metadata.

### `calibration/hail_filter_model.pkl`

v2.1 probabilistic environmental filter model.

- **Output:** probability of real surface hail.
- **Applied as:** `mesh_final = mesh_corrected × probability`.

### `calibration/calibration_diagnostics.csv`

Cross-source calibration diagnostics.

Recommended columns:

```text
source, period, percentile, raw_mm, corrected_mm, reference_mm, ratio, n_samples
```

### `calibration/hail_filter_diagnostics.csv`

v2.1 probabilistic filter diagnostics.

Recommended columns:

```text
model_type, feature_set, auc, brier_score, precision, recall, calibration_slope
```

---

## CDF Outputs

### `cdf/cdf_parameters.npz`

Per-cell frequency-severity parameters.

Arrays:

| Array | Description |
|---|---|
| `p_occ` | annual hail occurrence probability |
| `lognorm_mu` | lognormal body μ |
| `lognorm_sigma` | lognormal body σ |
| `gpd_xi` | GPD shape parameter |
| `gpd_sigma` | GPD scale parameter |
| `gpd_threshold` | selected GPD threshold in mm |
| `fit_type` | 0=no data, 1=lognormal only, 2=regional GPD, 3=cell GPD if used |
| `region_map` | regional cluster assignment |
| `region_xi` | pooled ξ by region |
| `grid_shape` | `[520, 1180]` |

### `cdf/threshold_selection.csv`

v2.1 automated GPD threshold diagnostics.

Recommended columns:

```text
region, candidate_threshold_mm, selected, n_exceedances, xi, sigma, mrl_score, stability_score, gof_score
```

### `cdf/rp_XXXXXyr_hail.tif`

Analytical return-period maps from Stage 09.

Return periods:

```text
10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000 years
```

### `cdf/rp_XXXXXyr_hail_smooth.tif`

Spatially pooled analytical return-period maps from Stage 10.

### `cdf/region_map.tif`

Regional cluster assignments for GPD pooling.

### `cdf/fitting_report.csv`

Summary of regional CDF fitting statistics.

### `cdf/mrl_diagnostics/mrl_region_*.png`

MRL diagnostic plots by region.

### `cdf/tail_stability_flags.tif`

v2.1 recommended raster identifying cells with unstable tail behavior.

Suggested values:

```text
0 = no flag
1 = low exceedance count
2 = unstable threshold
3 = extreme ξ
4 = analytical/stochastic divergence
```

---

## Occurrence Outputs

### `occurrence/p_occ_XpXXin.tif`

Annual probability of exceeding hail-size thresholds.

Thresholds:

```text
0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00 inches
```

Values range from 0.0 to 1.0 inside CONUS.

---

## Topography and Mask Outputs

### `conus_mask/conus_mask.tif`

Binary CONUS mask.

- 1.0 = CONUS land cell.
- 0.0 = outside domain.

### `topography/elevation_0.05deg.tif`

DEM resampled to the model grid.

- **Units:** meters.
- **Optional:** if absent, uniform correction is used.

### `topography/topo_correction.tif`

Topographic hail survival correction factor.

- **v2.0 fallback range:** 1.0–1.20.
- **v2.1 preferred range:** 1.0–1.25.

---

## Vulnerability Outputs

### `vulnerability/mdr_curves.csv`

Mean damage ratio lookup table for hail sizes 0–200 mm.

Columns:

```text
hail_mm, hail_in, 3tab_asphalt_aged, architectural_shingle, class4_ir, metal_standing_seam, masonry_bur
```

### `vulnerability/mdr_parameters.npz`

MDR parameters.

Arrays:

```text
class_names
mu_v
sigma_v
hail_sizes_mm
```

Important: these curves are placeholders and are not claims-calibrated.

---

## `data/stochastic/`

### `catalog/stochastic_event_summary.parquet`

One row per stochastic event.

Columns:

```text
sim_year, event_idx, template_id, doy, scale_factor, peak_hail_mm, n_cells
```

v2.1 recommended additions:

```text
drow, dcol, perturbation_type, template_peak_percentile
```

### `maps/rp_XXXXXyr_stochastic.tif`

Empirical return-period maps from the stochastic catalog.

### `pet/pet_occurrence.csv`

Occurrence exceedance probability table.

Columns:

```text
return_period_yr, peak_hail_mm, peak_hail_in, occ_n_cells
```

### `pet/pet_aggregate.csv`

Aggregate exceedance probability table.

Columns:

```text
return_period_yr, agg_n_cells, agg_n_events
```

### `diagnostics/analytical_stochastic_delta_XXXXXyr.tif`

v2.1 recommended difference maps:

```text
RP_stochastic − RP_analytical
```

---

## `docs/figures/`

| Directory | Contents |
|---|---|
| `figures/historical/` | analytical RP maps, climatology, event summaries |
| `figures/stochastic/` | stochastic RP maps, OEP/AEP charts |
| `figures/analysis/` | validation, tail diagnostics, analytical-vs-stochastic comparisons, vulnerability |
