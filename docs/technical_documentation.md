# Technical Documentation

**CONUS Hail Catastrophe Model v2.2**

---

## 1. Purpose

This document describes the implementation contract for the v2.2 hail hazard pipeline. It complements `docs/methodology.md`: the methodology document explains the scientific rationale, while this document specifies stage behavior, inputs, outputs, invariants, validation checks, and failure modes.

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
**Output:** `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif` (label = **convective day** at 12 UTC start; §2.6 in `methodology.md`)
**Manifest:** `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`

### 3.1 Technical behavior

1. Iterate convective-day labels from April 1998 through December 2011.
2. For each label, list MYRORSS keys from the two UTC calendar S3 prefixes that overlap the 12 UTC → 12 UTC window, then filter by parsed timestep UTC (`list_mesh_keys_for_convective_day`).
3. Accept both plain NetCDF and gzipped NetCDF objects.
4. Decode sparse pixel arrays into the native MYRORSS grid.
5. Accumulate convective-day maximum MESH at native resolution (12 UTC → 12 UTC; see `methodology.md` §2.6).
6. Subset to the CONUS model domain.
7. Aggregate to 0.05 degree by block maximum.
8. Apply Stage 01 physical QA: non-finite, negative, and `>300.0 mm` values
   are reset to `0.0` before downstream use.
9. Write one daily GeoTIFF with GDAL tag `CONVECTIVE_WINDOW_UTC`.
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
2. download or stream source GRIB2 files (optional `--workers N` parallel threads per day for S3 + decode; default 8);
3. extract the CONUS subset;
4. convert longitude convention where needed;
5. flip south-to-north native orientation into north-to-south model orientation;
6. accumulate convective-day maxima (12 UTC → 12 UTC; same helpers as Stage 01);
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

## 7. Stage 04b — GridRad download (NCAR RDA / THREDDS)

**Script:** `scripts/04b_download_gridrad.py`  
**Input:** NCAR RDA THREDDS catalogs + `fileServer` URLs:

| Dataset | ID | Role |
|---|---|---|
| GridRad V3.1 hourly | **d841000** | Hourly fallback through 2017 (all months) |
| GridRad V4.2 warm-season hourly | **d841001** | Hourly fallback Apr–Aug 2018+ when V3.1 is empty |
| GridRad-Severe 5-min | **d841006** | Preferred source (~100 severe events/year) |

Optional `GDEX_TOKEN` / `GDEX_API_TOKEN` or `~/.netrc` for authenticated GETs.  
**Output:** NetCDF files under:

```text
data/historical/gridrad/by_convective_day/YYYYMMDD/*.nc
data/historical/gridrad_severe/by_convective_day/YYYYMMDD/*.nc
```

### 7.1 Default schedule (disk- and memory-friendly)

By default the script **does not** build one giant download list for the whole
2012–01–01 … 2020–10–13 range. Instead, for **each convective day** (12 UTC → 12 UTC) it:

1. Queries THREDDS for that day’s filenames (month catalog for hourly; year + day catalog for severe).
2. Downloads only that day’s files (resumable: existing non-empty `.nc` files are skipped).

This caps the in-memory plan to **one day’s file list** and avoids holding hundreds of thousands of `DownloadItem` rows at once.

### 7.2 Concurrency and legacy mode

- **`--workers` (default `1`):** number of **parallel HTTP streams within a single day’s** download batch. NCAR guidance: keep total concurrent streams **≤ 10** across anything you run in parallel.
- **`--plan-all-days-first`:** restores the legacy workflow (catalog **all** days into one list, then download). Use only if you intentionally want that higher peak RAM footprint.

### 7.3 Reliability and tuning

- HTTP **retries / backoff** for transient 5xx, timeouts, and chunked read issues.
- **`--connect-timeout`**, **`--read-timeout`** (catalog XML), **`--download-read-timeout`** (NetCDF streams).
- Optional **`RDA_THREDDS_ORIGIN`** if NCAR ever documents an alternate THREDDS host with the same path layout.

### 7.4 Public helpers (for Stage 04c)

