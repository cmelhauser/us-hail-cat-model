# AGENTS.md - CONUS Hail Catastrophe Model v2.1

For AI agents and developers. This is the single fastest way to orient
yourself to this project. Read this file before touching code, docs, pipeline
state, or git. For deeper detail, follow the links into `docs/`.

Last updated: 2026-05-20 (`v2.1.2` / `main` at `c0b35b8`; Stage 04c gap-fill paused after disk-full incident — restart with `--workers 2`).

## What This Project Is

A radar-based probabilistic hail hazard model for the Continental United
States. It ingests three NOAA/NCAR radar datasets, applies bias correction and
EVT fitting, and generates return-period hazard maps and a 50,000-year
stochastic event catalog.

- Version: 2.1.0 (hardening release; no methodology redesign from v2.0)
- Output: gridded hail hazard only, not financial loss
- Grid: 0.05 degree, 520 rows x 1180 columns, CONUS
- Record: MYRORSS 1998-2011, GridRad 2012-2020-10-13, MRMS 2020-10-14-present
- Pipeline: 15 stages, all written and tested
- Python: 3.10+ for project support; the active long run is still on the
  existing Python 3.9.6 `.venv` and should be upgraded only after that run

Current operating branch: `v2.1.2` (aligned with `main` at `c0b35b8`). The old
`v2.1` branch has been merged and is no longer the active development branch.

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
| 6 | Never commit generated data files, logs, figures, model artifacts, or local bootstrap files. **Exception:** `data/analysis/mesh_daily_peaks/` diagnostic summaries (CSV/PNG + README). |
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
|   |-- 04b_download_gridrad.py
|   |-- 04c_fill_gridrad_gap.py
|   |-- 05_apply_mesh_bias_correction.py
|   |-- 06_validate_mesh_vs_spc.py
|   |-- 07_build_hail_climo.py
|   |-- 08_build_event_catalog.py
|   |-- 09_fit_cdf_regional.py
|   |-- 10_build_smooth_cdf.py
|   |-- 11_build_occurrence_probs.py
|   |-- 11b_prepare_topography.py
|   |-- 12_apply_conus_mask.py
|   |-- 13_generate_stochastic_catalog.py
|   |-- 14_build_vulnerability.py
|   |-- 15_render_figures.py
|   `-- diagnostics/
|       `-- summarize_mesh_daily_peaks.py  <- mesh archive peak CSV/ECDF (optional)
|-- tests/                      <- unit and synthetic integration tests
|-- docs/                       <- full documentation
|-- data/                       <- gitignored generated data (except data/analysis/mesh_daily_peaks/)
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
python run_pipeline.py --only 04c   # auto: --with-04b-download --workers 4; 04b skipped on full runs
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

