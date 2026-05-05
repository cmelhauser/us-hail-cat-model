# Full Model Run Notes

## Run Context

- Date started: 2026-05-01 14:47 EDT
- Active branch: `main`
- Current commit: `e4c9331`
- Remote sync: `main`, `origin/main`, and `upstream/main` are aligned at `e4c9331`
- Historical note: the run began while work was still coordinated through the
  `v2.1` branch; that branch has since been merged and retired from active
  development.
- Python: `.venv/bin/python` 3.9.6
- Disk available at start: approximately 376 GiB

## Current Run Status

Snapshot taken 2026-05-04 02:25 EDT:

- Stage 01 completed successfully through 2011-12-31 and validated.
- Stage 01 QA was rerun with the 300.0 mm physical cap: 0 files and 0
  cells required repair; post-repair validation passed. The earlier 250.0 mm
  pass had repaired 199 files and 3,852 cells.
- TIFF count under `data/historical/mesh_0.05deg`: 5,023 Stage 01 files plus
  any in-progress Stage 02 MRMS outputs.
- Stage 01 manifest has 5,023 rows: 4,981 `ok`, 30 `missing_source`,
  11 `ok_with_read_errors`, and 1 `no_hail_pixels`.
- Disk available: approximately 373 GiB.
- Stage 02 is running in detached `screen` session `hail_stage02_mrms`.
- Stages 05–15 outputs from the earlier May-2011 smoke path are placeholders,
  not production outputs.

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

Run in cautious stage chunks. Stage 01 is complete. Stage 02 is currently
running; after it completes, continue with:

```bash
.venv/bin/python run_pipeline.py --only 03
.venv/bin/python run_pipeline.py --only 04a
.venv/bin/python run_pipeline.py --only 04b
.venv/bin/python run_pipeline.py --only 05 --skip-ml
.venv/bin/python run_pipeline.py --from 06 --skip-ml
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

When Stage 02 completes:

```bash
.venv/bin/python run_pipeline.py --only 04a
.venv/bin/python run_pipeline.py --only 04b
.venv/bin/python run_pipeline.py --from 05 --skip-ml
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 1000
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 50000
.venv/bin/python run_pipeline.py --only 14
.venv/bin/python run_pipeline.py --only 15
.venv/bin/python run_pipeline.py --validate
```

Stage 03 has already completed and only needs rerunning if the user wants a
fresh SPC pull.
