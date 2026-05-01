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
*To be documented as scripts are updated for v2.0.*

## MESH75 Recalibration Constants

| Source | Equation | Reference |
|---|---|---|
| Witt (1998) | MESH = 2.54 × SHI^0.5 | Wea. Forecasting, 13, 286–303 |
| Murillo & Homeyer (2019, corrected 2021) | MESH75 = 15.096 × SHI^0.206 | JAMC, 58, 947–970; corrigendum JAMC, 60, 423 |
| Derived correction | MESH75 = 15.096 × (MESH_witt / 2.54)^0.412 | Algebraic inversion |

## Output File Format

All rasters are single-band float32 GeoTIFFs with LZW compression, EPSG:4326, 256×256 tiling, nodata = 0.0.
