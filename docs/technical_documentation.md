# Technical Documentation

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Grid Specification

| Parameter | Value |
|---|---:|
| CRS | EPSG:4326 |
| Resolution | 0.05° × 0.05° |
| Rows | 520 |
| Columns | 1180 |
| Total cells | 613,600 |
| Row orientation | north-to-south |
| Column orientation | west-to-east |
| Raster dtype | float32 unless otherwise stated |
| Compression | LZW tiled GeoTIFF |

Any change to these constants is a model-version change and requires regeneration of downstream outputs.

---

## 2. Stage 01 — MYRORSS Download and Raster Build

**Script:** `scripts/01_download_myrorss.py`  
**Input:** MYRORSS sparse NetCDF files on public AWS S3.  
**Output:** `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`

### Technical behavior

1. List all MYRORSS MESH files for each day.
2. Download and decompress gzipped NetCDF files.
3. Parse sparse pixel arrays.
4. Accumulate daily maximum MESH at native resolution.
5. Subset to CONUS.
6. Aggregate to 0.05° using block maximum.
7. Write a single-band GeoTIFF.

### Validation

- Output directory exists.
- File count is plausible.
- Random samples open with rasterio.
- CRS is EPSG:4326.
- Shape is 520 × 1180.
- Values are finite and non-negative.

---

## 3. Stage 02 — MRMS Download and Raster Build

**Script:** `scripts/02_download_mrms_mesh.py`  
**Input:** MRMS MESH GRIB2 files on public AWS S3.  
**Output:** same raster path and format as Stage 01.

### Technical behavior

MRMS uses 0–360° longitude and south-to-north native orientation. Stage 02 extracts the CONUS subset, flips orientation, accumulates daily maximum MESH, aggregates by block maximum, and writes 0.05° GeoTIFFs.

### Validation

Same as Stage 01, with additional orientation sanity checks.

---

## 4. Stage 03 — SPC Download

**Script:** `scripts/03_download_spc.py`  
**Input:** SPC daily report CSVs.  
**Output:** `data/historical/spc/YYYY/YYMMDD_rpts_hail.csv`

SPC reports are validation/calibration support only.

### Validation

- CSV files exist.
- Files are non-empty when reports are present.
- Sample files parse successfully.

---

## 5. Stage 04a — ERA5 Isotherms

**Script:** `scripts/04a_download_era5_isotherms.py`  
**Output:** `data/historical/era5/era5_monthly_isotherms_conus.nc`

### Variables

```text
h_0C_km
h_m20C_km
```

### Validation

- NetCDF exists.
- Required variables exist.
- Medians fall within physically plausible bounds.
- NaNs are not widespread after fallback filling.

---

## 6. Stage 04b — GridRad Gap Fill

**Script:** `scripts/04b_fill_gridrad_gap.py`  
**Input:** GridRad/GridRad-Severe NetCDF files and ERA5 isotherms.  
**Output:** daily MESH75 GeoTIFFs and `gridrad_days.txt`.

### Technical behavior

1. Locate GridRad-Severe first, hourly GridRad second.
2. Load reflectivity profiles.
3. Identify active columns exceeding reflectivity threshold.
4. Compute SHI above the freezing level.
5. Convert SHI to MESH75:

```text
MESH75 = 15.096 × SHI^0.206
```

6. Write daily maximum raster.

### Validation

- GridRad day list exists.
- Output rasters exist for available days.
- Peak values are plausible.
- ERA5 fallback usage is logged.

---

## 7. Stage 05 — Bias Correction and Environmental Filtering

**Script:** `scripts/05_apply_mesh_bias_correction.py`  
**Input:** raw daily MESH rasters.  
**Output:** corrected daily MESH75 rasters.

### Required logic

For MYRORSS and MRMS:

```text
apply MESH75 recalibration
```

For GridRad:

```text
apply optional conditional calibration if available
otherwise apply quantile mapping
```

For all sources:

```text
apply optional probabilistic filter if available
otherwise apply deterministic environmental filters
```

### Optional artifacts

```text
data/analysis/calibration/gridrad_cqm_model.pkl
data/analysis/calibration/hail_filter_model.pkl
```

### Required fallback behavior

Stage 05 must run without optional artifacts. `--skip-ml` must force deterministic fallback.

### Validation

- Corrected rasters exist.
- Output count is close to input count.
- CRS and shape are unchanged.
- Filtered pixel count is plausible.
- Calibration diagnostics are written.

---

## 8. Stage 06 — Validation Against SPC

**Script:** `scripts/06_validate_mesh_vs_spc.py`  
**Output directory:** `data/historical/validation/`

### Required outputs

```text
mesh_vs_spc_pairs.csv
calibration_report.csv
spatial_bias_1deg.csv
validation_summary.txt
```

### Required figures

```text
docs/figures/analysis/mesh_vs_spc_scatter.png
docs/figures/analysis/detection_by_size.png
```

### Interpretation

SPC is incomplete. Validation metrics should be interpreted as consistency diagnostics, not perfect error rates.

---

## 9. Stage 07 — Climatology

**Script:** `scripts/07_build_hail_climo.py`  
**Output:** `data/historical/mesh_0.05deg_climo/`

