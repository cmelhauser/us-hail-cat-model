# Technical Documentation

**CONUS Hail Catastrophe Model v2.0**

---

## Grid Specification

| Parameter | Value |
|---|---|
| Resolution | 0.05° × 0.05° (~5.5 km) |
| CRS | EPSG:4326 (WGS84) |
| Extent | lon [−125.005, −66.005], lat [24.005, 50.005] |
| Dimensions | 1180 cols × 520 rows = 613,600 cells |
| Origin (upper-left) | (−125.005, 50.005) |
| Cell convention | North-to-south, west-to-east |

## Pipeline Stages Reference

### Stage 01 — Download MYRORSS
- **Source:** `s3://noaa-oar-myrorss-pds/YYYY/MM/DD/MESH/00.25/`
- **Format:** Gzipped sparse NetCDF (pixel_x, pixel_y, MESH values in mm)
- **Native grid:** 0.01°, 3501 × 7001, lat origin 55.005°N
- **Processing:** Stream → daily max at native res → block-max 5×5 → 0.05° GeoTIFF
- **Output:** `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`

### Stage 02 — Download MRMS
- **Source:** `s3://noaa-mrms-pds/CONUS/MESH_00.50/YYYYMMDD/`
- **Format:** Gzipped GRIB2, full 3500 × 7000 grid
- **Native grid:** 0.01°, south-to-north, 0–360° longitude
- **Processing:** Stream → flip to N-S/-180 convention → daily max → block-max → 0.05°
- **Output:** Same path as stage 01

### Stage 03 — Download SPC
- **Output:** `data/historical/spc/YYYY/`

### Stage 04a — ERA5 Isotherms
- **CDS API request:** `reanalysis-era5-pressure-levels-monthly-means`, temperature + geopotential
- **Computation:** Interpolate 0°C and −20°C isotherm heights (km AGL) per month per grid cell
- **Output:** `data/historical/era5/era5_monthly_isotherms_conus.nc`

### Stage 04b — GridRad Gap Fill
- **Source:** NCAR RDA d841000 (V3.1) and d841006 (GridRad-Severe)
- **Priority:** GridRad-Severe (5-min) > GridRad hourly
- **Algorithm:** SHI (Witt 1998) from 3D reflectivity using ERA5 isotherms → MESH75
- **Constants:** MESH75 = 15.096 × SHI^0.206 (corrected 2021 corrigendum)
- **Sidecar:** `data/historical/mesh_0.05deg/gridrad_days.txt` (source tracking)
- **Output:** Same path as stages 01–02

### Stage 05 — Unified Bias Correction
- **Phase A:** Build quantile mapping from MYRORSS/GridRad overlap (2005–2011)
- **Phase B:** Apply source-specific corrections + environmental filter
- **MYRORSS/MRMS:** Witt→MESH75: 15.096 × (MESH_witt / 2.54)^0.412
- **GridRad:** Quantile mapping from Phase A
- **Env filter:** < 5 mm → 0; lat < 30°N in winter requires ≥ 25.4 mm
- **Output:** `data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif`
- **Calibration:** `data/analysis/calibration/gridrad_quantile_map.npz`

### Stage 06 — Validation
- **Method:** Match SPC reports to co-located corrected MESH75
- **Output:** `data/historical/validation/` (CSVs, summary, figures)

### Stages 07–15

### Stage 07 — Daily Climatology
- **Input:** `data/historical/mesh_0.05deg_corrected/`
- **Output:** `data/historical/mesh_0.05deg_climo/climo_DOY.tif` (366 files)
- **Method:** Per-DOY mean of corrected MESH75 across all years (including zeros)
- **Extras:** `annual_mean_mesh75.tif`, `annual_hail_days.tif`, seasonal figure

### Stage 08 — Event Catalog
- **Input:** `data/historical/mesh_0.05deg_corrected/`
- **Output:** `data/historical/events/event_catalog.csv` + `event_peaks.npz`
- **Grouping:** ≤1-day gap, 83 km overlap (15 cells at 0.05°), 5-day cap
- **Threshold:** 25.4 mm (1.0 inch)
- **Storage:** Sparse npz — per-event `(rows, cols, vals)` arrays. Compressed ~100× vs dense.

### Stage 09 — CDF Fitting (Regional GPD)
- **Input:** `data/historical/mesh_0.05deg_corrected/` (annual max computation)
- **Output:** `data/analysis/cdf/cdf_parameters.npz`, `rp_*yr_hail.tif`, `region_map.tif`, MRL plots
- **Regions:** K-means clustering on (mean_hail, p_occ, lat, lon), default 6
- **GPD:** Regional ξ from pooled L-moments, cell-specific σ from conditional mean
- **RPs:** 10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000 years
- **Physical cap:** 300 mm (~12 inches)

### Stage 10 — Spatially-Pooled CDF
- **Pool:** 150 km radius, exp(-d/75km) decay kernel
- **Method:** Weighted lognormal + GPD using regional ξ from stage 09
- **Output:** `data/analysis/cdf/rp_*yr_hail_smooth.tif`, `p_occurrence_smooth.tif`

### Stage 11 — Occurrence Probabilities
- **Thresholds:** 0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00 inches
- **Method:** (years with annual max ≥ threshold) / total years
- **Output:** `data/analysis/occurrence/p_occ_*in.tif` (8 files)

### Stage 12 — CONUS Mask + Topography
- **Mask:** regionmask US states polygon
- **Topo:** 5% hail size increase per km elevation (first-order approximation)
- **Output:** `data/analysis/conus_mask/conus_mask.tif`, `data/analysis/topography/topo_correction.tif`

### Stage 13 — Stochastic Catalog
- **Simulation:** 50,000 years, Poisson event count, DOY-weighted resampling
- **Perturbation:** σ calibrated from empirical monthly CV (not fixed 0.15)
- **Translation:** Enabled, ±3 cells (~16.5 km)
- **RP maps:** Empirical from ranked annual maxima, same 11 return periods as stage 09
- **PET:** Occurrence (OEP) + aggregate (AEP) tables
- **Output:** `data/stochastic/catalog/` (Parquet), `data/stochastic/maps/`, `data/stochastic/pet/`
- **Filename:** `rp_*yr_stochastic.tif`

### Stage 14 — Vulnerability (Placeholder)
- **Model:** MDR(h) = Φ((ln(h) − μ_v) / σ_v)
- **Classes:** 3-tab asphalt (aged), architectural shingle, Class 4 IR, metal standing seam, masonry BUR
- **Output:** `data/analysis/vulnerability/mdr_curves.csv`, `mdr_parameters.npz`

### Stage 15 — Figures
- **Historical:** `docs/figures/historical/` — analytical RP maps, event counts, seasonal distribution
- **Stochastic:** `docs/figures/stochastic/` — stochastic RP maps, OEP curves
- **Analysis:** `docs/figures/analysis/` — analytical vs stochastic comparison, vulnerability curves

## MESH75 Recalibration Constants

| Source | Equation | Reference |
|---|---|---|
| Witt (1998) | MESH = 2.54 × SHI^0.5 | Wea. Forecasting, 13, 286–303 |
| Murillo & Homeyer (2019, corrected 2021) | MESH75 = 15.096 × SHI^0.206 | JAMC, 58, 947–970; corrigendum JAMC, 60, 423 |
| Derived correction | MESH75 = 15.096 × (MESH_witt / 2.54)^0.412 | Algebraic inversion |

## Output File Format

All rasters are single-band float32 GeoTIFFs with LZW compression, EPSG:4326, 256×256 tiling, nodata = 0.0.
