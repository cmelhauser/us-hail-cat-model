# Migration Plan: Hail Cat Model v1.0 → v2.0

**Date:** 2026-05-01
**Status:** All 15 v2.0 stages written. Pipeline ready for execution.
**Goal:** Replace SPC-report-based hazard input with MRMS/GridRad MESH radar data as the primary source, increase grid resolution to 0.05°, apply literature-based bias correction, and retain SPC data for validation. Implement all improvements from the prioritized roadmap.

---

## 1. Pipeline Architecture Comparison

### v1.0 Pipeline (SPC-based, 15 stages — archived)

```
Stage 01  Download Census population data
Stage 02  Build county population trend
Stage 03  Download SPC storm reports
Stage 04  Build storm trends / compute β
Stage 05  Compute spatial neighborhood β per county
Stage 06  Build raw 0.05° rasters from SPC point reports
Stage 07  Apply population debiasing (β = 2.37)
Stage 08  Aggregate debiased rasters
Stage 09  Build daily climatology (366 files)
Stage 10  Event catalog + CDF fitting + spatial correlation
Stage 11  Spatially-pooled CDF rebuild (150 km)
Stage 12  Occurrence probability rasters (8 thresholds)
Stage 13  CONUS mask + spatial smoothing
Stage 14  50,000-year stochastic catalog (event-resampling)
Stage 15  Render all figures
```

### v2.0 Pipeline (MESH-based, 0.05° grid, 15 stages)

```
Stage 01   Download MYRORSS MESH data (1998–2011) from AWS S3, aggregate to 0.05°
Stage 02   Download operational MRMS MESH data (2020–present), aggregate to 0.05°
Stage 03   Download SPC hail reports (validation/calibration only)
Stage 04a  Download ERA5 monthly isotherm heights for SHI computation
Stage 04b  Fill 2012–2019 gap: compute MESH75 from GridRad 3D NEXRAD reflectivity
Stage 05   Unified bias correction: MESH75 recalibration + GridRad cross-calibration + env filter
Stage 06   Validate corrected MESH against SPC reports (calibration report)
Stage 07   Build daily climatology (366 files at 0.05°)
Stage 08   Event identification (synoptic grouping) + build event catalog
Stage 09   CDF fitting: lognormal + GPD with regional ξ pooling + MRL diagnostics
Stage 10   Spatially-pooled CDF rebuild (150 km kernel)
Stage 11   Occurrence probability rasters (8 thresholds)
Stage 12   CONUS mask + topographic correction (DEM overlay)
Stage 13   Stochastic catalog: 50,000-yr, calibrated σ, spatial translate enabled
Stage 14   Vulnerability curves (MDR by construction class) [placeholder]
Stage 15   Render figures + validation report
```

---

## 2. What Changes, What Stays

### Scripts that are REPLACED (archived to scripts/archive/v1/)

| v1.0 Script | Reason | Replacement |
|---|---|---|
| `01_download_population.py` | Population data no longer needed for primary pipeline | Archived |
| `02_build_population_trend.py` | Population debiasing retired | Archived |
| `04_build_storm_trends.py` | β computation retired | Archived |
| `05_build_spatial_beta.py` | Spatial β retired | Archived |
| `06_build_hail_rasters.py` | SPC→raster replaced by MESH→raster | `04_build_mesh_rasters.py` |
| `07_build_hail_debias.py` | Population debiasing eliminated | `05_apply_mesh_bias_correction.py` |
| `08_build_hail_agg.py` | Aggregation direction reversed (downscale, not upscale) | Folded into stage 04 |

### Scripts that are UPDATED (in place)

