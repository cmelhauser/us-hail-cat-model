# AGENTS.md - CONUS Hail Catastrophe Model v2.1

For AI agents and developers. This is the single fastest way to orient
yourself to this project. Read this file before touching code, docs, pipeline
state, or git. For deeper detail, follow the links into `docs/`.

Last updated: 2026-05-03 (main branch, Stage 01 running).

## What This Project Is

A radar-based probabilistic hail hazard model for the Continental United
States. It ingests three NOAA/NCAR radar datasets, applies bias correction and
EVT fitting, and generates return-period hazard maps and a 50,000-year
stochastic event catalog.

- Version: 2.1.0 (hardening release; no methodology redesign from v2.0)
- Output: gridded hail hazard only, not financial loss
- Grid: 0.05 degree, 520 rows x 1180 columns, CONUS
- Record: MYRORSS 1998-2011, GridRad 2012-2019, MRMS 2020-present
- Pipeline: 15 stages, all written and tested
- Python: 3.10+ for project support; the active long run is still on the
  existing Python 3.9.6 `.venv` and should be upgraded only after that run

Current operating branch: `main`. The old `v2.1` branch has been merged and is
no longer the active development branch.

## Non-Negotiable Rules

Violating any of these requires explicit user sign-off and usually a version
bump.

| # | Rule |
|---|---|
| 1 | Stage 13 is sparse-safe. Never build `(n_events, 520, 1180)` dense arrays. Operate on `rows, cols, vals` only. |
| 2 | Stage 05 has a deterministic fallback. `--skip-ml` must produce complete valid output with no optional ML artifact. |
| 3 | SPC reports are validation only. Never use SPC as a hazard input. |
| 4 | `event_peaks.npz` is authoritative for Stage 13. Sparse arrays are the source of truth. |
| 5 | The 0.05 degree grid is fixed in v2.1. Any change requires a version bump and full rerun. |
| 6 | Never commit generated data files, logs, figures, model artifacts, or local bootstrap files. |
| 7 | Update tests and docs whenever methodology, output schemas, or stage behavior changes. |
| 8 | Grid constants come from `scripts/_config.py`. Do not redefine `NROWS`, `NCOLS`, `DX`, `LAT_MAX`, or `LON_MIN` in stage scripts. |
| 9 | Preserve source-coverage metadata. Stage 01 GeoTIFF zeros alone do not distinguish missing source files from no-hail days; use `manifest_stage01_myrorss.csv`. |
| 10 | Use `scripts/_logging.py` for stage loggers and `scripts/_io.py` for shared raster/geospatial helpers. |

## Known Issues / Discrepancies

No active constant-drift issues are known. `MAX_CENTROID_KM_DAY` was resolved on
2026-05-03, and the `_config.py`, `_logging.py`, and `_io.py` refactors are now
wired into all stage scripts where needed.

Stages 05-15 were previously run against a May-2011 smoke slice before Stage 01
finished. Those outputs are placeholders, not production outputs.

## Repository Layout

```text
us-hail-cat-model/
|-- AGENTS.md                   <- you are here
|-- docs/HANDOFF.md             <- session handoff doc
|-- docs/REVIEW_PRE_RUN.md      <- pre-execution audit
|-- docs/REVIEW_2026-05-01.md   <- comprehensive post-v2.1 review
|-- docs/RUN_NOTES.md           <- first-run context and commands
|-- CHANGELOG.md                <- version history
|-- CITATION.cff                <- academic citation
|-- CONTRIBUTING.md             <- dev workflow and PR standards
|-- pyproject.toml              <- project metadata, ruff/mypy/pytest config
|-- environment.yml             <- conda environment
|-- Dockerfile                  <- reproducible container
|-- run_pipeline.py             <- pipeline entry point
|-- scripts/
|   |-- _config.py              <- grid constants, paths, EVT defaults
|   |-- _logging.py             <- shared logger factory
|   |-- _io.py                  <- write_geotiff, haversine_km, latlon_to_grid
|   |-- 01_download_myrorss.py
|   |-- 02_download_mrms_mesh.py
|   |-- 03_download_spc.py
|   |-- 04a_download_era5_isotherms.py
|   |-- 04b_fill_gridrad_gap.py
|   |-- 05_apply_mesh_bias_correction.py
|   |-- 06_validate_mesh_vs_spc.py
|   |-- 07_build_hail_climo.py
|   |-- 08_build_event_catalog.py
|   |-- 09_fit_cdf_regional.py
|   |-- 10_build_smooth_cdf.py
|   |-- 11_build_occurrence_probs.py
|   |-- 12_apply_conus_mask.py
|   |-- 13_generate_stochastic_catalog.py
|   |-- 14_build_vulnerability.py
|   `-- 15_render_figures.py
|-- tests/                      <- unit and synthetic integration tests
|-- docs/                       <- full documentation
|-- data/                       <- gitignored generated data
`-- logs/                       <- gitignored stage logs
```

## Pipeline CLI

All commands run from repo root with `.venv/bin/python` for the active run, or
`python` in an activated Python 3.10+ environment / Docker container.

```bash
# Cautious staged run shape
python run_pipeline.py --only 01
python run_pipeline.py --only 02
python run_pipeline.py --only 03
python run_pipeline.py --only 04a
python run_pipeline.py --only 04b
python run_pipeline.py --only 05 --skip-ml
python run_pipeline.py --from 06 --skip-ml

# After all outputs exist
python run_pipeline.py --validate

# Stage 13 sparse-safe smoke test before full stochastic run
python scripts/13_generate_stochastic_catalog.py --n-years 1000

# Useful flags
--from N           # run stages N through 15
--only N           # run exactly stage N
--skip 14,15       # exclude stages
--dry-run          # validate config and I/O paths without executing
--validate         # re-run output validation for all stages
--skip-ml          # force deterministic fallback in Stage 05
--retrain-models   # retrain optional ML artifacts in Stage 05
```