- **`download_for_day(...)`** — plan + download all files for one `date` (explicit `hourly` / `severe` flags).
- **`download_for_day_adaptive(...)`** — **severe-first** policy used by Stage **04c** with `--with-04b-download`:
  1. Skip downloads when staged GridRad-Severe already covers the convective window.
  2. If the severe catalog lists timesteps, download **severe only**.
  3. Re-check window coverage; if gaps remain, download **hourly** as fill (**d841000**, then **d841001** for Apr–Aug 2018+).
  4. If no severe catalog data exists, download **hourly only** (same **d841000 → d841001** order).
- **`severe_catalog_has_convective_data(...)`** — lightweight THREDDS plan check (no GETs).
- **`download_planned_items(...)`** — download a pre-built list (used internally).

---

## 8. Stage 04c — GridRad gap fill (SHI → MESH75)

**Script:** `scripts/04c_fill_gridrad_gap.py`  
**Input:** GridRad or GridRad-Severe NetCDF files on disk **and/or** live downloads when `--with-04b-download` is set; plus `data/historical/era5/era5_monthly_isotherms_conus.nc` from Stage 04a (or climatological fallback if missing).  
**Output:** `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif` for gap days and `data/historical/mesh_0.05deg/gridrad_days.txt`.  
**Calendar span:** 2012-01-01 through **2020-10-13** (`GAP_END` in script); MRMS begins **2020-10-14**.

### 8.1 Default run shape (disk- and memory-friendly)

1. **Sequential convective days by default:** `--workers` defaults to **`1`** (one Python process; no `ProcessPoolExecutor` fan-out). Increase only if you have RAM headroom and want parallel days.
2. **Per-day NetCDF handling:** each file is opened, processed column-by-column, and closed before the next file; the daily accumulator is a single **520×1180** `float32` array (same order of magnitude as other daily stages).
3. **Automatic cleanup of GridRad staging:** after **each** convective day is handled (whether the GeoTIFF was written, skipped because it already existed, marked no-data, or ended in error), the directories  
   `data/historical/gridrad/by_convective_day/YYYYMMDD/` and `data/historical/gridrad_severe/by_convective_day/YYYYMMDD/`  
   are removed with `shutil.rmtree` **unless** you pass **`--keep-gridrad-inputs`**.  
   - **Why:** keeps the GridRad tree from occupying a full multi-year archive on disk when you only need the derived `mesh_*.tif` products.  
   - **Re-runs / debugging:** pass **`--keep-gridrad-inputs`** so NetCDF inputs remain for inspection or so you can re-run 04c without re-downloading.

### 8.2 Single-pass download + gap fill

```bash
python scripts/04c_fill_gridrad_gap.py --with-04b-download
```

**`run_pipeline.py`:** when it runs stage **04c** (not in **`--validate`** mode), it
passes **`--with-04b-download --workers 4`** by default. It also **auto-skips
standalone stage 04b** on full runs and on **`--from`** resumes that start before
**04b**, so GridRad is not staged twice. Use **`python run_pipeline.py --only 04b`**
or **`--from 04b`** for the legacy NCAR-only downloader.

This loads Stage **04b** in-process via `importlib` (module registered in `sys.modules`
before `exec_module` so dataclasses resolve correctly in worker processes). With
**`--workers 1`**, the parent holds one `requests.Session` for all days. With
**`--workers N`** and **`N > 1`**, worker processes use a pool initializer so **04b**
is loaded **once per worker** (not once per day); each convective day still opens a
**new** `requests.Session`, runs
**`download_for_day_adaptive`** when the output GeoTIFF is absent, then **`process_day`**.
Expect roughly **`N × (--04b-download-workers)`** peak concurrent HTTP GETs unless
downloads skip quickly—stay within NCAR/GDEX throttling.

**Severe-first policy:** most convective days download only GridRad-Severe (~288
5-min files) instead of severe plus hourly (~24 extra files). Hourly is fetched only
when the severe catalog is empty or staged severe files do not span the full
12 UTC → 12 UTC window (coverage checked via `convective_window_coverage_ok` in
`scripts/_io.py`).

#### Quick reference (mental model)