| v1.0 Script | v2.0 Script | Key Changes |
|---|---|---|
| `03_download_spc.py` | `03_download_spc.py` | Same logic; now labeled as validation/calibration source |
| `09_build_hail_climo.py` | `07_build_hail_climo.py` | Re-numbered; reads 0.05° corrected MESH rasters |
| `10_hail_catmodel_pipeline.py` | `08_build_event_catalog.py` | Event identification only; CDF moved to stage 09 |
| `11_build_smooth_cdf.py` | `10_build_smooth_cdf.py` | Re-numbered; operates on 0.05° grid |
| `12_build_occurrence_probs.py` | `11_build_occurrence_probs.py` | Re-numbered |
| `13_apply_conus_mask.py` | `12_apply_conus_mask.py` | Re-numbered; adds topographic correction |
| `14_generate_stochastic_catalog.py` | `13_generate_stochastic_catalog.py` | Calibrated σ from data; SPATIAL_TRANSLATE enabled |
| `15_render_figures.py` | `15_render_figures.py` | Updated for new data paths + validation figures |

### NEW scripts

| Script | Purpose |
|---|---|
| `01_download_myrorss.py` | Download MYRORSS MESH (1998–2011) from AWS S3 |
| `02_download_mrms_mesh.py` | Download operational MRMS MESH (2012–present) |
| `04_build_mesh_rasters.py` | Aggregate native MESH to 0.05° daily GeoTIFFs |
| `05_apply_mesh_bias_correction.py` | MESH75 recalibration + environmental filtering |
| `06_validate_mesh_vs_spc.py` | Cross-validate corrected MESH against SPC reports |
| `09_fit_cdf_regional.py` | CDF fitting with MRL diagnostics + regional GPD ξ pooling |
| `14_build_vulnerability.py` | MDR curves by construction class (placeholder) |

---

## 3. Grid Specification Change

### v1.0 Grid (archived)

| Parameter | Value |
|---|---|
| Resolution | SPC-report-based, variable |
| Active cells | ~8,362 |

### v2.0 Grid

| Parameter | Value |
|---|---|
| Resolution | 0.05° (~5.5 km) |
| Extent | lon [−125, −66], lat [24, 50] |
| Dimensions | 1,180 cols × 520 rows = 613,600 cells |
| Expected active cells | ~100,000–150,000 (with MESH sensitivity) |

**Rationale:** 0.05° preserves spatial variability of hail swaths (typical swath width 5–20 km) while providing sufficient spatial averaging for stable CDF statistics. Native MRMS (~1 km) is too fine for CDF fitting (most cells would have 0–2 events). The 0.05° grid matches the v1.0 raw raster resolution, so existing grid infrastructure is reused.

**Memory implications:** Event peak array grows from (n_events, 104, 236) to (n_events, 520, 1180). At float32, a 3,000-event catalog requires ~7.3 GB vs 0.3 GB in v1.0. Sparse storage or active-cell-only indexing is recommended.

---

## 4. Data Directory Structure (v2.0)

```
data/
├── myrorss/                      ← MYRORSS MESH downloads (1998–2011)
│   └── YYYY/MM/DD/               ← Daily subdirectories
├── mrms/                         ← Operational MRMS MESH (2012–present)
│   └── YYYY/MM/DD/               ← Daily subdirectories
├── spc/                          ← SPC reports (validation only)
│   └── YYYY/
├── mesh_0.05deg/                 ← Aggregated 0.05° daily MESH rasters
│   └── YYYY/mesh_YYYYMMDD.tif
├── mesh_0.05deg_corrected/       ← Bias-corrected 0.05° MESH rasters
│   └── YYYY/mesh_YYYYMMDD.tif
├── mesh_0.05deg_climo/           ← 366 daily climatology files
├── mesh_0.05deg_CDF/             ← CDF layer outputs
├── stochastic/                   ← Stochastic catalog outputs
│   └── maps/                    ← Stochastic RP and p_occ GeoTIFFs
├── validation/                   ← MESH vs SPC cross-validation outputs
├── topography/                   ← DEM and derived correction grids
└── vulnerability/                ← MDR curves and lookup tables [future]
```

---

## 5. New Dependency Requirements

### Added to requirements.txt

