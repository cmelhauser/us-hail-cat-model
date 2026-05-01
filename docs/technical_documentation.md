# Technical Documentation

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Grid Specification

| Parameter | Value |
|---|---:|
| Resolution | 0.05° × 0.05° |
| Approximate cell size | ~5.5 km |
| CRS | EPSG:4326 |
| Extent | lon −125.005 to −66.005, lat 24.005 to 50.005 |
| Dimensions | 1180 columns × 520 rows |
| Total cells | 613,600 |
| Orientation | row 0 is northernmost, column 0 is westernmost |
| Default raster dtype | float32 |
| Default compression | LZW tiled GeoTIFF |

All scripts should use the same grid constants. Any change to these constants is a model-version change and must trigger full regeneration.

---

## 2. Stage Reference

### Stage 01 — MYRORSS download and raster build

**Script:** `01_download_myrorss.py`  
**Input:** public MYRORSS sparse NetCDF files on AWS  
**Output:** `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`

Technical notes:

- Native sparse MYRORSS data are converted into daily maximum 0.01° grids.
- CONUS subset is aggregated to 0.05° using block maximum.
- Output values are daily maximum MESH in mm.
- Missing days are written as all-zero rasters to preserve temporal continuity.

Validation should confirm file count, CRS, shape, dtype, and reasonable maximum values.

---

### Stage 02 — Operational MRMS download and raster build

**Script:** `02_download_mrms_mesh.py`  
**Input:** public MRMS GRIB2 files on AWS  
**Output:** same directory and format as Stage 01

Technical notes:

- Native MRMS uses south-to-north orientation and 0–360° longitudes.
- Stage 02 flips rasters to north-to-south and converts to −180/+180 longitude convention.
- Daily maximum is accumulated before 0.05° block maximum.

Validation should include orientation checks against known spatial patterns or sample points.

---

### Stage 03 — SPC report download

**Script:** `03_download_spc.py`  
**Input:** NOAA SPC daily report CSVs  
**Output:** `data/historical/spc/YYYY/YYMMDD_rpts_hail.csv`

SPC reports are validation data only. They must not be used as the primary hazard input.

---

### Stage 04a — ERA5 isotherm climatology

**Script:** `04a_download_era5_isotherms.py`  
**Input:** ERA5 monthly pressure-level temperature and geopotential  
**Output:** `data/historical/era5/era5_monthly_isotherms_conus.nc`

Variables:

- `h_0C_km`
- `h_m20C_km`

v2.1 recommended additions if resources allow:

- CAPE.
- Relative humidity layers.
- Optional shear proxy inputs.

These are used by Stage 05 conditional calibration and environmental filtering.

---

### Stage 04b — GridRad gap fill

**Script:** `04b_fill_gridrad_gap.py`  
**Input:** GridRad / GridRad-Severe NetCDF reflectivity and ERA5 isotherms  
**Output:** daily MESH75 GeoTIFFs in `data/historical/mesh_0.05deg/`

Core equation:

```text
MESH75 = 15.096 × SHI^0.206
```

Stage 04b should write `gridrad_days.txt` to identify GridRad-derived rasters. Stage 05 uses this source-tracking file to apply GridRad-specific calibration.

---

### Stage 05 — Unified bias correction and environmental filtering

**Script:** `05_apply_mesh_bias_correction.py`  
**Input:** `data/historical/mesh_0.05deg/`  
**Output:** `data/historical/mesh_0.05deg_corrected/`

v2.1 Stage 05 has four logical components:

1. Source identification from `gridrad_days.txt`.
2. MESH75 recalibration for MYRORSS/MRMS.
3. GridRad conditional calibration, with quantile mapping fallback.
4. Probabilistic environmental filtering.

Recommended outputs:

```text
data/analysis/calibration/gridrad_quantile_map.npz
data/analysis/calibration/gridrad_cqm_model.pkl
data/analysis/calibration/hail_filter_model.pkl
data/analysis/calibration/calibration_diagnostics.csv
data/analysis/calibration/hail_filter_diagnostics.csv
```

Implementation constraints:

- Raster operations should be vectorized.
- Avoid per-pixel Python loops over the full 520×1180 grid.
- Calibration models should be optional and skip-safe.
- If ML model files are missing, the script should fall back to v2.0 quantile mapping and hard filters.

---

### Stage 06 — MESH vs SPC validation

**Script:** `06_validate_mesh_vs_spc.py`  
**Input:** corrected MESH rasters and SPC hail reports  
**Output:** validation CSVs, summary text, and figures

Required outputs:

```text
data/historical/validation/mesh_vs_spc_pairs.csv
data/historical/validation/calibration_report.csv
data/historical/validation/spatial_bias_1deg.csv
data/historical/validation/validation_summary.txt
docs/figures/analysis/mesh_vs_spc_scatter.png
docs/figures/analysis/detection_by_size.png
```

v2.1 recommended additions:

```text
data/historical/validation/source_bias_summary.csv
data/historical/validation/top_event_validation.csv
docs/figures/analysis/source_distribution_comparison.png
```

---

### Stage 07 — Daily climatology

**Script:** `07_build_hail_climo.py`  
**Output:** 366 daily climatology rasters plus annual summaries

Outputs:

```text
data/historical/mesh_0.05deg_climo/climo_001.tif ... climo_366.tif
data/historical/mesh_0.05deg_climo/annual_mean_mesh75.tif
data/historical/mesh_0.05deg_climo/annual_hail_days.tif
```

Annual hail days should be interpreted as expected hail-active days per year, not probability.

---

### Stage 08 — Event catalog

**Script:** `08_build_event_catalog.py`  
**Input:** corrected daily MESH75 rasters  
**Output:** sparse historical event catalog

Outputs:

```text
data/historical/events/event_catalog.csv
data/historical/events/event_peaks.npz
```

v2.1 additional recommended columns:

```text
centroid_speed_km_day
merge_quality_flag
max_intensity_jump_ratio
```

Sparse storage format:

```text
rows_<event_id>: int16 row indices
cols_<event_id>: int16 col indices
vals_<event_id>: float32 hail size values
```

Critical implementation rule:

```text
Sparse event arrays are the authoritative representation. Do not build a full dense event cube for production simulation.
```

---

### Stage 09 — Regional CDF fitting

**Script:** `09_fit_cdf_regional.py`  
**Output:** CDF parameters, analytical RP maps, region map, threshold diagnostics

Outputs:

```text
data/analysis/cdf/cdf_parameters.npz
data/analysis/cdf/rp_XXXXXyr_hail.tif
data/analysis/cdf/region_map.tif
data/analysis/cdf/fitting_report.csv
data/analysis/cdf/mrl_diagnostics/mrl_region_*.png
data/analysis/cdf/threshold_selection.csv
```

v2.1 threshold selection should report:

- Candidate threshold.
- Exceedance count.
- ξ estimate.
- σ estimate.
- GOF score.
- Stability score.
- Selected flag.

CDF parameter arrays:

```text
p_occ
lognorm_mu
lognorm_sigma
gpd_xi
gpd_sigma
gpd_threshold
fit_type
region_map
region_xi
grid_shape
```

---

### Stage 10 — Spatially pooled CDF rebuild

**Script:** `10_build_smooth_cdf.py`  
**Input:** corrected rasters and Stage 09 CDF parameters  
**Output:** smoothed analytical RP maps

Outputs:

```text
data/analysis/cdf/rp_XXXXXyr_hail_smooth.tif
data/analysis/cdf/p_occurrence_smooth.tif
```

v2.1 performance recommendation:

- Use spatial indexing or chunked neighbor windows if runtime becomes excessive.
- Avoid repeated full-grid neighbor scans for every active cell when possible.

---

### Stage 11 — Occurrence probabilities

**Script:** `11_build_occurrence_probs.py`  
**Output:** empirical annual occurrence probabilities

Outputs:

```text
data/analysis/occurrence/p_occ_0p25in.tif
data/analysis/occurrence/p_occ_0p50in.tif
data/analysis/occurrence/p_occ_1p00in.tif
data/analysis/occurrence/p_occ_1p50in.tif
data/analysis/occurrence/p_occ_2p00in.tif
data/analysis/occurrence/p_occ_3p00in.tif
data/analysis/occurrence/p_occ_4p00in.tif
data/analysis/occurrence/p_occ_5p00in.tif
```

