# Full Model Run Notes

## Run Context

- Date started: 2026-05-01 14:47 EDT
- Active branch: **`v2.2.1`** (development on `origin` only). Model **2.2.0** on `main`.
- Prior production mesh archived under `data/historical/mesh_0.05deg_archive_calendar_utc_00z/` (gitignored)
- Historical note: the run began while work was still coordinated through the
  `v2.1` branch; that branch has since been merged and retired from active
  development.
- Python: `.venv/bin/python` 3.9.6
- Disk available at start: approximately 376 GiB

## v2.2 convective-day migration (2026-05-28)

- **Temporal definition:** daily `mesh_YYYYMMDD.tif` = max over **[label 12:00 UTC, label+1 12:00 UTC)**.
- **Prior v2.1 rasters** archived under `data/historical/mesh_0.05deg_archive_calendar_utc_00z/`; `mesh_0.05deg/` must be rebuilt.
- **GridRad staging:** `gridrad(_severe)/by_convective_day/YYYYMMDD/` (not `YYYY/YYYYMMDD/`).
- **Mesh peak diagnostic:** v2.1 CSV/PNG removed; regenerate after re-ingest with `scripts/diagnostics/summarize_mesh_daily_peaks.py`.

## Current Run Status

Snapshot taken **2026-06-08**:

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 01 (MYRORSS) | ✅ Complete | 5,023 convective-day rasters through 2011-12-31. Manifest: 4,989 `ok`, 20 `missing_source`, 11 `ok_with_read_errors`, 3 `no_hail_pixels`. QA cap 300.0 mm. |
| Stage 02 (MRMS) | ✅ Complete | Finished **2026-06-08 06:19 EDT** (86.4 h). 2,060 rasters **2020-10-14 → 2026-06-04**. Manifest: 2,059 `ok`, 1 `ok_with_read_errors`. Output validation passed. Peak MESH 299.9 mm. |
| Stage 03 (SPC) | ✅ Complete | SPC CSV files downloaded. Rerun only for a fresh pull. |
| Stage 04a (ERA5) | ✅ Complete | `era5_monthly_isotherms_conus.nc` and `era5_surface_geopotential_conus.nc` on disk; validation passed 2026-05-13. |
| Stage 04c (GridRad) | ⏸ Not started (v2.2) | **0** gap-era (2012–2020-10-13) convective-day TIFFs on disk. Prior calendar-UTC gap outputs were cleared for v2.2 re-ingest. Last log activity **2026-05-29** at **2016-06-20** (pre-migration run). **Restart required.** |
| Stages 05–15 | ⚠️ Placeholder | Ran against 31 May-2011 smoke files only. Not production. |

**Mesh archive totals:** 7,083 `mesh_*.tif` under `data/historical/mesh_0.05deg/` (5,023 MYRORSS + 2,060 MRMS). Gap era pending Stage 04c.

**Disk available:** ~154 GiB (2026-06-08).

**No active processes:** Stage 02 `screen` session `hail_stage02_mrms` is gone; stale PID in `logs/stage02_mrms.pid`.

### Stage 04c restart (recommended)

```bash
.venv/bin/python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2
```

- Prefer **`--workers 2`** on constrained disks (`run_pipeline.py --only 04c` defaults to `--workers 4`).
- Monitor: `tail -f logs/04c_fill_gridrad_gap.run.log`
- **04c** skips existing `mesh_*.tif`; no gap-era files exist yet, so the full 2012–2020-10-13 range will be processed.
- **Re-process rule:** delete any gap TIFF written with the old `Nradecho` reader before trusting distributions.

### Stage 02 completion log (2026-06-08)

From `logs/02_download_mrms_mesh.log`:

- Days processed this run: 1,199 (861 skipped as existing)
- Days with no MESH data: 0
- Total S3 GRIB2 files read: 862,997
- Output validation: passed

---

### Historical snapshots (superseded)

**2026-05-20:** Stage 04c reflectivity reader fixed (`Nradecho` → sparse **`Reflectivity`** + lon normalization). Run stopped for disk full (`[Errno 28]`); stale `gridrad/` / `gridrad_severe/` trees under 2013 removed (~35 GB).

**2026-05-04:** Stage 01 complete; Stage 02 running in `screen` session `hail_stage02_mrms`; 5,023 Stage 01 TIFFs on disk.

## Preflight Commands

