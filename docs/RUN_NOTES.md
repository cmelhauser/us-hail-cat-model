# Full Model Run Notes

## Run Context

- Date started: 2026-05-01 14:47 EDT
- Active branch: **`v2.2.1`** (development on `origin` only). Model **2.2.1** on `v2.2.1`; **2.2.0** on `main`.
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

Snapshot taken **2026-06-30** — **v2.2.1 production run complete**:

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 01 (MYRORSS) | ✅ Complete | 5,023 convective-day rasters through 2011-12-31. |
| Stage 02 (MRMS) | ✅ Complete | 2,060 rasters **2020-10-14 → 2026-06-04**. |
| Stage 03 (SPC) | ✅ Complete | Validation only. |
| Stage 04a (ERA5) | ✅ Complete | Isotherms on disk. |
| Stage 04c (GridRad) | ✅ Complete | **2,714** gap-era TIFFs in corrected archive; manifest 3,209 rows. |
| Stage 05 | ✅ Complete | **9,797** corrected days (0 skipped); era-pooled QM; **3.6 min** (2026-06-29). |
| Stage 06 | ✅ Complete | **173,766** SPC pairs; validation passed. |
| Stage 07 | ✅ Complete | 366 DOY climatology files. |
| Stage 08 | ✅ Complete | **8,798** events at **29 mm** (~303 yr⁻¹); validation passed. |
| Stages 09–12 | ✅ Complete | Analytical/smoothed RP maps through 50,000 yr. |
| Stage 13 | ✅ Complete | **50,000** yr; **15.17M** synthetic events; **~5.4 h** (memmap fix 2026-06-30). |
| Stages 14–15 | ✅ Complete | Placeholder vulnerability + figures; validation passed. |

**v2.2.1 parameters:** `EVENT_ACTIVE_THRESH_MM = 29.0`; era-pooled GridRad QM; see `docs/methodology.md` §2.7.

**Mesh archive totals:** **9,797** `mesh_*.tif` under `data/historical/mesh_0.05deg/` (5,023 + 2,714 + 2,060).

**Logs:** `logs/pipeline_from05_v221_rerun.run.log`, `logs/pipeline_from13_rerun.run.log`

### Stage 04c commands

**First full gap fill:**

```bash
.venv/bin/python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 4
```

**Backfill days without an output GeoTIFF** (skips existing rasters; includes new **d841001** warm-season hourly fallback for Apr–Aug 2018–2020):

```bash
.venv/bin/python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 4 --missing-only
```

- Prefer **`--workers 2`** on disks under ~250 GiB free (`run_pipeline.py --only 04c` defaults to `--workers 4`).
- Monitor: `tail -f logs/04c_fill_gridrad_gap.run.log`
- **Severe-first downloads:** with `--with-04b-download`, **04c** downloads GridRad-Severe when the catalog lists it; hourly GridRad (**d841000** V3.1, then **d841001** V4.2 warm-season Apr–Aug 2018+) is used only when severe is missing or does not cover the full convective window (see `docs/technical_documentation.md` §8.3).
- **04c** skips existing `mesh_*.tif` unless the day is missing from disk (`--missing-only` filters to those days).
- **Manifest:** `data/historical/mesh_0.05deg/manifest_stage04c_gridrad.csv` is upserted per day (rebuild: `--manifest-only`).
- **Re-process rule:** delete any gap TIFF written with the old `Nradecho` reader before trusting distributions.

### Stage 02 completion log (2026-06-08)

From `logs/02_download_mrms_mesh.log`:

- Days processed this run: 1,199 (861 skipped as existing)
- Days with no MESH data: 0
- Total S3 GRIB2 files read: 862,997
- Output validation: passed

---

### Historical snapshots (superseded)

**2026-06-27:** Stage 04c primary ingest complete. Production runs **2026-06-08 → 2026-06-27** wrote **2,501** gap-era TIFFs. Manifest complete for all **3,209** convective days. **`--missing-only`** backfill launched for remaining days without TIFFs.

**2026-06-08:** Stage 04c production run started (`--with-04b-download --workers 2`). Stage 02 (MRMS) finished; mesh archive was 7,083 TIFFs (MYRORSS + MRMS only).

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

Stages 01–04c and the full **v2.2.1** hazard pipeline (**05–15**) are complete. Optional:

```bash
.venv/bin/python run_pipeline.py --validate
.venv/bin/python scripts/diagnostics/hail_day_climatology.py
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

1. **Confirm Stage 04c backfill is done** (or accept manifest `missing_source` days as NCAR gaps).
2. **Re-run Stages 05–15** with `--skip-ml`.
3. **Stage 13 smoke** then full 50,000-year catalog.
4. **Validate** and regenerate mesh-era diagnostic summaries.

```bash
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
