# Data Dictionary

**CONUS Hail Catastrophe Model v2.0**

---

## data/historical/

### mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif
Daily maximum MESH (raw, pre-correction). Mixed sources: MYRORSS, GridRad, MRMS.
- **Type:** Single-band float32 GeoTIFF
- **Shape:** 520 rows × 1180 cols
- **Units:** mm (MESH hail diameter estimate)
- **CRS:** EPSG:4326
- **NoData:** 0.0
- **Source tracking:** `mesh_0.05deg/gridrad_days.txt` lists dates from GridRad

### mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif
Daily maximum MESH75 after bias correction and environmental filtering. Homogeneous across all sources.
- Same format as above
- **Units:** mm (MESH75-calibrated hail diameter)

### mesh_0.05deg_climo/climo_DOY.tif (366 files)
Daily climatological mean of corrected MESH75.
- Same format, DOY = day of year (001–366)

### events/event_catalog.csv
Historical event catalog from synoptic grouping.
- **Columns:** event_id, start_date, end_date, n_days, n_cells, peak_hail_mm, centroid_lat, centroid_lon

### events/event_peak_array.npy
Per-event peak hail at each grid cell. Sparse or active-cell-only storage.
- **Shape:** (n_events, 520, 1180) or sparse equivalent
- **Units:** mm

### validation/mesh_vs_spc_pairs.csv
Matched SPC report / corrected MESH75 pairs.
- **Columns:** date, lat, lon, spc_size_in, mesh75_mm, mesh75_in, grid_row, grid_col, hour

### validation/calibration_report.csv
Calibration statistics by hail size bin.

### validation/validation_summary.txt
Human-readable summary: bias, RMSE, POD/FAR/CSI, diurnal coverage.

### spc/YYYY/YYMMDD_rpts_hail.csv
Raw SPC daily hail report CSVs.

### era5/era5_monthly_isotherms_conus.nc
ERA5 1991–2020 climatological isotherm heights.
- **Variables:** h_0C_km (0°C height, km AGL), h_m20C_km (−20°C height, km AGL)
- **Dimensions:** month (12), latitude, longitude

---

## data/analysis/

### calibration/gridrad_quantile_map.npz
Quantile mapping arrays for GridRad→MYRORSS cross-calibration.
- **Arrays:** percentiles, gridrad_quantiles, myrorss_quantiles
- **Metadata:** correction_type, n_gridrad, n_myrorss

### calibration/calibration_diagnostics.csv
Per-percentile GridRad vs MYRORSS comparison.

### cdf/cdf_parameters.npz
CDF fit parameters for all cells (produced by stage 09).
- **Arrays:** p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type, region_map, region_xi, grid_shape
- **fit_type values:** 0=nodata, 1=lognorm only, 2=lognorm+GPD(regional)

### cdf/rp_XXXXXyr_hail.tif (11 files, analytical)
Analytical return period maps from CDF inversion (stage 09).
- **RPs:** 00010, 00025, 00050, 00100, 00200, 00250, 00500, 01000, 05000, 10000, 50000
- **Format:** Single-band float32 GeoTIFF, mm, 520×1180, EPSG:4326

### cdf/rp_XXXXXyr_hail_smooth.tif (11 files, spatially-pooled)
Smoothed RP maps from 150 km kernel pooling (stage 10). Same format.

### cdf/region_map.tif
Regional cluster assignments for GPD ξ pooling. Integer values 0–N.

### cdf/mrl_diagnostics/mrl_region_*.png
Mean Residual Life plots per region for GPD threshold validation.

### cdf/fitting_report.csv
Per-region fitting statistics: n_cells, ξ, threshold, pooled exceedances, fit counts.

### occurrence/p_occ_XpXXin.tif (8 files)
Annual occurrence probability rasters (stage 11).
- **Thresholds:** 0p25, 0p50, 1p00, 1p50, 2p00, 3p00, 4p00, 5p00 (inches)
- **Format:** Single-band float32, 0.0–1.0, nodata = -1.0

### topography/elevation_0.05deg.tif
DEM resampled to 0.05° (user-provided; stage 12 uses if present).

### topography/topo_correction.tif
Elevation-based hail survival correction factor (1.0–1.20). Stage 12.

### vulnerability/mdr_curves.csv
MDR lookup table: 201 hail sizes (0–200 mm) × 5 construction classes.

### vulnerability/mdr_parameters.npz
MDR curve parameters: class_names, mu_v, sigma_v arrays.

### conus_mask/conus_mask.tif
Binary CONUS land mask from regionmask. 1.0 = CONUS, 0.0 = outside.

---

## data/stochastic/

### catalog/stochastic_event_summary.parquet
One row per stochastic event across the 50,000-year simulation.
- **Columns:** sim_year, event_idx, template_id, doy, scale_factor, peak_hail_mm, n_cells

### maps/rp_XXXXXyr_stochastic.tif (11 files, empirical)
Empirical return period maps from ranked stochastic annual maxima (stage 13).
- **RPs:** 00010–50000 (same levels as analytical)
- **Format:** Single-band float32 GeoTIFF, mm, 520×1180, EPSG:4326

### pet/pet_occurrence.csv
Occurrence Exceedance Probability table.
- **Columns:** return_period_yr, peak_hail_mm, peak_hail_in, occ_n_cells

### pet/pet_aggregate.csv
Aggregate Exceedance Probability table.
- **Columns:** return_period_yr, agg_n_cells, agg_n_events

---

## docs/figures/

| Directory | Contents | Produced by |
|---|---|---|
| `figures/historical/` | Historical RP maps, climatology, event footprints | Stage 15 |
| `figures/stochastic/` | Stochastic RP maps, EP curves, PET charts | Stage 15 |
| `figures/analysis/` | Validation scatter, spatial bias, detection rates, diagnostics | Stages 06, 15 |
