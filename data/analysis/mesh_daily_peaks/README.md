# Mesh daily peak summaries

Diagnostic summaries of daily maximum hail across the unified `mesh_0.05deg` archive
(MYRORSS, GridRad gap-fill, MRMS). **v2.1 calendar-UTC** CSV/PNG outputs were removed
after the v2.2 convective-day (12 UTC → 12 UTC) migration; regenerate once the new
`mesh_0.05deg/` tree exists:

```bash
.venv/bin/python scripts/diagnostics/summarize_mesh_daily_peaks.py
```

## Files (after regeneration)

| File | Description |
|------|-------------|
| `mesh_daily_peaks.csv` | One row per daily GeoTIFF: date, source era, peak mm/in, active cells |
| `mesh_daily_peak_percentiles.csv` | Percentiles by source (all months and May-only subsets) |
| `mesh_daily_peak_ecdf.png` | ECDF of daily peak hail by radar era |

Peak values prefer GDAL tag `MAX_MESH75_MM` when present (Stage 04c); otherwise raster max.