---

### Stage 12 — CONUS mask and topographic correction

**Script:** `12_apply_conus_mask.py`  
**Output:** CONUS mask and topographic correction raster

Outputs:

```text
data/analysis/conus_mask/conus_mask.tif
data/analysis/topography/elevation_0.05deg.tif
data/analysis/topography/topo_correction.tif
```

v2.1 correction formula:

```text
factor = 1 + α × elevation_km / freezing_level_km
factor = clip(factor, 1.0, 1.25)
```

Fallback:

```text
factor = 1 + 0.05 × elevation_km
factor = clip(factor, 1.0, 1.20)
```

---

### Stage 13 — Stochastic catalog

**Script:** `13_generate_stochastic_catalog.py`  
**Output:** stochastic catalog, empirical RP maps, PET tables

Outputs:

```text
data/stochastic/catalog/stochastic_event_summary.parquet
data/stochastic/maps/rp_XXXXXyr_stochastic.tif
data/stochastic/pet/pet_occurrence.csv
data/stochastic/pet/pet_aggregate.csv
```

v2.1 critical technical requirement:

```text
Do not reconstruct every event into dense 520×1180 arrays. Operate on sparse rows/cols/vals and update annual maxima through active-cell indexing.
```

Recommended simulation configuration:

- 50,000 years for final run.
- shorter `--n-years` runs for testing.
- deterministic RNG seed for reproducibility.
- data-calibrated lognormal intensity perturbation.
- Gaussian spatial translation.
- optional sparse shape perturbation.

---

### Stage 14 — Vulnerability placeholder

**Script:** `14_build_vulnerability.py`  
**Output:** MDR curves and parameter file

Outputs:

```text
data/analysis/vulnerability/mdr_curves.csv
data/analysis/vulnerability/mdr_parameters.npz
```

These curves are not claims-calibrated. They are for method demonstration and integration testing.

---

### Stage 15 — Figures and diagnostics

**Script:** `15_render_figures.py`  
**Output:** all figures

Required figure categories:

```text
docs/figures/historical/
docs/figures/stochastic/
docs/figures/analysis/
```

v2.1 additions:

```text
docs/figures/analysis/analytical_vs_stochastic_delta_*.png
docs/figures/analysis/gpd_threshold_map.png
docs/figures/analysis/tail_stability_flags.png
docs/figures/analysis/source_distribution_comparison.png
```

---

## 3. Validation Requirements

Each stage should support `--validate`. Validation should check both existence and reasonableness.

Minimum checks:

- File exists.
- File is non-empty.
- Raster shape and CRS match grid specification.
- Values are finite.
- Values fall within plausible bounds.
- Required schemas are present.
- Event durations do not exceed the cap.
- Sparse event arrays are internally consistent.
- RP maps are monotonic with return period for most cells.

---

## 4. Performance Requirements

The following operations are potentially expensive:

1. Stage 04b GridRad SHI computation.
2. Stage 09 annual maximum build and CDF fitting.
3. Stage 10 spatial pooling.
4. Stage 13 stochastic simulation.

v2.1 implementation guidance:

- Use vectorized raster operations.
- Avoid Python loops over all cells unless the active set is small.
- Treat sparse event arrays as first-class objects.
- Avoid dense `(n_events, NROWS, NCOLS)` arrays in production.
- Use chunked or memory-mapped arrays if full annual grids are required.

---

## 5. Reproducibility

Every final run should record:

- Git commit hash if available.
- Model version.
- Stage arguments.
- Random seed.
- Input date range.
- Calibration model paths.
- Whether fallback calibration/filtering was used.

Recommended manifest output:

```text
data/analysis/run_manifest.json
```

---

## 6. Production Review Checklist

Before using v2.1 outputs for underwriting-grade review, confirm:

- Stage 05 source calibration diagnostics are acceptable.
- Stage 06 validation is complete.
- Stage 09 threshold selection has no major unstable regions.
- Stage 13 stochastic outputs are complete and monotonic across return periods.
- Stage 15 analytical-vs-stochastic differences are understood.
- Vulnerability is clearly labeled as placeholder if losses are discussed.
