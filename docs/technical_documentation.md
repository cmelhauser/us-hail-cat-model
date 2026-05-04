# Technical Documentation

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Purpose

This document describes the implementation contract for the v2.1 hail hazard pipeline. It complements `docs/methodology.md`: the methodology document explains the scientific rationale, while this document specifies stage behavior, inputs, outputs, invariants, validation checks, and failure modes.

The pipeline is intentionally file-oriented. Each stage writes durable artifacts that can be inspected independently, rerun, validated, and excluded from git tracking. This design favors reproducibility and auditability over a monolithic in-memory workflow.

---

## 2. Global Grid Contract

| Parameter | Value |
|---|---:|
| CRS | EPSG:4326 |
| Resolution | 0.05 degree x 0.05 degree |
| Rows | 520 |
| Columns | 1180 |
| Total cells | 613,600 |
| Row orientation | north-to-south |
| Column orientation | west-to-east |
| Raster dtype | float32 unless otherwise stated |
| Raster compression | LZW tiled GeoTIFF |
| Standard units | millimeters for hail size |

### 2.1 Invariants

Every gridded hazard output must preserve:

- shape `(520, 1180)`;
- EPSG:4326 coordinates;
- north-to-south row orientation;
- west-to-east column orientation;
- finite non-negative hail values unless a stage explicitly uses a mask or nodata value;
- stable filename conventions.

Changing any grid constant is a model-version change and requires regeneration of downstream outputs.

### 2.2 Hail aggregation rule

Hail size is an extremal variable. Native-to-model-grid aggregation must use a maximum operator:

```text
out_cell = max(native_cells intersecting out_cell)
```

Do not use area means, bilinear interpolation, or summation for MESH fields unless the purpose is a clearly labelled diagnostic.

---

## 3. Stage 01 - MYRORSS Download and Raster Build

**Script:** `scripts/01_download_myrorss.py`  
**Input:** MYRORSS sparse NetCDF files on public AWS S3 (`.netcdf` and `.netcdf.gz`)
**Output:** `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`
**Manifest:** `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`

### 3.1 Technical behavior

1. Iterate MYRORSS dates from April 1998 through December 2011.
2. List source objects for each day.
3. Accept both plain NetCDF and gzipped NetCDF objects.
4. Decode sparse pixel arrays into the native MYRORSS grid.
5. Accumulate daily maximum MESH at native resolution.
6. Subset to the CONUS model domain.
7. Aggregate to 0.05 degree by block maximum.
8. Apply Stage 01 physical QA: non-finite, negative, and `>300.0 mm` values
   are reset to `0.0` before downstream use.
9. Write one daily GeoTIFF.
10. Upsert a source manifest row.
11. After download/processing, scan the Stage 01 date range again with the same
    QA rules and refresh manifest `active_cells_0p05`, `max_mesh_mm`, and
    `status` fields.

### 3.2 Manifest semantics

The manifest is the authoritative source-coverage record. A zero-valued daily GeoTIFF does not, by itself, reveal whether a day was meteorologically quiet or whether source data were absent.

| Status | Meaning | Downstream interpretation |
|---|---|---|
| `missing_source` | No MYRORSS objects found for the day. | Treat as data availability gap. |
| `no_hail_pixels` | Source objects existed but produced no valid CONUS hail pixels. | Treat as observed quiet day. |
| `ok` | Source objects existed and produced active cells. | Normal observed day. |
| `ok_with_read_errors` | Some files failed, but active cells were produced. | Use output, flag for QA. |
| `no_hail_pixels_with_read_errors` | Some files failed and no active cells were produced. | Use cautiously; inspect if common. |
| `error` | All source files failed to read. | Treat as failed day until diagnosed. |

Manifest columns:

```text
date
output_path
source_files
plain_netcdf_files
gz_netcdf_files
source_valid_pixels
active_cells_0p05
max_mesh_mm
status
skipped
read_errors
```

### 3.3 Scientific notes

