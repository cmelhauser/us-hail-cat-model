# Data Dictionary

**CONUS Hail Catastrophe Model v2.1**

---

## 1. General Conventions

| Convention | Value |
|---|---|
| CRS | EPSG:4326 |
| Grid | 520 rows × 1180 columns |
| Resolution | 0.05° |
| Raster dtype | float32 unless otherwise noted |
| Hail units | millimeters unless filename or column explicitly says inches |
| Hazard NoData | 0.0 |
| Probability NoData | usually -1.0 outside domain or 0.0 when masked |
| Compression | LZW tiled GeoTIFF |
| Coordinate orientation | row 0 north, column 0 west |

---

## 2. Raw and Corrected Raster Data

### `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`

Raw daily maximum MESH raster before Stage 05 correction.

| Attribute | Value |
|---|---|
| Type | single-band GeoTIFF |
| Shape | 520 × 1180 |
| Units | mm |
| Source | MYRORSS, GridRad-derived MESH75, or operational MRMS |
| Meaning | daily maximum estimated hail size per grid cell |
| Important caveat | `0.0` means no MESH signal in the raster cell; use the Stage 01 manifest to distinguish missing MYRORSS source days from available-source no-hail days |
| Value QA | Values must be finite and within `[0.0, 300.0]` mm after each producing stage's QA pass |

### `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`

Per-day Stage 01 source-coverage and output manifest. This file is generated
alongside MYRORSS GeoTIFFs and is the authoritative way to distinguish source
availability from no-hail raster values.

| Column | Type | Meaning |
|---|---|---|
| `date` | ISO date | MYRORSS day, `YYYY-MM-DD` |
| `output_path` | string | Relative path to the daily GeoTIFF |
| `source_files` | integer | Total MYRORSS NetCDF objects found for the day |
| `plain_netcdf_files` | integer | Source objects ending in `.netcdf` |
| `gz_netcdf_files` | integer | Source objects ending in `.netcdf.gz` |
| `source_valid_pixels` | integer or blank | Valid native CONUS hail pixels read from source files; blank for skipped existing rasters |
| `active_cells_0p05` | integer | Output 0.05° cells with MESH > 0 |
| `max_mesh_mm` | float | Daily maximum MESH in millimeters after Stage 01 QA repair; values are capped by validation at 300.0 mm |
| `status` | string | `missing_source`, `no_hail_pixels`, `ok`, `ok_with_read_errors`, `no_hail_pixels_with_read_errors`, or `error` |
| `skipped` | integer | `1` when the GeoTIFF already existed and was not rebuilt in this pass, else `0` |
| `read_errors` | integer or blank | Count of source files that failed to read; blank for skipped existing rasters |

### `data/historical/mesh_0.05deg/gridrad_days.txt`

List of dates whose daily raster was generated from GridRad or GridRad-Severe.

| Attribute | Value |
|---|---|
| Type | plain text |
| Format | one `YYYYMMDD` date per line |
| Used by | Stage 05 source-specific calibration |

### `data/historical/gridrad/` and `data/historical/gridrad_severe/`

Staging directories for GridRad / GridRad-Severe NetCDF trees downloaded in Stage **04b**
(or by **04c** when run with **`--with-04b-download`**).

| Attribute | Value |
|---|---|
| Type | nested directories by calendar day |
| Ephemeral by default | After Stage **04c** processes a day, both trees for that `YYYYMMDD` are deleted unless **`--keep-gridrad-inputs`** is passed |
| Meaning | Not a required long-term archive path in the default pipeline; keep inputs only when debugging or reprocessing without re-downloading |

### `data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif`

Bias-corrected and filtered MESH75 raster.

| Attribute | Value |
|---|---|
| Created by | Stage 05 |
| Units | mm MESH75 |
| Meaning | homogenized daily hail-size estimate |
| v2.1 behavior | may include optional conditional calibration and probability-weighted filtering |
| Value QA | Values must be finite and within `[0.0, 300.0]` mm after Stage 05 correction/filtering |