### Required outputs

```text
climo_001.tif ... climo_366.tif
annual_mean_mesh75.tif
annual_hail_days.tif
```

### Validation

- 366 climatology files exist.
- Annual summaries exist.
- Shapes and CRS are correct.

---

## 10. Stage 08 — Event Catalog

**Script:** `scripts/08_build_event_catalog.py`  
**Output:** `data/historical/events/`

### Required outputs

```text
event_catalog.csv
event_peaks.npz
```

### Event grouping constraints

```text
temporal gap <= 2 days
buffered footprint overlap required
duration <= 5 days
centroid displacement <= configured limit
peak intensity jump <= configured limit
```

### Sparse storage requirement

`event_peaks.npz` stores rows, columns, and values by event. Dense event cubes are not production storage.

### Validation

- CSV exists and has events.
- NPZ exists.
- Each event has matching row/col/value lengths.
- Duration cap is not violated.
- Peak hail values are plausible.

---

## 11. Stage 09 — Regional CDF Fitting

**Script:** `scripts/09_fit_cdf_regional.py`  
**Output:** `data/analysis/cdf/`

### Required outputs

```text
cdf_parameters.npz
rp_XXXXXyr_hail.tif
region_map.tif
fitting_report.csv
threshold_selection.csv
mrl_diagnostics/
```

### CDF model

```text
annual occurrence probability
lognormal body
GPD tail
regional xi pooling
```

### Threshold diagnostics

`threshold_selection.csv` should contain candidate thresholds, exceedance count, ξ, σ, stability score, GOF score, MRL score, and selected flag.

### Validation

- Parameter arrays exist.
- RP maps exist.
- Values are finite.
- Return-period maps are broadly monotonic with return period.
- ξ values are bounded.

---

## 12. Stage 10 — Spatially Pooled CDF

**Script:** `scripts/10_build_smooth_cdf.py`  
**Output:** smoothed return-period maps.

### Technical behavior

Stage 10 pools nearby observations within a configured radius and uses distance-decay weights to rebuild smoother CDF maps.

### Validation

- Smoothed RP maps exist.
- `p_occurrence_smooth.tif` exists.
- Values remain plausible.
- Smoothed maps do not introduce extreme artifacts.

---

## 13. Stage 11 — Occurrence Probabilities

**Script:** `scripts/11_build_occurrence_probs.py`

### Outputs

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

### Validation

- Values are in [0, 1].
- Higher thresholds have lower or equal probability than lower thresholds.

---

## 14. Stage 12 — CONUS Mask and Topographic Correction

**Script:** `scripts/12_apply_conus_mask.py`

### Outputs

```text
data/analysis/conus_mask/conus_mask.tif
data/analysis/topography/topo_correction.tif
```

### v2.1 correction

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

### Validation

- Mask exists.
- Correction factor is within bounds.
- Outside-CONUS cells are masked.

---

## 15. Stage 13 — Stochastic Catalog

**Script:** `scripts/13_generate_stochastic_catalog.py`

### Outputs

```text
data/stochastic/catalog/stochastic_event_summary.parquet
data/stochastic/maps/rp_XXXXXyr_stochastic.tif
data/stochastic/pet/pet_occurrence.csv
data/stochastic/pet/pet_aggregate.csv
```

### Critical implementation rule

Do not reconstruct all events into dense arrays. Use sparse arrays:

```text
rows, cols, vals
```

### Stochastic steps

1. Draw event count from Poisson distribution.
2. Draw event date from seasonal distribution.
3. Select historical template with seasonal weights.
4. Apply sparse translation.
5. Apply intensity scaling.
6. Optionally perturb sparse shape.
7. Update annual maxima.

### Validation

- Smoke test with `--n-years 1000`.
- RP maps exist.
- PET tables exist.
- Sparse logic remains memory bounded.

---

## 16. Stage 14 — Vulnerability

**Script:** `scripts/14_build_vulnerability.py`

### Outputs

```text
mdr_curves.csv
mdr_parameters.npz
```

### Important caveat

These curves are placeholders and should not be used for production loss estimates without claims calibration.

---

## 17. Stage 15 — Figures

**Script:** `scripts/15_render_figures.py`

### Output directories

```text
docs/figures/historical/
docs/figures/stochastic/
docs/figures/analysis/
```

### Required categories

- return-period maps;
- stochastic maps;
- EP curves;
- validation figures;
- analytical-vs-stochastic comparisons;
- event summaries;
- vulnerability curves.

---

## 18. Validation Commands

Before full run:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

After outputs exist:

```bash
python run_pipeline.py --validate
```

---

## 19. Run Manifest

Recommended manifest path:

```text
data/analysis/run_manifest.json
```

Manifest should record:

- model version;
- git commit;
- random seed;
- stages run;
- calibration mode;
- filtering mode;
- stochastic years;
- run date;
- script versions if available.

---

## 20. Pre-Run Hardening Summary

The v2.1 hardening pass emphasizes:

- sparse-safe Stage 13;
- deterministic Stage 05 fallback;
- event merge sanity checks;
- GPD threshold diagnostics;
- expanded tests;
- synchronized documentation.
