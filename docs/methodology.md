# Methodology

**CONUS Hail Catastrophe Model v2.0**

---

## 1. Overview

The model constructs a probabilistic hail hazard layer for CONUS using radar-derived Maximum Expected Size of Hail (MESH) observations on a 0.05° (~5.5 km) grid. The methodology has five phases: data acquisition and homogenization (stages 01–06), climatology and event identification (stages 07–08), frequency-severity modeling (stages 09–12), stochastic simulation (stage 13), and vulnerability parameterization (stage 14).

## 2. Input Data

Three radar sources provide continuous CONUS MESH coverage from 1998 to present:

**MYRORSS (1998–2011):** Multi-Year Reanalysis of Remotely Sensed Storms. NEXRAD Level-II data reprocessed through the MRMS framework. Provides pre-computed Witt MESH on a 0.01° grid at ~5-min intervals. Accessed from AWS S3 (`noaa-oar-myrorss-pds`).

**GridRad (2012–2019):** Composited 3D NEXRAD reflectivity at 0.02° horizontal and 1 km vertical resolution, hourly. SHI is computed from vertical reflectivity profiles using ERA5 monthly gridded 0°C and −20°C isotherm heights, then converted to MESH75. GridRad-Severe (5-min resolution) is prioritized when available. Accessed from NCAR RDA.

**Operational MRMS (2020–present):** Real-time MRMS system. Pre-computed Witt MESH on a 0.01° grid at 2-min intervals. Accessed from AWS S3 (`noaa-mrms-pds`).

All three sources are aggregated to 0.05° via block-maximum and written as daily GeoTIFFs to `data/historical/mesh_0.05deg/`.

## 3. MESH75 Bias Correction (Stage 05)

The Witt et al. (1998) MESH algorithm intentionally overforecasts: ~75% of observed hail falls below the MESH estimate. Stage 05 applies three corrections in a single pass:

**For MYRORSS/MRMS sources:** Witt→MESH75 recalibration using the corrected Murillo & Homeyer (2021) power law: MESH75 = 15.096 × (MESH_witt / 2.54)^0.412.

**For GridRad sources:** Quantile-mapping cross-calibration built from the MYRORSS/GridRad overlap period (2005–2011). Aligns the GridRad MESH75 distribution to the MYRORSS MESH75 distribution, correcting for temporal resolution and smoothing biases.

**For all sources:** Environmental filtering — noise floor (< 5 mm → 0) and subtropical winter suppression (lat < 30°N during Nov–Feb requires ≥ 25.4 mm).

Output: `data/historical/mesh_0.05deg_corrected/`

## 4. Validation (Stage 06)

Corrected MESH75 is cross-validated against SPC ground reports (2004–present). For each report, the co-located corrected MESH75 value is extracted. Metrics include mean bias, RMSE, POD/FAR/CSI for severe (≥1.0") and significant severe (≥2.0") thresholds, spatial bias maps, and diurnal coverage analysis.

Output: `data/historical/validation/`

## 5. Climatology (Stage 07)

366 daily climatology rasters computed from the corrected MESH75 record. Each raster contains the mean daily maximum MESH75 value for that calendar day across all years.

Output: `data/historical/mesh_0.05deg_climo/`

## 6. Event Identification (Stage 08)

Discrete hail events are identified using synoptic-system grouping: consecutive hail days are merged if footprints overlap within 83 km and total duration ≤ 5 days. Each event records dates, footprint mask, peak hail intensity, centroid location, and affected cell count.

Output: `data/historical/events/`

## 7. CDF Fitting (Stages 09–10)

Per-cell frequency-severity distributions use a zero-inflated two-component model:
- **Body:** Lognormal distribution (fitted via L-moments or MLE)
- **Tail:** GPD fitted via regional L-moment pooling — shared shape parameter ξ per climatological region, cell-specific scale σ
- **GPD threshold:** Validated per region using Mean Residual Life (MRL) diagnostics
- **Spatial pooling:** 150 km Gaussian kernel for final return period maps

Output: `data/analysis/cdf/`

## 8. Stochastic Catalog (Stage 13)

50,000-year event-resampling with seasonal DOY weighting. Intensity perturbation σ calibrated from empirical inter-annual event intensity variance. Spatial translation enabled using observed event centroid variance distribution. Produces occurrence and aggregate Probable Exceedance Tables (PETs).

Output: `data/stochastic/`

## 9. Vulnerability (Stage 14, placeholder)

Lognormal MDR curves: MDR(h) = Φ((ln(h) − μ_v) / σ_v). Parameters from published literature (Brown et al. 2015; IBHS) for 3–5 construction classes. Production calibration requires proprietary claims data.

Output: `data/analysis/vulnerability/`