MYRORSS is a historical radar reanalysis. Its value is spatial and temporal continuity over the early radar era, but individual files can be sparse, missing, corrupt, or encoded differently across periods. The stage must therefore treat archive format variation as normal operational reality rather than exceptional behavior.

Stage 01 uses a conservative 300.0 mm upper QA bound for hail diameter values.
This cap is larger than the NOAA/NSSL U.S. record hailstone diameter from
Vivian, South Dakota, and is intended to remove malformed radar/source values
without clipping plausible extreme hail. The QA pass can be run independently:

```bash
python scripts/01_download_myrorss.py --qa-only
```

### 3.4 Validation

- Output directory exists.
- TIFF count is plausible for the requested date span.
- Manifest rows are continuous over processed dates.
- CRS is EPSG:4326.
- Shape is 520 x 1180.
- Values are finite, non-negative, and no larger than 300.0 mm.
- `missing_source` and `no_hail_pixels` are distinguished by manifest status.
- Random sample rasters open with rasterio.

---

## 4. Stage 02 - MRMS Download and Raster Build

**Script:** `scripts/02_download_mrms_mesh.py`  
**Input:** MRMS MESH GRIB2 files on public AWS S3
**Output:** `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`

### 4.1 Technical behavior

MRMS native products use conventions that differ from the final model grid. Stage 02 must:

1. list available MRMS MESH products;
2. download or stream source GRIB2 files;
3. extract the CONUS subset;
4. convert longitude convention where needed;
5. flip south-to-north native orientation into north-to-south model orientation;
6. accumulate daily maxima;
7. aggregate by block maximum;
8. apply the shared hail-value QA guard: finite, non-negative, and no larger
   than 300.0 mm;
9. write model-grid GeoTIFFs.

### 4.2 Validation

Same raster validation as Stage 01, including the 300.0 mm physical QA bound,
with additional orientation sanity checks. A simple visual or statistical check
should confirm that major hail maxima are over plausible U.S. regions rather
than shifted over oceans, Mexico, or Canada by grid-orientation error.

---

## 5. Stage 03 - SPC Download

**Script:** `scripts/03_download_spc.py`  
**Input:** SPC daily hail report CSVs
**Output:** `data/historical/spc/YYYY/YYMMDD_rpts_hail.csv`

SPC reports are validation and calibration-support data. They are not the primary hazard field.

### 5.1 Validation

- CSV files exist for requested dates.
- Files parse successfully.
- Empty or missing report days are handled explicitly.
- Report sizes, latitudes, longitudes, and timestamps pass range checks.

---

## 6. Stage 04a - ERA5 Isotherms

**Script:** `scripts/04a_download_era5_isotherms.py`  
**Output:** `data/historical/era5/era5_monthly_isotherms_conus.nc`

### 6.1 Required variables

```text
h_0C_km
h_m20C_km
```

### 6.2 Technical behavior

Stage 04a prepares monthly thermodynamic context for GridRad SHI computation and optional filtering. The 0 C and -20 C levels define the vertical layer over which reflectivity contributes to SHI temperature weighting.

### 6.3 Validation

- NetCDF exists.
- Required variables exist.
- Dimensions align with expected spatial and temporal axes.
- Median values are physically plausible.
- NaN coverage is limited and fallback filling is logged.

---

## 7. Stage 04b - GridRad Gap Fill

**Script:** `scripts/04b_fill_gridrad_gap.py`  
**Input:** GridRad or GridRad-Severe NetCDF files plus ERA5 isotherms
**Output:** daily MESH75 GeoTIFFs and `gridrad_days.txt`

### 7.1 Technical behavior

1. Locate GridRad-Severe where available; otherwise fall back to hourly GridRad.
2. Load three-dimensional reflectivity profiles.
3. Identify active columns above reflectivity threshold.
4. Integrate Severe Hail Index above the freezing level and through the hail-growth layer.
5. Convert SHI to MESH75:

```text
MESH75 = 15.096 * SHI^0.206
```

6. Accumulate daily maximum MESH75.
7. Apply the shared hail-value QA guard: finite, non-negative, and no larger
   than 300.0 mm.