| Goal | Typical pattern |
|---|---|
| Parallel **gap-fill only** (inputs already downloaded) | `04c` with `--workers N` and **no** `--with-04b-download` |
| One convective day at a time; maximize **within-day** download concurrency | `04c --workers 1 --with-04b-download --04b-download-workers M` |
| Many convective days at once; each day may **download then process** | `04c --workers N --with-04b-download` — watch **`N × M`** against NCAR/GDEX limits |
| Keep a full local GridRad tree between stages | Run **`04b`** then **`04c`** separately; use **`--keep-gridrad-inputs`** on **04c** if you need to retain trees after each day |

On **04c**, **`--workers`** counts **processes across days**. **`--04b-download-workers`**
counts **parallel GETs inside** each day's download call (`download_for_day_adaptive` →
`download_for_day`) for the day assigned to that process.
They multiply for throttling purposes. Stage **04b**’s own CLI **`--workers`** is
unrelated: it only parallelizes GETs **within** each day when you run **04b** as its
own stage.

### 8.3 Technical behavior (per day)

1. **Source selection (staged files):** `find_gridrad_files()` prefers GridRad-Severe
   when it covers the convective window (≥6 files, edges within 30 min of window
   bounds, max gap ≤15 min for 5-min data). If severe is partial, merge severe plus
   hourly timesteps not within 3 min of a severe observation (`gridrad-severe-5min+hourly-fill`).
   If no severe files exist, use hourly only (`gridrad-hourly`).
2. **Load reflectivity (dBZ) for SHI:**
   - GridRad v3/v4 NetCDF files usually store physical reflectivity as **sparse** `Reflectivity(Index)` plus an `index` vector, not as a dense `(Altitude, Latitude, Longitude)` array.
   - Stage 04c reconstructs a dense 3-D reflectivity grid from sparse `Reflectivity` + `index` when needed.
   - **`Nradecho` is not used for SHI.** It is a 3-D echo mask/count field (typical range ~0–35), not dBZ. Using it as reflectivity produced all-zero gap-fill rasters on most hourly-only days before v2.1.1.
   - Longitudes in 0–360° form are converted to −180…180 before the CONUS mask and grid indexing.
3. Find columns with column-max reflectivity ≥ `Z_THRESHOLD` (40 dBZ).
4. Integrate SHI (Witt et al. 1998) using ERA5 0 °C / −20 °C heights from Stage 04a when available.
5. Convert SHI → MESH75: `MESH75 = 15.096 * SHI^0.206` (2021 corrigendum coefficients).
6. Take convective-day maxima on the canonical 0.05° grid; apply shared `MAX_HAIL_MM` QA via `sanitize_hail_values`.
7. Write GeoTIFF with optional GDAL diagnostic tags (`MAX_MESH75_MM`, `ACTIVE_CELLS`, `SOURCE`, `DATE`, `CONVECTIVE_WINDOW_UTC`); log one line per day with peak hail and active-cell count. Upsert `manifest_stage04c_gridrad.csv` (same schema as Stage 01/02 manifests).
8. Append `YYYYMMDD` to `gridrad_days.txt` when the day produced data.

**Re-run after reflectivity-reader fixes:** delete affected `mesh_YYYYMMDD.tif` files under `data/historical/mesh_0.05deg/` for gap days that were produced with the old reader (log lines showing `src=gridrad-hourly` and `active_cells=0` on storm days are a strong indicator), then re-run 04c for those dates.

### 8.4 Parallel days (`--workers` > 1)

Optional **process-based** parallelism across days. **`--with-04b-download`** is
allowed with **`--workers > 1`**: each worker runs download-then-process for its
assigned days (separate convective days, separate on-disk trees). **Do not** set
`workers × 04b-download-workers` so high that NCAR rate limits trigger. When
`workers > 1`, **deletion of GridRad inputs** still runs in the **parent** process
after each worker result returns.

**Disk headroom:** With **`--with-04b-download`** and **`--workers 4`**, up to four
full day trees may exist concurrently under `data/historical/gridrad_severe/` (often
~8–12 GB each on severe-hail days). A production run that filled the volume with
`[Errno 28] No space left on device` was recovered by stopping **04c**, deleting
stale staging for the active year, and restarting with **`--workers 2`**. Prefer
**`scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2`** over
`run_pipeline.py --only 04c` when free space is under ~250 GiB.

### 8.5 Scientific notes

