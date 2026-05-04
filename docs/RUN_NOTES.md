# Full Model Run Notes

## Run Context

- Date started: 2026-05-01 14:47 EDT
- Active branch: `main`
- Current commit: `2228d54`
- Remote sync: `main` and `origin/main` are aligned at `2228d54`
- Historical note: the run began while work was still coordinated through the
  `v2.1` branch; that branch has since been merged and retired from active
  development.
- Python: `.venv/bin/python` 3.9.6
- Disk available at start: approximately 376 GiB

## Current Run Status

Snapshot taken 2026-05-03 16:46 EDT:

- Stage 01 is still running under `.venv/bin/python run_pipeline.py --only 01`.
- Latest Stage 01 log progress: 2010-09-10, `done=4,034`, `skipped=512`,
  ETA approximately 5 h 13 m.
- TIFF count under `data/historical/mesh_0.05deg`: 4,578.
- Stage 01 manifest extends into 2010-09-11 and continues to record `ok`,
  `missing_source`, `no_hail_pixels`, and read-error statuses.
- Disk available: approximately 370 GiB.
- Stages 05–15 outputs from the earlier May-2011 smoke path are placeholders,
  not production outputs.

## Preflight Commands

```bash
.venv/bin/python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests
.venv/bin/python run_pipeline.py --dry-run
```

## Recommended Full Run Shape

Run in cautious stage chunks. Because Stage 01 is already active, do not start
another Stage 01 process. When Stage 01 completes, continue from Stage 02:

```bash
.venv/bin/python run_pipeline.py --only 02
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
- Stage 01 has already been restarted and is running. Do not rerun it unless the
  active process fails or the user explicitly asks for a clean rebuild.

## Next Actions

When Stage 01 completes:

```bash
.venv/bin/python run_pipeline.py --only 02
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