```
# v2.0 additions
s3fs>=2023.1          # AWS S3 access for MYRORSS/MRMS downloads
boto3>=1.26           # AWS SDK (alternative to s3fs)
cfgrib>=0.9.10        # GRIB2 reading for MRMS operational data
eccodes>=1.5          # GRIB2 backend (required by cfgrib)
netCDF4>=1.6          # NetCDF reading for MYRORSS/GridRad
h5py>=3.8             # HDF5 backend
tqdm>=4.65            # Progress bars for large downloads
scikit-learn>=1.2     # K-means clustering for regional GPD grouping
```

### Removed/optional

```
# v1.0 only (archived, not required for v2.0 primary pipeline)
# Population download/trend scripts still available in scripts/archive/v1/
```

---

## 6. Implementation Phases

### Phase 1: Data Acquisition (Stages 01–03)
**Estimated effort:** 2–3 days
**Estimated download time:** 12–48 hours (depending on bandwidth)

- Write `01_download_myrorss.py`: AWS S3 download of MYRORSS MESH (1998–2011)
- Write `02_download_mrms_mesh.py`: Iowa State archive or AWS download (2012–present)
- Update `03_download_spc.py`: mark as validation source, no functional changes
- Validate: spot-check downloaded files for format consistency, spatial extent, temporal coverage

### Phase 2: Raster Construction + Bias Correction (Stages 04–06)
**Estimated effort:** 3–4 days

- Write `04_build_mesh_rasters.py`:
  - Read GRIB2 (MRMS) and NetCDF (MYRORSS) MESH files
  - Extract daily maximum MESH per native grid cell
  - Aggregate to 0.05° using block-max (not block-sum — MESH is a size estimate, not a count)
  - Output: single-band float32 GeoTIFF per day (value = max MESH in inches)
- Write `05_apply_mesh_bias_correction.py`:
  - Apply MESH75 recalibration (Murillo & Homeyer 2019 SHI→size mapping)
  - Apply environmental filter: require CAPE > threshold from ERA5/RAP reanalysis
  - Apply lightning proximity filter: require CG lightning within 40 km (if lightning data available; otherwise environmental-only)
  - Output: corrected 0.05° daily GeoTIFFs
- Write `06_validate_mesh_vs_spc.py`:
  - For each SPC hail report (2004–present), extract the co-located corrected MESH value
  - Compute bias statistics: mean bias, RMSE, percentile mapping
  - Output: calibration report CSV, scatter plots, spatial bias maps

### Phase 3: Core Model Rebuild (Stages 07–12)
**Estimated effort:** 4–5 days

- Update `07_build_hail_climo.py`: read 0.05° corrected MESH rasters
- Rewrite `08_build_event_catalog.py`: event identification only (same synoptic grouping rules: ≤1-day gap, 83 km overlap, 5-day cap), operating on 0.05° grid
  - **Key change:** event_peak_array is now (n_events, 520, 1180) — use sparse or active-cell-only storage
- Write `09_fit_cdf_regional.py`:
  - Per-cell annual maximum series from event_peak_array
  - MRL diagnostic plots per region (Great Plains, Southeast, Northeast, Mountain West, Front Range)
  - Lognormal body fit (MLE or L-moments)
  - GPD tail: regional ξ pooling via L-moment ratio matching (Hosking & Wallis 1997)
  - Cell-specific σ within each region
  - Output: CDF parameters, MRL diagnostic figures, region assignments
- Update `10_build_smooth_cdf.py`: spatial pooling on 0.05° grid (may need reduced kernel if cell density increases)
- Update `11_build_occurrence_probs.py`: no structural change, re-numbered
- Update `12_apply_conus_mask.py`: add topographic correction
  - Download SRTM/GMTED2010 DEM
  - Parameterize elevation-dependent hail survival (literature-based)

### Phase 4: Stochastic + Vulnerability (Stages 13–14)
**Estimated effort:** 3–4 days

- Update `13_generate_stochastic_catalog.py`:
  - Calibrate σ from empirical inter-annual intensity variance in event catalog
  - Enable SPATIAL_TRANSLATE with physically motivated displacement distribution
  - Address memory: active-cell-only storage for 0.05° event arrays