GridRad is a gap-fill source. It should not be assumed exchangeable with MYRORSS or MRMS before calibration. Differences in temporal sampling, reflectivity processing, and vertical structure can affect high-percentile hail estimates.

### 8.6 Validation

- `gridrad_days.txt` exists after a successful run.
- Output rasters exist for processed days.
- Peak values fall within plausible hail-size bounds.
- ERA5 fallback usage is logged if isotherms are missing.
- Source-era distribution checks are available downstream.
- During gap-fill runs, inspect stage logs and GDAL tags on output GeoTIFFs to confirm non-zero peaks on hail days.

---

## 9. Stage 05 - Bias Correction and Environmental Filtering

**Script:** `scripts/05_apply_mesh_bias_correction.py`  
**Input:** raw daily MESH rasters
**Output:** corrected daily MESH75 rasters

### 9.1 Required logic

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

### 9.2 Optional artifacts

```text
data/analysis/calibration/gridrad_cqm_model.pkl
data/analysis/calibration/hail_filter_model.pkl
```

### 9.3 Hard requirement

Stage 05 must run successfully without optional artifacts. The `--skip-ml` flag must force deterministic behavior.

### 9.4 Validation

- Corrected rasters exist.
- Output count is close to input count after expected date filters.
- CRS and shape are unchanged.
- Values remain finite, non-negative, and no larger than 300.0 mm.
- Filtered-cell counts are plausible by month and region.
- Calibration diagnostics are written.
- Source-era distributions are reviewed for MYRORSS/GridRad/MRMS discontinuities.

---

## 10. Stage 06 - Validation Against SPC

**Script:** `scripts/06_validate_mesh_vs_spc.py`  
**Output directory:** `data/historical/validation/`

### 10.1 Required outputs

```text
mesh_vs_spc_pairs.csv
calibration_report.csv
spatial_bias_1deg.csv
validation_summary.txt
```

### 10.2 Required figures

```text
docs/figures/analysis/mesh_vs_spc_scatter.png
docs/figures/analysis/detection_by_size.png
```

### 10.3 Interpretation

SPC validation is a consistency exercise, not a perfect error calculation. False-alarm and miss metrics should be labelled as proxies because either the radar field or the report record can be incomplete at a given time and location.

### 10.4 Validation

- Pairing logic uses documented spatial and temporal tolerances.
- Report-size bins are stable.
- Regional summaries identify source or terrain biases.
- Figures are regenerated and visually inspected.

---

## 11. Stage 07 - Climatology

**Script:** `scripts/07_build_hail_climo.py`  
**Output:** `data/historical/mesh_0.05deg_climo/`

### 11.1 Required outputs

```text
climo_001.tif ... climo_366.tif
annual_mean_mesh75.tif
annual_hail_days.tif
```

### 11.2 Technical behavior

Stage 07 averages corrected daily MESH75 by day-of-year across available years. Zeros remain in the average because the output is expected daily hazard activity, not size conditional on hail occurrence.

Input is the **Stage 05 unified archive** (`mesh_0.05deg_corrected/`). MYRORSS, GridRad (all 04c products), and MRMS are already harmonized there; Stage 07 does not read raw source trees or GridRad version tags.

Stage 07 supports bounded concurrency via `--workers N` (threaded per-DOY raster reads). Use `--workers 1` for strictly sequential behavior.

### 11.3 Validation

- 366 climatology files exist.
- Annual summaries exist.
- Shapes and CRS match the grid contract.
- Seasonal maxima occur in meteorologically plausible months.
- Leap-day handling is explicit.

---

## 12. Stage 08 - Event Catalog

**Script:** `scripts/08_build_event_catalog.py`  
**Output:** `data/historical/events/`

### 12.1 Required outputs

```text
event_catalog.csv
event_peaks.npz
```

### 12.2 Event grouping constraints

```text
temporal gap <= 2 days
buffered footprint overlap required
duration <= 5 days
centroid displacement <= configured limit
peak intensity jump <= configured limit
```

### 12.3 Sparse storage requirement

`event_peaks.npz` stores event arrays by event ID:

```text
rows_<event_id>
cols_<event_id>
vals_<event_id>
```

