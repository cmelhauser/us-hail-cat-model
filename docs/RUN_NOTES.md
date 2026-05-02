# Full Model Run Notes

## Run Context

- Date started: 2026-05-01 14:47 EDT
- Branch: `v2.1`
- Commit: `38a6879`
- Remote sync: `v2.1`, `origin/v2.1`, `main`, and `origin/main` were aligned before run planning
- Python: `.venv/bin/python` 3.9.6
- Disk available at start: approximately 376 GiB

## Preflight Commands

```bash
.venv/bin/python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests
.venv/bin/python run_pipeline.py --dry-run
```

## Recommended Full Run Shape

Run in cautious stage chunks:

```bash
.venv/bin/python run_pipeline.py --only 01
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
- A direct April 1998 canary rerun rebuilt three formerly zero days from 888 source files; full Stage 01 should be restarted with `.venv/bin/python run_pipeline.py --only 01`.
- Added `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv` so Stage 01 records source availability separately from output raster values. Status values distinguish `missing_source` from `no_hail_pixels` and `ok`.