8. Write daily GeoTIFFs on the common grid.

### 7.2 Scientific notes

GridRad is a gap-fill source. It should not be assumed exchangeable with MYRORSS or MRMS before calibration. Differences in temporal sampling, reflectivity processing, and vertical structure can affect high-percentile hail estimates.

### 7.3 Validation

- GridRad day list exists.
- Output rasters exist for available days.
- Peak values fall within plausible hail-size bounds.
- ERA5 fallback usage is logged.
- Source-era distribution checks are available downstream.

---

## 8. Stage 05 - Bias Correction and Environmental Filtering

**Script:** `scripts/05_apply_mesh_bias_correction.py`  
**Input:** raw daily MESH rasters
**Output:** corrected daily MESH75 rasters

### 8.1 Required logic

For MYRORSS and MRMS:

```text
apply corrected MESH75 recalibration
```

For GridRad:

```text
if conditional calibration artifact exists and --skip-ml is false:
    apply conditional calibration
else:
    apply deterministic quantile mapping
```

For all sources:

```text
if hail-filter artifact exists and --skip-ml is false:
    apply probabilistic filter
else:
    apply deterministic environmental filters
```

### 8.2 Optional artifacts

```text
data/analysis/calibration/gridrad_cqm_model.pkl
data/analysis/calibration/hail_filter_model.pkl
```

### 8.3 Hard requirement

Stage 05 must run successfully without optional artifacts. The `--skip-ml` flag must force deterministic behavior.

### 8.4 Validation

- Corrected rasters exist.
- Output count is close to input count after expected date filters.
- CRS and shape are unchanged.
- Values remain finite, non-negative, and no larger than 300.0 mm.
- Filtered-cell counts are plausible by month and region.
- Calibration diagnostics are written.
- Source-era distributions are reviewed for MYRORSS/GridRad/MRMS discontinuities.

---

## 9. Stage 06 - Validation Against SPC

**Script:** `scripts/06_validate_mesh_vs_spc.py`  
**Output directory:** `data/historical/validation/`

### 9.1 Required outputs

```text
mesh_vs_spc_pairs.csv
calibration_report.csv
spatial_bias_1deg.csv
validation_summary.txt
```

### 9.2 Required figures

```text
docs/figures/analysis/mesh_vs_spc_scatter.png
docs/figures/analysis/detection_by_size.png
```

### 9.3 Interpretation

SPC validation is a consistency exercise, not a perfect error calculation. False-alarm and miss metrics should be labelled as proxies because either the radar field or the report record can be incomplete at a given time and location.

### 9.4 Validation

- Pairing logic uses documented spatial and temporal tolerances.
- Report-size bins are stable.
- Regional summaries identify source or terrain biases.
- Figures are regenerated and visually inspected.

---

## 10. Stage 07 - Climatology

**Script:** `scripts/07_build_hail_climo.py`  
**Output:** `data/historical/mesh_0.05deg_climo/`

### 10.1 Required outputs

```text
climo_001.tif ... climo_366.tif
annual_mean_mesh75.tif
annual_hail_days.tif
```

### 10.2 Technical behavior

Stage 07 averages corrected daily MESH75 by day-of-year across available years. Zeros remain in the average because the output is expected daily hazard activity, not size conditional on hail occurrence.

### 10.3 Validation

- 366 climatology files exist.
- Annual summaries exist.
- Shapes and CRS match the grid contract.
- Seasonal maxima occur in meteorologically plausible months.
- Leap-day handling is explicit.

---

## 11. Stage 08 - Event Catalog

**Script:** `scripts/08_build_event_catalog.py`  
**Output:** `data/historical/events/`

### 11.1 Required outputs

```text
event_catalog.csv
event_peaks.npz
```

### 11.2 Event grouping constraints

```text
temporal gap <= 2 days
buffered footprint overlap required
duration <= 5 days
centroid displacement <= configured limit
peak intensity jump <= configured limit
```