Dense event cubes are prohibited as production event storage. They are memory-inefficient and can make Stage 13 infeasible at full catalog length.

### 12.4 Validation

- CSV exists and has events.
- NPZ exists and event IDs align with CSV.
- Every event has matching row, column, and value lengths.
- Duration cap is not violated.
- Active-cell counts are positive for non-empty events.
- Peak hail values are plausible.
- Physical merge constraints are audited.

### 12.5 Post-run hail-day climatology diagnostic

**Script:** `scripts/diagnostics/hail_day_climatology.py` (optional, not a pipeline stage)  
**Output:** `data/analysis/hail_day_climatology/`

Run after Stage 05 (and ideally after Stage 08) to benchmark per-cell severe-hail-day frequencies against Cintineo et al. (2012) and Murillo et al. (2021). Default thresholds: 25.4, 29.0, 35.56, 41.91, 50.8, and 63.25 mm.

Review:

- `threshold_benchmark_summary.csv` — Great Plains max/mean days/yr vs literature;
- `national_annual_hail_days.csv` — CONUS any-cell counts (comparable to Stage 08 λ);
- seasonal PNG — winter inflation at conventional 25.4 mm vs SPC report-day seasonality.

---

## 13. Stage 09 - Regional CDF Fitting

**Script:** `scripts/09_fit_cdf_regional.py`  
**Output:** `data/analysis/cdf/`

### 13.1 Required outputs

```text
cdf_parameters.npz
rp_XXXXXyr_hail.tif
region_map.tif
fitting_report.csv
threshold_selection.csv
mrl_diagnostics/
```

### 13.2 Statistical model

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

### 13.3 Threshold diagnostics

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

### 13.4 Validation

- Parameter arrays exist.
- Return-period maps exist.
- Values are finite and non-negative.
- Return-period maps are monotonic by return period at almost all valid cells.
- `xi` values are bounded and not dominated by fallback values.
- Regions have adequate pooled exceedance counts.

---

## 14. Stage 10 - Spatially Pooled CDF

**Script:** `scripts/10_build_smooth_cdf.py`  
**Output:** smoothed return-period maps

### 14.1 Technical behavior

Stage 10 pools nearby annual maxima or fitted parameters within a configured radius and applies distance-decay weights. The goal is to reduce noisy cell-level artifacts while preserving broad hail corridors.

### 14.2 Methodological caution

Spatial smoothing is not a full spatial extremes model. It improves marginal maps but does not estimate extremal dependence. Aggregate risk and multi-cell joint exceedance behavior must be checked through event-based stochastic outputs.

### 14.3 Validation

- Smoothed return-period maps exist.
- `p_occurrence_smooth.tif` exists.
- Values remain plausible.
- Smoothing does not introduce halos, edge artifacts, or shifted maxima.
- Smoothed maps remain broadly consistent with unsmoothed maps and empirical occurrence products.

---

## 15. Stage 11 - Occurrence Probabilities

**Script:** `scripts/11_build_occurrence_probs.py`

### 15.1 Outputs

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

### 15.2 Validation

- Values are in `[0, 1]`.
- Higher thresholds have lower or equal probability than lower thresholds.
- High-probability corridors are meteorologically plausible.
- Maps are used to sanity-check fitted CDF return levels.

---

## 16. Stage 11b - Public DEM Preparation

**Script:** `scripts/11b_prepare_topography.py`

Stage 11b downloads the public NOAA/NCEI ETOPO 2022 60 arc-second surface
elevation GeoTIFF and resamples it to the model's 0.05 degree grid. ETOPO 2022
is selected because it is public, globally complete, DOI-backed, and
scientifically documented, while its 60 arc-second product is operationally
small enough for a reproducible pipeline stage.

**Source DOI:** https://doi.org/10.25921/fd45-gt74

### 16.1 Outputs

```text
data/analysis/topography/source/ETOPO_2022_v1_60s_N90W180_surface.tif
data/analysis/topography/elevation_0.05deg.tif
```

Negative ocean elevations are clipped to 0 m because Stage 12 uses the raster
only for land topographic correction. The output GeoTIFF stores source URL, DOI,
reference, and processing metadata tags.

### 16.2 Validation