## Stage 01 Data Provenance

Stage 01 reads MYRORSS MESH timesteps from public S3. Early archive days may be
stored as plain `.netcdf`; later days are often `.netcdf.gz`. The downloader
must accept both forms and write one daily GeoTIFF at:

```text
data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif
```

Daily GeoTIFF rasters use `0.0` for no MESH signal, so the raster by itself does
not say whether the day had no source files or had source files with no hail
pixels. The authoritative distinction is:

```text
data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv
```

Manifest statuses:

| Status | Meaning |
|---|---|
| `missing_source` | No MYRORSS NetCDF objects were available for that day. |
| `no_hail_pixels` | Source files existed, but no valid CONUS hail pixels were found. |
| `ok` | Source files existed and produced at least one active 0.05 degree cell. |
| `ok_with_read_errors` | Some source files failed to read, but the day still produced active cells. |
| `no_hail_pixels_with_read_errors` | Some source files failed and no active cells were produced. |
| `error` | All source files failed to read. |

## Pre-Run Checklist

Before any full pipeline execution:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

Then review `docs/REVIEW_PRE_RUN.md`.

## Key Constants

These come from `scripts/_config.py`.

| Constant | Value | Meaning |
|---|---:|---|
| `NROWS` | 520 | Grid rows, north to south |
| `NCOLS` | 1180 | Grid columns, west to east |
| `DX` | 0.05 degree | Cell size |
| `LAT_MAX` | 50.005 | North edge of row 0 |
| `LON_MIN` | -125.005 | West edge of col 0 |
| `DAMAGE_THRESH_MM` | 25.4 | 1-inch damage threshold |
| `MAX_HAIL_MM` | 250.0 | Hard cap on MESH75 |
| `RNG_SEED` | 42 | Stochastic RNG seed |
| `N_SIM_YEARS` | 50000 | Catalog length |
| `POOL_RADIUS_KM` | 150 | Stage 10 smoothing radius |
| `DECAY_KM` | 75 | Stage 10 exponential decay |
| `N_REGIONS_DEFAULT` | 6 | K-means EVT regions |
| `TRANSLATE_CELLS` | +/-3 | Stage 13 spatial translation |
| `MAX_CENTROID_KM_DAY` | 150.0 | Stage 08 merge check |

## Current Status

As of 2026-05-03:

| Area | Status |
|---|---|
| Active branch | `main`, synced with `origin/main` at `2228d54` |
| All 15 stage scripts | Written and syntax-checked |
| Tests | 28 pytest files; GitHub Actions green on Python 3.10/3.11/3.12 |
| Integration test | `tests/integration/test_smoke_synthetic.py` |
| Constant-drift guard | `tests/test_no_duplicated_constants.py` |
| First full pipeline run | Stage 01 in progress, started 2026-05-01 |
| Project metadata | LICENSE, CHANGELOG, CITATION, CONTRIBUTING, COC, SECURITY |
| Python project config | pyproject.toml, .pre-commit-config.yaml |
| CI/CD | `.github/workflows/tests.yml` |
| Stage 01 source manifest | Implemented |
| Regression / golden tests | Pending first production outputs |
| Bootstrap CIs on RP maps | Pending first production outputs |

## Current Run Watch

As of the 2026-05-03 16:46 EDT snapshot, Stage 01 was active at 2010-09-10
(`done=4,034`, `skipped=512`, ETA about 5 h 13 m), with 4,578 TIFFs present
and about 370 GiB free. Do not start another Stage 01 process while the active
one is running.

After Stage 01 completes, the next production sequence is:

1. Run Stage 02 (MRMS).
2. Run Stage 04a (ERA5).
3. Run Stage 04b (GridRad).
4. Re-run Stages 05-15 with `--skip-ml` against the full dataset.
5. Run Stage 13 1,000-year smoke, then the 50,000-year catalog.
6. Re-render Stage 15 figures and run `python run_pipeline.py --validate`.
7. Freeze regression/golden outputs and add bootstrap CIs to Stage 09.
8. Upgrade `.venv` to Python 3.10+ after the active run.

## Documentation Quick Reference

| Need | Read |
|---|---|
| Current run state and next commands | `docs/RUN_NOTES.md` |
| Session handoff | `docs/HANDOFF.md` |
| Scientific methodology | `docs/methodology.md` |
| Per-stage implementation | `docs/technical_documentation.md` |
| Output schemas | `docs/data_dictionary.md` |
| Reproduction guide | `docs/reproduce.md` |
| Uncertainty disclosures | `docs/uncertainty.md` |
| Extended AI operating rules | `docs/ai_instructions.md` |
| Canonical project state | `docs/project_memory.md` |
| Full review findings | `docs/REVIEW_2026-05-01.md` |
| Pre-run audit | `docs/REVIEW_PRE_RUN.md` |
| Contribution workflow | `CONTRIBUTING.md` |
| Version history | `CHANGELOG.md` |

## Stack

Python 3.10+, numpy, pandas, scipy, rasterio, xarray, regionmask, cartopy,
lmoments3, pyarrow, matplotlib, boto3, s3fs, cfgrib, eccodes, netCDF4, h5py,
scikit-learn, cdsapi, tqdm, requests, tenacity.

External accounts required: NCAR RDA (GridRad) and Copernicus CDS (ERA5).