---

## 3. Climatology Outputs

### `data/historical/mesh_0.05deg_climo/climo_DOY.tif`

Daily climatology raster for each day of year.

| Attribute | Value |
|---|---|
| Files | `climo_001.tif` through `climo_366.tif` |
| Units | mm |
| Zeros included | yes |
| Purpose | seasonal diagnostics and stochastic seasonal weighting |

### `annual_mean_mesh75.tif`

Annual mean corrected MESH75 activity summary.

### `annual_hail_days.tif`

Mean annual number of hail-active days per grid cell.

---

## 4. Event Outputs

### `data/historical/events/event_catalog.csv`

Historical hail event catalog.

| Column | Description |
|---|---|
| `event_id` | integer event identifier |
| `start_date` | first event date |
| `end_date` | last event date |
| `duration_days` | event duration |
| `n_active_cells` | number of cells ≥ 25.4 mm |
| `footprint_area_km2` | approximate event footprint area |
| `peak_hail_mm` | maximum event hail size |
| `peak_hail_in` | maximum hail size in inches |
| `mean_hail_mm` | mean hail size over active cells |
| `centroid_lat` | intensity-weighted centroid latitude |
| `centroid_lon` | intensity-weighted centroid longitude |
| `doy` | start-date day of year |
| `centroid_speed_km_day` | optional v2.1 merge diagnostic |
| `max_intensity_jump_ratio` | optional v2.1 merge diagnostic |
| `merge_quality_flag` | optional v2.1 quality flag |

### `data/historical/events/event_peaks.npz`

Sparse event peak arrays.

| Array | Description |
|---|---|
| `rows_<event_id>` | row indices of active cells |
| `cols_<event_id>` | column indices of active cells |
| `vals_<event_id>` | peak hail values in mm |
| `event_ids` | integer event IDs |
| `n_events` | number of events |
| `grid_shape` | `[520, 1180]` |

Important: this sparse format is the authoritative event representation.

---

## 5. SPC Validation Outputs

### `data/historical/validation/mesh_vs_spc_pairs.csv`

Co-located SPC and corrected MESH75 pairs.

Columns:

```text
date, lat, lon, spc_size_in, mesh75_mm, mesh75_in, grid_row, grid_col, hour
```

### `calibration_report.csv`

Size-bin calibration statistics.

### `spatial_bias_1deg.csv`

Mean and median MESH/SPC ratio by 1° cells.

### `validation_summary.txt`

Human-readable validation summary.

### Recommended v2.1 additions

```text
source_bias_summary.csv
top_event_validation.csv
```

---

## 6. ERA5 Outputs

### `data/historical/era5/era5_monthly_isotherms_conus.nc`

| Variable | Units | Description |
|---|---|---|
| `h_0C_km` | km AGL | monthly mean 0°C isotherm height |
| `h_m20C_km` | km AGL | monthly mean −20°C isotherm height |

Optional v2.1 predictors may include CAPE, RH, or shear proxies.

---

## 7. Calibration Outputs

### `data/analysis/calibration/gridrad_quantile_map.npz`

Fallback GridRad quantile mapping.

Arrays:

```text
percentiles
gridrad_quantiles
myrorss_quantiles
correction_type
n_gridrad
n_myrorss
```

### `gridrad_cqm_model.pkl`

Optional conditional calibration model.

### `hail_filter_model.pkl`

Optional probabilistic hail-realness model.

### `calibration_diagnostics.csv`

Recommended columns:

```text
source, period, percentile, raw_mm, corrected_mm, reference_mm, ratio, n_samples
```

### `hail_filter_diagnostics.csv`

Recommended columns:

```text
model_type, feature_set, auc, brier_score, precision, recall, calibration_slope
```

---

## 8. CDF Outputs

### `data/analysis/cdf/cdf_parameters.npz`

Arrays:

| Array | Description |
|---|---|
| `p_occ` | annual hail occurrence probability |
| `lognorm_mu` | lognormal body μ |
| `lognorm_sigma` | lognormal body σ |
| `gpd_xi` | GPD shape parameter |
| `gpd_sigma` | GPD scale parameter |
| `gpd_threshold` | GPD threshold in mm |
| `fit_type` | fit type code |
| `region_map` | region assignment |
| `region_xi` | pooled ξ by region |
| `grid_shape` | `[520, 1180]` |

### `threshold_selection.csv`

Recommended columns:

```text
region, candidate_threshold_mm, selected, n_exceedances, xi, sigma, mrl_score, stability_score, gof_score
```

### `rp_XXXXXyr_hail.tif`

Analytical return-period maps.

### `rp_XXXXXyr_hail_smooth.tif`

Spatially smoothed analytical maps.

### `region_map.tif`

Regional assignment raster.

### `fitting_report.csv`

Regional CDF fitting summary.

### `mrl_diagnostics/mrl_region_*.png`

MRL plots by region.

### `tail_stability_flags.tif`

Recommended diagnostic values:

```text
0 = no flag
1 = low exceedance count
2 = unstable threshold
3 = extreme xi
4 = analytical/stochastic divergence
```

---

## 9. Occurrence Outputs

### `data/analysis/occurrence/p_occ_XpXXin.tif`

Annual exceedance probability rasters for standard hail thresholds.

Thresholds:

```text
0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00 inches
```

---

## 10. Mask and Topography Outputs

### `data/analysis/conus_mask/conus_mask.tif`

Binary CONUS land mask.

### `data/analysis/topography/elevation_0.05deg.tif`

NOAA/NCEI ETOPO 2022 60 arc-second surface elevation resampled by Stage 11b to
the model grid. Negative ocean elevations are set to 0 m before writing because
Stage 12 uses the raster only for land-elevation topographic correction.

Source DOI: https://doi.org/10.25921/fd45-gt74

### `data/analysis/topography/source/ETOPO_2022_v1_60s_N90W180_surface.tif`

Cached source GeoTIFF downloaded from NOAA/NCEI by Stage 11b. This generated
source cache is ignored by git.

### `data/analysis/topography/topo_correction.tif`

Topographic correction factor.

v2.1 preferred bounds:

```text
1.0 to 1.25
```

---

## 11. Vulnerability Outputs

### `data/analysis/vulnerability/mdr_curves.csv`

Columns:

```text
hail_mm, hail_in, 3tab_asphalt_aged, architectural_shingle, class4_ir, metal_standing_seam, masonry_bur
```

### `mdr_parameters.npz`

Arrays:

```text
class_names
mu_v
sigma_v
hail_sizes_mm
```

These are placeholders and not production loss curves.

---

## 12. Stochastic Outputs

### `data/stochastic/catalog/stochastic_event_summary.parquet`

Columns:

```text
sim_year, event_idx, template_id, doy, scale_factor, peak_hail_mm, n_cells
```

Recommended v2.1 additions:

```text
drow, dcol, perturbation_type, template_peak_percentile
```

### `data/stochastic/maps/rp_XXXXXyr_stochastic.tif`

Empirical return-period maps from the stochastic catalog.

### `data/stochastic/pet/pet_occurrence.csv`

Occurrence exceedance probability table.

### `data/stochastic/pet/pet_aggregate.csv`

Aggregate exceedance probability table.

### `data/stochastic/diagnostics/analytical_stochastic_delta_XXXXXyr.tif`

Recommended delta map:

```text
RP_stochastic − RP_analytical
```

---

## 13. Figure Outputs

| Directory | Contents |
|---|---|
| `docs/figures/historical/` | analytical maps, climatology, event summaries |
| `docs/figures/stochastic/` | stochastic maps and EP curves |
| `docs/figures/analysis/` | validation, tail diagnostics, analytical-vs-stochastic comparisons |