- Raster shape matches the canonical model grid.
- CRS is EPSG:4326.
- Values are finite and nonnegative.
- CONUS maximum elevation is within a physically plausible range.

---

## 17. Stage 12 - CONUS Mask and Topographic Correction

**Script:** `scripts/12_apply_conus_mask.py`

### 17.1 Outputs

```text
data/analysis/conus_mask/conus_mask.tif
data/analysis/topography/elevation_0.05deg.tif
data/analysis/topography/topo_correction.tif
```

### 17.2 v2.1 correction

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

### 17.3 Validation

- Mask exists.
- Correction factor is within configured bounds.
- Outside-CONUS cells are masked.
- Correction does not introduce discontinuities along state or source boundaries.
- Terrain correction is reviewed in mountainous regions.

Stage 12 supports bounded concurrency via `--workers N` when applying the mask to independent rasters.

---

## 18. Stage 13 - Stochastic Catalog

**Script:** `scripts/13_generate_stochastic_catalog.py`

### 18.1 Outputs

```text
data/stochastic/catalog/stochastic_event_summary.parquet
data/stochastic/maps/rp_XXXXXyr_stochastic.tif
data/stochastic/pet/pet_occurrence.csv
data/stochastic/pet/pet_aggregate.csv
```

### 18.2 Critical implementation rule

Do not reconstruct the event catalog as dense event rasters. The stochastic loop operates on:

```text
rows, cols, vals
```

### 18.3 Stochastic steps

1. Draw annual event count from `Poisson(lambda)`.
2. Draw event date from the smoothed seasonal distribution.
3. Select historical template using seasonal weights.
4. Calibrate global `sigma_perturb` as the median March-September monthly coefficient of variation of event peaks, clipped to `[0.10, 0.40]`.
5. Apply percentile-aware lognormal intensity scaling.
6. Apply sparse spatial translation.
7. Optionally perturb sparse shape with a reduced-intensity neighbor shell.
8. Update compact annual maxima.
9. Write empirical return-period maps and PET tables.

### 18.4 Validation

- Smoke test with `--n-years 1000`.
- Full catalog run completes without memory blowup.
- Return-period maps exist.
- PET tables exist.
- Sparse logic remains memory bounded.
- Analytical and stochastic maps are compared in Stage 15.

---

## 19. Stage 14 - Vulnerability

**Script:** `scripts/14_build_vulnerability.py`

### 19.1 Outputs

```text
mdr_curves.csv
mdr_parameters.npz
```

### 19.2 Important caveat

These curves are placeholders. They are suitable for pipeline integration and demonstration, but they are not production loss curves and should not be used for financial decisions without claims calibration.

### 19.3 Validation

- Curves are monotonic with hail size.
- Mean damage ratios remain in `[0, 1]`.
- Runtime warning or documentation clearly labels placeholder status.

---

## 20. Stage 15 - Figures

**Script:** `scripts/15_render_figures.py`

### 20.1 Output directories

```text
docs/figures/historical/
docs/figures/stochastic/
docs/figures/analysis/
```

### 20.2 Required categories

- analytical return-period maps;
- stochastic return-period maps;
- exceedance probability curves;
- validation figures;
- analytical-vs-stochastic comparisons;
- event summaries;
- vulnerability curves;
- GPD and tail diagnostics.

### 20.3 Figure QA

Figures are scientific diagnostics, not decoration. Review for:

- shifted CONUS domain or orientation error;
- suspicious maxima over Mexico, oceans, or masked cells;
- source-transition artifacts;
- over-smoothed hail corridors;
- analytical-vs-stochastic divergence;
- unreadable labels, legends, or colorbars;
- generated files that should remain untracked.

---

## 21. Validation Commands

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

## 22. Run Manifest

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

## 23. Pre-Run Hardening Summary

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

## 24. Failure Handling

If a stage fails:

1. stop before rerunning destructive or expensive work;
2. inspect the stage log;
3. determine whether outputs are partial, complete, or corrupt;
4. preserve diagnostic logs;
5. rerun only the failed stage or affected date range if the script supports it;
6. document the reason if generated outputs are deleted or replaced.

Never infer success from file existence alone. Use validation checks, logs, manifest coverage, and sample raster reads.

---

## 25. References

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