### 11.3 Sparse storage requirement

`event_peaks.npz` stores event arrays by event ID:

```text
rows_<event_id>
cols_<event_id>
vals_<event_id>
```

Dense event cubes are prohibited as production event storage. They are memory-inefficient and can make Stage 13 infeasible at full catalog length.

### 11.4 Validation

- CSV exists and has events.
- NPZ exists and event IDs align with CSV.
- Every event has matching row, column, and value lengths.
- Duration cap is not violated.
- Active-cell counts are positive for non-empty events.
- Peak hail values are plausible.
- Physical merge constraints are audited.

---

## 12. Stage 09 - Regional CDF Fitting

**Script:** `scripts/09_fit_cdf_regional.py`  
**Output:** `data/analysis/cdf/`

### 12.1 Required outputs

```text
cdf_parameters.npz
rp_XXXXXyr_hail.tif
region_map.tif
fitting_report.csv
threshold_selection.csv
mrl_diagnostics/
```

### 12.2 Statistical model

At each grid cell, annual maxima are modeled as a zero-inflated positive distribution:

```text
p_occ = count(years with nonzero hail) / total_years
positive distribution = lognormal body + GPD tail
```

The tail uses regional GPD shape pooling:

```text
cluster cells by climatology and geography
pool exceedances within each region
estimate regional xi
estimate cell-specific scale where possible
```

### 12.3 Threshold diagnostics

`threshold_selection.csv` should contain:

```text
region_id
candidate_threshold_mm
exceedance_count
xi
sigma
mrl_score
stability_score
gof_score
selected
```

Threshold selection is a model-risk control. Long return-period maps should not be interpreted without reviewing these diagnostics.

### 12.4 Validation

- Parameter arrays exist.
- Return-period maps exist.
- Values are finite and non-negative.
- Return-period maps are monotonic by return period at almost all valid cells.
- `xi` values are bounded and not dominated by fallback values.
- Regions have adequate pooled exceedance counts.

---

## 13. Stage 10 - Spatially Pooled CDF

**Script:** `scripts/10_build_smooth_cdf.py`  
**Output:** smoothed return-period maps

### 13.1 Technical behavior

Stage 10 pools nearby annual maxima or fitted parameters within a configured radius and applies distance-decay weights. The goal is to reduce noisy cell-level artifacts while preserving broad hail corridors.

### 13.2 Methodological caution

Spatial smoothing is not a full spatial extremes model. It improves marginal maps but does not estimate extremal dependence. Aggregate risk and multi-cell joint exceedance behavior must be checked through event-based stochastic outputs.

### 13.3 Validation

- Smoothed return-period maps exist.
- `p_occurrence_smooth.tif` exists.
- Values remain plausible.
- Smoothing does not introduce halos, edge artifacts, or shifted maxima.
- Smoothed maps remain broadly consistent with unsmoothed maps and empirical occurrence products.

---

## 14. Stage 11 - Occurrence Probabilities

**Script:** `scripts/11_build_occurrence_probs.py`

### 14.1 Outputs

```text
p_occ_0p25in.tif
p_occ_0p50in.tif
p_occ_1p00in.tif
p_occ_1p50in.tif
p_occ_2p00in.tif
p_occ_3p00in.tif
p_occ_4p00in.tif
p_occ_5p00in.tif
```

### 14.2 Validation

- Values are in `[0, 1]`.
- Higher thresholds have lower or equal probability than lower thresholds.
- High-probability corridors are meteorologically plausible.
- Maps are used to sanity-check fitted CDF return levels.

---

## 15. Stage 12 - CONUS Mask and Topographic Correction

**Script:** `scripts/12_apply_conus_mask.py`

### 15.1 Outputs

```text
data/analysis/conus_mask/conus_mask.tif
data/analysis/topography/topo_correction.tif
```

### 15.2 v2.1 correction

Preferred:

```text
factor = 1 + alpha * elevation_km / freezing_level_km
factor = clip(factor, 1.0, 1.25)
```

Fallback:

```text
factor = 1 + 0.05 * elevation_km
factor = clip(factor, 1.0, 1.20)
```

### 15.3 Validation

- Mask exists.
- Correction factor is within configured bounds.
- Outside-CONUS cells are masked.
- Correction does not introduce discontinuities along state or source boundaries.
- Terrain correction is reviewed in mountainous regions.

---

## 16. Stage 13 - Stochastic Catalog

**Script:** `scripts/13_generate_stochastic_catalog.py`

### 16.1 Outputs

```text
data/stochastic/catalog/stochastic_event_summary.parquet
data/stochastic/maps/rp_XXXXXyr_stochastic.tif
data/stochastic/pet/pet_occurrence.csv
data/stochastic/pet/pet_aggregate.csv
```

### 16.2 Critical implementation rule

Do not reconstruct the event catalog as dense event rasters. The stochastic loop operates on:

```text
rows, cols, vals
```

### 16.3 Stochastic steps

1. Draw annual event count from `Poisson(lambda)`.
2. Draw event date from the smoothed seasonal distribution.
3. Select historical template using seasonal weights.
4. Calibrate global `sigma_perturb` as the median March-September monthly coefficient of variation of event peaks, clipped to `[0.10, 0.40]`.
5. Apply percentile-aware lognormal intensity scaling.
6. Apply sparse spatial translation.
7. Optionally perturb sparse shape with a reduced-intensity neighbor shell.
8. Update compact annual maxima.
9. Write empirical return-period maps and PET tables.

### 16.4 Validation

- Smoke test with `--n-years 1000`.
- Full catalog run completes without memory blowup.
- Return-period maps exist.
- PET tables exist.
- Sparse logic remains memory bounded.
- Analytical and stochastic maps are compared in Stage 15.

---

## 17. Stage 14 - Vulnerability

**Script:** `scripts/14_build_vulnerability.py`

### 17.1 Outputs

```text
mdr_curves.csv
mdr_parameters.npz
```

### 17.2 Important caveat

These curves are placeholders. They are suitable for pipeline integration and demonstration, but they are not production loss curves and should not be used for financial decisions without claims calibration.

### 17.3 Validation

- Curves are monotonic with hail size.
- Mean damage ratios remain in `[0, 1]`.
- Runtime warning or documentation clearly labels placeholder status.

---

## 18. Stage 15 - Figures

**Script:** `scripts/15_render_figures.py`

### 18.1 Output directories

```text
docs/figures/historical/
docs/figures/stochastic/
docs/figures/analysis/
```

### 18.2 Required categories

- analytical return-period maps;
- stochastic return-period maps;
- exceedance probability curves;
- validation figures;
- analytical-vs-stochastic comparisons;
- event summaries;
- vulnerability curves;
- GPD and tail diagnostics.

### 18.3 Figure QA

Figures are scientific diagnostics, not decoration. Review for:

- shifted CONUS domain or orientation error;
- suspicious maxima over Mexico, oceans, or masked cells;
- source-transition artifacts;
- over-smoothed hail corridors;
- analytical-vs-stochastic divergence;
- unreadable labels, legends, or colorbars;
- generated files that should remain untracked.

---

## 19. Validation Commands

Before a full run:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

After outputs exist:

```bash
python run_pipeline.py --validate
```

Stage-specific validation commands should be run before advancing after any failure, major source change, or methodology change.

---

## 20. Run Manifest

Recommended manifest path:

```text
data/analysis/run_manifest.json
```

The manifest should record:

- model version;
- git commit;
- branch;
- random seed;
- stages run;
- calibration mode;
- filtering mode;
- stochastic years;
- run date;
- script versions or checksums if available;
- source-data date ranges;
- warnings and non-fatal read errors.

The run manifest should be considered part of reproducibility, but generated manifests under `data/` should remain untracked unless the project explicitly decides to version a small summary artifact.

---

## 21. Pre-Run Hardening Summary

The v2.1 hardening pass emphasizes:

- explicit MYRORSS source manifest;
- sparse-safe Stage 13;
- deterministic Stage 05 fallback;
- event merge sanity checks;
- GPD threshold diagnostics;
- source-transition QA;
- expanded tests;
- synchronized documentation.

---

## 22. Failure Handling

If a stage fails:

1. stop before rerunning destructive or expensive work;
2. inspect the stage log;
3. determine whether outputs are partial, complete, or corrupt;
4. preserve diagnostic logs;
5. rerun only the failed stage or affected date range if the script supports it;
6. document the reason if generated outputs are deleted or replaced.

Never infer success from file existence alone. Use validation checks, logs, manifest coverage, and sample raster reads.

---

## 23. References

This section lists the technical and scientific references that define the pipeline's data formats, gridded processing assumptions, radar products, statistical machinery, and reproducibility expectations.

Allen, J. T. and M. K. Tippett, 2015: The characteristics of United States hail reports: 1955-2014. *Electronic Journal of Severe Storms Meteorology*, 10(3), 1-31.

Balkema, A. A. and L. de Haan, 1974: Residual life time at great age. *Annals of Probability*, 2(5), 792-804.

Coles, S., 2001: *An Introduction to Statistical Modeling of Extreme Values.* Springer.

Davison, A. C., S. A. Padoan, and M. Ribatet, 2012: Statistical modeling of spatial extremes. *Statistical Science*, 27(2), 161-186.

GDAL/OGR contributors, 2026: *GDAL/OGR Geospatial Data Abstraction Software Library.* Open Source Geospatial Foundation.

Grossi, P. and H. Kunreuther, 2005: *Catastrophe Modeling: A New Approach to Managing Risk.* Springer.

Hosking, J. R. M. and J. R. Wallis, 1997: *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press.

Mitchell-Wallace, K., M. Jones, J. Hillier, and M. Foote, 2017: *Natural Catastrophe Risk Management and Modelling: A Practitioner's Guide.* Wiley.

Murillo, E. M. and C. R. Homeyer, 2019: Severe hail fall and hailstorm detection using remote sensing observations. *Journal of Applied Meteorology and Climatology*, 58, 947-970; corrigendum and corrected MESH relationships.

Murillo, E. M., C. R. Homeyer, and J. T. Allen, 2021: A 23-year severe hail climatology using GridRad MESH observations. *Monthly Weather Review*, 149, 945-958.

National Centers for Environmental Prediction, 2003: *NCEP Office Note 388: GRIB Edition 2.* National Weather Service.

NetCDF Contributors, 2026: *Network Common Data Form (NetCDF) User Guide.* Unidata Program Center.

NumPy Developers, 2020: Array programming with NumPy. *Nature*, 585, 357-362.

Open Source Geospatial Foundation, 2026: *PROJ Coordinate Transformation Software Library.*

Ortega, K. L., 2018: Evaluating multi-radar, multi-sensor products for surface hailfall estimation. *Electronic Journal of Severe Storms Meteorology*, 13(1), 1-36.

Pandas Development Team, 2020: pandas-dev/pandas: Pandas. Zenodo.

Pickands, J., 1975: Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119-131.

Rasterio contributors, 2026: *Rasterio: access to geospatial raster data for Python programmers.*

Scarrott, C. and A. MacDonald, 2012: A review of extreme value threshold estimation and uncertainty quantification. *REVSTAT*, 10(1), 33-60.

SciPy Developers, 2020: SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nature Methods*, 17, 261-272.

Smith, T. M., et al., 2016: Multi-Radar Multi-Sensor severe weather and aviation products: initial operating capabilities. *Bulletin of the American Meteorological Society*, 97, 1617-1630.

Wendt, N. A. and I. L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Weather and Forecasting*, 36, 645-659.

Williams, S. S., K. L. Ortega, T. M. Smith, and coauthors, 2022: Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms. *Bulletin of the American Meteorological Society*, 103, E838-E854.

Witt, A., et al., 1998: An enhanced hail detection algorithm for the WSR-88D. *Weather and Forecasting*, 13, 286-303.
