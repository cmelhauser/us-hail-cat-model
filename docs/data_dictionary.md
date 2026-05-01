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

### cdf/
CDF parameter files (produced by stages 09–10). *Schema TBD after script update.*

### occurrence/
Annual occurrence probability rasters (stage 11). *Schema TBD.*

### topography/
DEM and derived hail survival correction grids (stage 12). *Schema TBD.*

### vulnerability/
MDR curve parameters by construction class (stage 14). *Schema TBD.*

### conus_mask/
CONUS land mask raster (stage 12). *Schema TBD.*

---

## data/stochastic/

### catalog/
50,000-year stochastic event catalog (stage 13). Parquet format. *Schema TBD.*

### maps/
Stochastic return period and occurrence probability GeoTIFFs. *Schema TBD.*

### pet/
Probable Exceedance Tables (occurrence + aggregate). *Schema TBD.*

---

## docs/figures/

| Directory | Contents | Produced by |
|---|---|---|
| `figures/historical/` | Historical RP maps, climatology, event footprints | Stage 15 |
| `figures/stochastic/` | Stochastic RP maps, EP curves, PET charts | Stage 15 |
| `figures/analysis/` | Validation scatter, spatial bias, detection rates, diagnostics | Stages 06, 15 |