# Stage 02 is often run directly (MRMS); optional throughput flag:
# python scripts/02_download_mrms_mesh.py --workers 8
```

**GridRad via `run_pipeline.py`:** full runs (and resumes starting before **04b**)
auto-**skip** standalone **04b** and run **04c** with **`--with-04b-download --workers 4`**
(streaming download + four parallel days; per-day staging deleted by default). Use
**`--only 04b`** or **`--from 04b`** for the legacy NCAR-only downloader.

## Stages 04b / 04c (GridRad)

- **04b** (`scripts/04b_download_gridrad.py`): default is **one calendar day at a time**
  (plan + download per day). **`--plan-all-days-first`** restores the legacy global
  plan-then-download flow. **`--workers`** defaults to **1** (parallel HTTP GETs *within*
  the current day only; respect NCAR throttling guidance).
- **04c** (`scripts/04c_fill_gridrad_gap.py`): default **`--workers 1`** (sequential days).
  After each day finishes, **`delete_gridrad_inputs_for_day`** removes that day’s trees
  under `data/historical/gridrad/` and `data/historical/gridrad_severe/` unless
  **`--keep-gridrad-inputs`**. **`--with-04b-download`** chains **04b**’s
  **`download_for_day`** before **`process_day`**; with **`--workers > 1`**, each worker
  process uses its own HTTP session (04b is loaded once per worker via a pool
  initializer; mind **`workers × --04b-download-workers`** vs NCAR throttling).
- **04c reflectivity:** use sparse **`Reflectivity(Index)` + `index`** (not **`Nradecho`**, which is not dBZ). Gap-fill GeoTIFFs include GDAL tags `MAX_MESH75_MM`, `ACTIVE_CELLS`, etc., and per-day log lines with peak hail.
- **04c disk / workers:** `run_pipeline.py` passes **`--workers 4`** by default. With **`--with-04b-download`**, up to four concurrent day trees under `gridrad_severe/` can use ~8–12 GB each. On constrained disks, run **`scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2`** (or `1`) directly instead of `run_pipeline.py --only 04c`.

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

Stage 01 also performs a physical QA pass after download/processing. Values
that are non-finite, negative, or greater than `MAX_HAIL_MM = 300.0` are reset
to `0.0`, and the manifest active-cell and daily-maximum fields are refreshed.
Run this repair pass independently with:

```bash
python scripts/01_download_myrorss.py --qa-only
```

The same `MAX_HAIL_MM` QA cap is enforced by Stage 02, Stage 04b, and Stage 05
before their outputs are accepted. Do not introduce a new hail-size-producing
stage without importing the shared QA helper from `scripts/_io.py`.

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
ruff check .
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
| `MAX_HAIL_MM` | 300.0 | Physical QA cap on hail diameter values |
| `RNG_SEED` | 42 | Stochastic RNG seed |
| `N_SIM_YEARS` | 50000 | Catalog length |
| `POOL_RADIUS_KM` | 150 | Stage 10 smoothing radius |
| `DECAY_KM` | 75 | Stage 10 exponential decay |
| `N_REGIONS_DEFAULT` | 6 | K-means EVT regions |
| `TRANSLATE_CELLS` | +/-3 | Stage 13 spatial translation |
| `MAX_CENTROID_KM_DAY` | 150.0 | Stage 08 merge check |

## Current Status

As of 2026-05-20:

| Area | Status |
|---|---|
| Active branch | `v2.1.2` / `main` at `c0b35b8` |
| All 15 stage scripts | Written and syntax-checked |
| Tests | 28 pytest files; GitHub Actions green on Python 3.10/3.11/3.12 |
| Integration test | `tests/integration/test_smoke_synthetic.py` |
| Constant-drift guard | `tests/test_no_duplicated_constants.py` |
| First full pipeline run | Stage 01 complete; Stage 02 and **04c** in progress (04c paused 2026-05-20 for disk cleanup) |
| Mesh peak diagnostic | `scripts/diagnostics/summarize_mesh_daily_peaks.py` + tracked `data/analysis/mesh_daily_peaks/` |
| Project metadata | LICENSE, CHANGELOG, CITATION, CONTRIBUTING, COC, SECURITY |
| Python project config | pyproject.toml, .pre-commit-config.yaml |
| CI/CD | `.github/workflows/tests.yml` |
| Stage 01 source manifest | Implemented |
| Regression / golden tests | Pending first production outputs |
| Bootstrap CIs on RP maps | Pending first production outputs |

## Current Run Watch

Stage 01 is complete through 2011-12-31 (5,023 MYRORSS daily rasters; manifest QA at 300.0 mm cap). Stage **04c** gap-fill uses the sparse **`Reflectivity`** reader; bad pre-fix gap TIFFs must be deleted before re-run. **2026-05-20:** a disk-full stop removed stale `gridrad/` / `gridrad_severe/` staging under 2013 (~35 GB); restart **04c** with **`--workers 2`** (see `docs/RUN_NOTES.md`). Monitor `logs/04c_fill_gridrad_gap.run.log`. Optional era QA: `scripts/diagnostics/summarize_mesh_daily_peaks.py`.

The remaining production sequence is:

1. Let Stage 02 (MRMS) and Stage 04c (GridRad gap-fill) complete; use direct **04c** with `--workers 2` if disk is tight.
2. Run Stage 04a (ERA5) if CDS credentials are configured.
3. Re-run Stages 05-15 with `--skip-ml` against the full dataset.
4. Run Stage 13 1,000-year smoke, then the 50,000-year catalog.
5. Re-render Stage 15 figures and run `python run_pipeline.py --validate`.
6. Freeze regression/golden outputs and add bootstrap CIs to Stage 09.
7. Upgrade `.venv` to Python 3.10+ after the active run.

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
Stage 04a requires the Copernicus account to have accepted the ERA5 monthly
pressure-level and single-level dataset licence terms, plus `~/.cdsapirc` with:

```yaml
url: https://cds.climate.copernicus.eu/api
key: YOUR_PERSONAL_ACCESS_TOKEN
```

The file must stay outside the repository, should be `chmod 600`, and must
never be committed or printed with the token visible.

CDS licence acceptance is per account and separate from the token. A valid
`~/.cdsapirc` can still fail Stage 04a with `403 Client Error: Forbidden` and
`required licences not accepted`. In that case, accept both ERA5 monthly dataset
licences while signed in to the token's CDS account:

- https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels-monthly-means?tab=download#manage-licences
- https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means?tab=download#manage-licences

Stage 04a caches bounded ERA5 pressure-level chunks under
`data/historical/era5/pressure_chunks/`. If a CDS yearly request exceeds cost
limits, the script falls back to monthly chunks and then combines the cached
pieces into the raw NetCDF used for isotherm interpolation.

Stage 11b prepares the topography input for Stage 12. It downloads NOAA/NCEI
ETOPO 2022 60 arc-second surface elevation, caches the source under
`data/analysis/topography/source/`, and writes
`data/analysis/topography/elevation_0.05deg.tif` on the canonical model grid.