- Write `14_build_vulnerability.py` (placeholder):
  - Implement lognormal MDR curves for 3–5 construction classes
  - No exposure layer yet — vulnerability is parameterized, not applied to TIV

### Phase 5: Figures + Documentation + Cleanup (Stage 15 + docs)
**Estimated effort:** 2–3 days

- Update `15_render_figures.py`: all new data paths, 0.05° grid, add validation figures
- Update all documentation: README, methodology, executive summary, technical docs, data dictionary
- Archive v1.0 scripts to `scripts/archive/v1/`
- Remove outdated data references from documentation
- Remove outdated figures from `docs/figures/`

---

## 7. Files to Archive or Remove

### Archive to scripts/archive/v1/

```
scripts/01_download_population.py
scripts/02_build_population_trend.py
scripts/04_build_storm_trends.py
scripts/05_build_spatial_beta.py
scripts/06_build_hail_rasters.py
scripts/07_build_hail_debias.py
scripts/08_build_hail_agg.py
```

### Remove from docs/figures/ (regenerated by stage 15)

All existing figures in:
```
docs/figures/historical/
docs/figures/stochastic/
docs/figures/analysis/
```

These will be regenerated by the v2.0 pipeline with MESH-based data.

### Remove from docs/ (replaced by v2.0 versions)

The following docs are replaced in-place (not removed, but fully rewritten):
```
docs/README.md
docs/executive_summary.md
docs/methodology.md
docs/technical_documentation.md
docs/data_dictionary.md
docs/reproduce.md
docs/explainer.md
```

---

## 8. Validation Plan

### 8.1 MESH vs SPC Cross-Validation (Stage 06)

For each co-located SPC report + corrected MESH observation:
- Compute mean bias by hail size bin
- Compute spatial bias maps (does MESH systematically over/underestimate in certain regions?)
- Verify that MESH captures >90% of SPC reports ≥1.0" in the co-located cells
- Document nighttime event capture improvement (MESH should detect events where SPC has zero reports)

### 8.2 Return Period Validation (Stage 15)

- Compare v2.0 return period maps to v1.0 maps — document spatial pattern changes
- Compare v2.0 100-year RP values to published AIR/RMS benchmark ranges (where available)
- Compare stochastic PET to historical PET — should be consistent within confidence bounds

### 8.3 Population-Independence Verification

- Compute correlation between v2.0 return period values and local population density
- Should be near zero (vs. residual correlation in v1.0 despite debiasing)
- Plot return period values vs. population density for a diagnostic panel

---

## 9. Key Parameters (v2.0)

| Parameter | v1.0 Value | v2.0 Value | Source |
|---|---|---|---|
| Grid resolution | v1.0 SPC-based | 0.05° | Section 10 of literature review |
| Primary data source | SPC reports | MRMS/MYRORSS MESH | Wendt & Jirak 2021; Ortega et al. 2022 |
| Record period | 2004–2025 (22 yr) | 1998–present (~28 yr) | MYRORSS + operational MRMS |
| MESH calibration | N/A | MESH75 (Murillo & Homeyer 2019) | Murillo et al. 2021 |
| Population debiasing | β = 2.37 | Eliminated (radar-based) | — |
| GPD threshold | 2.0" (heuristic) | Per-region MRL-validated | Coles 2001; Scarrott & MacDonald 2012 |
| GPD ξ estimation | Per-cell L-moments | Regional pooled L-moments | Hosking & Wallis 1997 |
| Fallback cells | 88 empirical-only | Target: <10 | Regional ξ pooling |
| Event grouping | ≤1-day, 83 km, 5-day cap | Same | Unchanged |
| Stochastic perturbation σ | 0.15 (a priori) | Calibrated from data | event_peak_array empirical CV |
| Spatial translation | Disabled | Enabled, ±2–4 cells | Event centroid variance |
| Simulation years | 50,000 | 50,000 | Unchanged |
| Topographic correction | None | DEM-based hail survival | Li et al. 2021 |
| Vulnerability | None | Lognormal MDR, 3–5 classes | Brown et al. 2015; IBHS |
