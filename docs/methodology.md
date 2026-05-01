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
- **Tail:** GPD fitted via regional L-moment pooling — shared shape parameter ξ per climatological region (K-means, default 6 regions), cell-specific scale σ
- **GPD threshold:** Validated per region using Mean Residual Life (MRL) diagnostics
- **Spatial pooling:** 150 km Gaussian kernel (decay 75 km) for smooth return period maps
- **Return periods:** 10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000 years

Two independent RP products are computed and cross-checked:
- **Analytical RPs** (stages 09–10): CDF extrapolation. Well-constrained up to ~200 yr; increasingly uncertain beyond.
- **Stochastic RPs** (stage 13): empirical from the 50,000-year simulation. Stable at all return periods. Divergence between the two flags cells where the GPD tail may be misspecified.

Output: `data/analysis/cdf/`

## 8. Occurrence Probabilities (Stage 11)

Annual probability of exceeding 8 hail size thresholds (0.25", 0.50", 1.00", 1.50", 2.00", 3.00", 4.00", 5.00") at each cell, computed directly from the annual maximum series.

Output: `data/analysis/occurrence/`

## 9. CONUS Mask + Topographic Correction (Stage 12)

CONUS land mask built from regionmask US states polygon. All RP and occurrence rasters are masked to CONUS extent. A first-order topographic correction adjusts hail size by elevation (5% per km, based on shorter melt path at higher elevation). Full treatment requires ERA5 melting layer heights.

Output: `data/analysis/conus_mask/`, `data/analysis/topography/`

## 10. Stochastic Catalog (Stage 13)

50,000-year event-resampling with:
- Poisson annual event count (λ from historical rate)
- Seasonal DOY weighting (Gaussian KDE, σ=10 days)
- Intensity perturbation: σ **calibrated from empirical inter-annual monthly CV** of peak intensity (replaces fixed σ=0.15 from v1.0)
- Spatial translation: **enabled**, ±3 cells (~16.5 km)
- Sparse event reconstruction from compressed npz format

Each stochastic event is a perturbed copy of a real historical event — preserves actual footprint geometry while varying intensity and location. Cannot generate novel footprint shapes absent from the 28-year record.

Produces empirical return period maps and Probable Exceedance Tables (occurrence OEP + aggregate AEP).

Output: `data/stochastic/catalog/` (Parquet), `data/stochastic/maps/`, `data/stochastic/pet/`

## 11. Vulnerability (Stage 14, placeholder)

Lognormal MDR curves: MDR(h) = Φ((ln(h) − μ_v) / σ_v) for 5 construction classes:
1. 3-tab asphalt shingle (aged) — most vulnerable
2. Architectural/laminated shingle
3. Class 4 impact-resistant
4. Metal standing seam
5. Masonry built-up roof

Parameters from published literature (Brown et al. 2015; IBHS impact testing). Production calibration requires proprietary claims data.

Output: `data/analysis/vulnerability/`

## 12. Figures (Stage 15)

All figures rendered to three directories:
- `docs/figures/historical/` — analytical RP maps, climatology, event catalog summaries
- `docs/figures/stochastic/` — stochastic RP maps, OEP curves
- `docs/figures/analysis/` — analytical vs stochastic RP comparison, validation diagnostics, vulnerability curves