```bash
.venv/bin/python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests
.venv/bin/python run_pipeline.py --dry-run
```

Stage 04a also requires Copernicus CDS access before it can request ERA5.
Confirm the account has accepted the ERA5 monthly pressure-level and
single-level dataset licence terms, then confirm `~/.cdsapirc` exists with
`url: https://cds.climate.copernicus.eu/api` and a personal access token from
the CDS profile page. Keep the file outside the repository and do not print or
commit the token.

The required CDS licence pages are:

- https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels-monthly-means?tab=download#manage-licences
- https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means?tab=download#manage-licences

If Stage 04a fails with `403 Client Error: Forbidden` and `required licences not
accepted`, the token is being read but the account has not accepted one of these
dataset licences.

Stage 04a downloads ERA5 pressure-level fields in yearly chunks and falls back
to monthly chunks if CDS rejects a yearly request as too large. Chunk files are
cached under `data/historical/era5/pressure_chunks/` and can be reused after an
interrupted run.

## Recommended Full Run Shape

Stages 01, 02, 03, and 04a are complete. **Restart Stage 04c**, then continue:

```bash
.venv/bin/python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2
.venv/bin/python run_pipeline.py --only 05 --skip-ml
.venv/bin/python run_pipeline.py --from 06 --skip-ml
```

**`run_pipeline.py` GridRad:** stage **04c** is run with **`--with-04b-download --workers 4`**
(per-day staging removed after each day by default). On disks under ~250 GiB free, prefer the
direct script with **`--workers 2`** (see snapshot above). Standalone **04b** is **auto-skipped**
when **04c** is in the plan. Use **`--only 04b`** / **`--from 04b`** for the legacy downloader.
See **`docs/reproduce.md` §4–§5**.

Stage 11b is included in `--from 06`; it downloads NOAA/NCEI ETOPO 2022
surface elevation and writes `data/analysis/topography/elevation_0.05deg.tif`
before Stage 12 applies topographic correction. It can also be run directly:

```bash
.venv/bin/python run_pipeline.py --only 11b
```

After outputs exist:

```bash
.venv/bin/python run_pipeline.py --validate
```

Stage 13 sparse-safe smoke before any full stochastic rerun:

```bash
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

## Known Fallbacks / Watch Items

- Stage 05 should use `--skip-ml` first, forcing deterministic calibration/filter fallbacks.
- Stage 11b prepares `data/analysis/topography/elevation_0.05deg.tif` from NOAA/NCEI ETOPO 2022.
- Stage 12 uses uniform topographic correction if `data/analysis/topography/elevation_0.05deg.tif` is absent.
- Generated rasters, logs, and rendered figures are intentionally ignored by git.
- Stage 13 stochastic maps are CONUS-masked during output and Stage 15 also masks at render time.

## Stage 01 Restart Note

- Initial Stage 01 run was stopped on 2026-05-01 after discovering many early MYRORSS objects are stored as plain `.netcdf`, not `.netcdf.gz`.
- Patched `scripts/01_download_myrorss.py` to ingest both formats and removed 597 generated zero rasters from 1998-04-24 through 1999-12-31 that had plain NetCDF source files.
- A direct April 1998 canary rerun rebuilt three formerly zero days from 888 source files.
- Added `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv` so Stage 01 records source availability separately from output raster values. Status values distinguish `missing_source` from `no_hail_pixels` and `ok`.
- Stage 01 completed on 2026-05-03. A 300.0 mm QA repair pass was added and run
  on 2026-05-04. Do not rerun Stage 01 downloads unless the user explicitly asks
  for a clean rebuild; use `--qa-only` for repair/validation without downloading.

## Next Actions

1. **Restart Stage 04c** (full 2012–2020-10-13 convective-day gap fill).
2. **Re-run Stages 05–15** with `--skip-ml` after 04c completes.
3. **Stage 13 smoke** then full 50,000-year catalog.
4. **Validate** and regenerate mesh-era diagnostic summaries.

```bash
.venv/bin/python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2
.venv/bin/python run_pipeline.py --from 05 --skip-ml
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 1000
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 50000
.venv/bin/python run_pipeline.py --only 14
.venv/bin/python run_pipeline.py --only 15
.venv/bin/python run_pipeline.py --validate
.venv/bin/python scripts/diagnostics/summarize_mesh_daily_peaks.py
```

Stage 03 has already completed and only needs rerunning if the user wants a
fresh SPC pull.
