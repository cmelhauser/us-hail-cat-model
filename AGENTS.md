# AGENTS.md - CONUS Hail Catastrophe Model v2.3.0

For AI agents and developers. This is the single fastest way to orient
yourself to this project. Read this file before touching code, docs, pipeline
state, or git. For deeper detail, follow the links into `docs/`.

**AI collaborator identity:** All AI collaboration on this project is credited
under the pseudonym **theonlymuffinbot** (not a separate GitHub repository).
Scientific direction and accountability remain with Christopher Melhauser.
The sole code remote is `origin` → `cmelhauser/us-hail-cat-model`.

Last updated: 2026-08-05 (documentation synchronized; run status unverified
since 2026-07-09; canonical state in `docs/RUN_NOTES.md`).

## What This Project Is

A radar-based probabilistic hail hazard model for the Continental United
States. It ingests three NOAA/NCAR radar datasets, applies bias correction and
EVT fitting, and generates return-period hazard maps and a 50,000-year
stochastic event catalog.

- Version: **2.3.0** (Tier 0 radar QC + optional geometry-aware research classifier)
- Output: gridded hail hazard only, not financial loss
- Grid: 0.05 degree, 520 rows x 1180 columns, CONUS
- Record: MYRORSS 1998-2011, GridRad 2012-2020-10-13, MRMS 2020-10-14-present
- Pipeline: 14 stages (01–13 hazard + 14 figures), all written and tested
- Python: 3.10+ for project support; the historical long-run environment used
  Python 3.9.6. Verify that no run is active before replacing that `.venv`.

Current operating branch: **`v2.3.0`** (push/PR to `origin` only; CI on `main` and
`v*`). Model release **2.3.0**. `origin/main` already carries the 2.3.0 codebase tip
from the 2026-07-30 fast-forward; this branch may be a few commits ahead (docs/CI).
Retired version branches (`v2.2.2`, `v2.2.3`, `v2.1`) are not active development.

## Non-Negotiable Rules

Violating any of these requires explicit user sign-off and usually a version
bump.

| # | Rule |
|---|---|
| 1 | Stage 13 is sparse-safe. Never build `(n_events, 520, 1180)` dense arrays. Operate on `rows, cols, vals` only. |
| 2 | Stage 05 has a deterministic fallback. `--skip-ml` must produce complete valid output with no optional ML artifact. |
| 3 | SPC reports are validation only. Never use SPC as a hazard input. |
| 4 | `event_peaks.npz` is authoritative for Stage 13. Sparse arrays are the source of truth. |
| 5 | The 0.05 degree grid is fixed. Convective-day definition (12 UTC start) is versioned in v2.2; any change requires a version bump and full rerun. |
| 11 | Daily MESH labels use **convective days** (12 UTC → 12 UTC). Stages 01, 02, 04b, 04c filter timesteps with `scripts/_io.py` helpers; do not revert to calendar UTC midnight without a version bump. |
| 6 | Never commit generated data files, logs, figures, model artifacts, or local bootstrap files (including diagnostic summaries under `data/analysis/`). |
| 7 | Update tests and docs whenever methodology, output schemas, or stage behavior changes. |
| 8 | Grid constants come from `scripts/_config.py`. Do not redefine `NROWS`, `NCOLS`, `DX`, `LAT_MAX`, or `LON_MIN` in stage scripts. |
| 9 | Preserve source-coverage metadata. Stage 01 GeoTIFF zeros alone do not distinguish missing source files from no-hail days; use `manifest_stage01_myrorss.csv`. |
| 10 | Use `scripts/_logging.py` for stage loggers, `scripts/_io.py` for shared raster/geospatial helpers, and `scripts/_mapping.py` for CONUS map PNGs (Lambert Conformal + admin boundaries). |
| 12 | **Git:** sole remote is **`origin`** (`cmelhauser/us-hail-cat-model`). Commit and push only there. PRs: `gh pr create --repo cmelhauser/us-hail-cat-model --base main`. CI runs on `main` and `v*`. See `docs/GIT_REMOTES.md`. |
| 13 | **Quality gate before every commit:** run `./scripts/quality_gate.sh` (100% `scripts`+`run_pipeline` coverage, 100% AWS coverage, ruff, dry-run, docs/policy sync). Do not commit with stale docs/`AGENTS.md`/`docs/ai_instructions.md`, and do not use `--no-verify` unless the user explicitly orders it. CI on every push/PR to `main`/`v*` must stay green. |

## Known Issues / Discrepancies

No active constant-drift issues are known. `MAX_CENTROID_KM_DAY` was resolved on
2026-05-03, and the `_config.py`, `_logging.py`, and `_io.py` refactors are now
wired into all stage scripts where needed. Map PNGs (Stage 14 and diagnostics) use
`scripts/_mapping.py` for Lambert Conformal projection and admin boundaries.

Stages 05-14 were previously run against a May-2011 smoke slice before Stage 01
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
|-- Dockerfile                  <- reproducible container (also the ECR image for aws/)
|-- run_pipeline.py             <- local pipeline entry point
|-- aws/                        <- optional ECS Fargate adapter (does not modify stages)
|   |-- config/pipeline.yaml    <- CDK + orchestrator parameters
|   |-- cdk/                    <- deployable Python CDK stack
|   |-- hail_aws/               <- config loader, ECS client, workflow
|   |-- run_pipeline_aws.py     <- local boto3 orchestrator CLI
|   |-- docker-compose.localstack.yml  <- LocalStack Community 4.14.0 for tests
|   `-- tests/                  <- aws unit/integration tests (100% hail_aws gate)
|-- scripts/
|   |-- _config.py              <- grid constants, paths, EVT defaults, MODEL_VERSION
|   |-- _logging.py             <- shared logger factory
|   |-- _io.py                  <- write_geotiff, haversine_km, latlon_to_grid
|   |-- _mapping.py             <- Lambert Conformal maps, admin_0/admin_1 boundaries
|   |-- _radar_geometry.py      <- NEXRAD sites, range debias, multi-pass artifact filter
|   |-- _gridrad_qc.py          <- GridRad native echo-frequency + clutter QC (04c)
|   |-- _artifact_features.py   <- geometry features for optional artifact classifier
|   |-- _pipeline_cleanup.py    <- delete Stage N+ outputs (used by rerun / --clean-from)
|   |-- setup_git_remotes.sh    <- origin-only remote setup
|   |-- train_artifact_classifier.py <- optional Stage 05 classifier trainer
|   |-- rerun_stage05.py        <- wait, clean 05+, blocking Stage 05 rebuild
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
|   |-- 14_render_figures.py    <- Stage 14 figures (formerly 15)
|   |-- archive/                <- legacy v1 reference scripts (not CI-linted)
|   `-- diagnostics/
|       |-- _diagnostic_io.py            <- shared warn-and-skip data availability helpers
|       |-- summarize_mesh_daily_peaks.py  <- mesh archive peak CSV/ECDF (optional)
|       |-- hail_day_climatology.py        <- per-cell hail-day threshold sensitivity (optional)
|       |-- radar_artifact_diagnostic.py   <- speckle/range debias QA (optional)
|       |-- literature_validation_suite.py <- literature benchmarks across stages (optional)
|       |-- render_pnas_article_figures.py <- manuscript figures
|       |-- render_pnas_publication_md.py  <- publication markdown build
|       |-- render_pnas_review_docx.py     <- Word review draft
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
python run_pipeline.py --only 04c   # auto: --with-04b-download --workers 4; 04b skipped on full runs
python run_pipeline.py --only 05 --skip-ml
python run_pipeline.py --from 06 --skip-ml

# After all outputs exist
python run_pipeline.py --validate

# Stage 13 sparse-safe smoke test before full stochastic run
python scripts/13_generate_stochastic_catalog.py --n-years 1000

# Useful flags
--from N           # run stages N through 14
--only N           # run exactly stage N
--skip 14          # exclude figure rendering
--dry-run          # validate config and I/O paths without executing
--validate         # re-run output validation for all stages
--skip-ml          # force deterministic fallback in Stage 05
--skip-calibration # Stage 05: skip ML calibration (with --skip-ml)
--clean-from N     # delete outputs from stage N onward before run (e.g. 05)
--retrain-models   # train diagnostic artifact classifier only (never applied to hazard rasters)

# Stage 05 deterministic baseline — blocking; do not background from agents
python scripts/rerun_stage05.py
python run_pipeline.py --only 05 --clean-from 05 --skip-ml --skip-calibration

# Stage 02 is often run directly (MRMS); optional throughput flag:
# python scripts/02_download_mrms_mesh.py --workers 8
```

## AWS Fargate adapter (optional)

Parallel cloud runs without changing stage scripts. Shared EFS holds `data/` /
`logs/` / figures; the root `Dockerfile` (entrypoint writes `~/.cdsapirc` from
Secrets Manager–injected `CDSAPI_*`) is the container image.

```bash
pip install -e ".[aws]"
python aws/run_pipeline_aws.py --dry-run
# Secrets → pipeline.yaml ARNs → cdk deploy → docker build/push ECR → then:
python aws/run_pipeline_aws.py --mode full          # 01|02 + GridRad day fan-out, then finalize
python aws/run_pipeline_aws.py --mode downloads-only
python aws/run_pipeline_aws.py --mode finalize
# Optional: bound GridRad days or disable fan-out
python aws/run_pipeline_aws.py --dry-run \
  --gridrad-from-date 2015-05-20 --gridrad-until-date 2015-05-21
```

Parameters: `aws/config/pipeline.yaml` (includes `workflow.gridrad_fanout`).
**Complete operator guide:** `aws/README.md` (secrets JSON shape, ECR push, stack
outputs, smoke ladder, cost/teardown, troubleshooting). Also `docs/reproduce.md` §14.

Tests (CI job **`aws`** enforces **100%** on `hail_aws` + CLI; CDK synth needs Node):

```bash
PYTHONPATH=aws pytest -q aws/tests -m 'not localstack' \
  --ignore=aws/tests/test_cdk_stack.py \
  --cov=hail_aws --cov=run_pipeline_aws --cov-fail-under=100
```

**Coverage policy:** AWS adapter = 100% gate. Pipeline `scripts/` + `run_pipeline.py`
also gate at **100%** statement coverage in `pyproject.toml` (`fail_under = 100`;
`scripts/archive/*` and `aws/cdk/*` omitted). Stages remain I/O-heavy; unit tests
use mocks for network/filesystem paths. CI (`.github/workflows/tests.yml`) and
the local pre-commit hook both enforce the same floors via
`./scripts/quality_gate.sh`.

## Quality gate (required before every commit)

```bash
./scripts/quality_gate.sh
# equivalent checks (also run in CI on main / v*):
#   python scripts/check_policy_consistency.py
#   python -m py_compile run_pipeline.py scripts/*.py
#   ruff check .
#   OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
#     pytest -q tests -p pytest_cov --cov=scripts --cov=run_pipeline --cov-fail-under=100
#   PYTHONPATH=aws ... --cov-fail-under=100
#   python run_pipeline.py --dry-run
```

Update `AGENTS.md`, `docs/ai_instructions.md`, and any touched operator/methodology
docs in the same commit as code/schema/CLI changes. Cursor loads
`.cursor/rules/commit-quality-gate.mdc` and blocks `git commit` until the gate
stamp is current.

LocalStack Community image pin: `localstack/localstack:4.14.0` (ECS is **Pro**;
Community does not validate Fargate spend). Laptop stub E2E:
`aws/tests/test_laptop_orchestrator_e2e.py`. Design:
`docs/superpowers/specs/2026-07-17-aws-fargate-adapter-design.md`.

There is no in-repo Cursor skill pack for this project; agent operating rules live
in this file and `docs/ai_instructions.md`.

**GridRad via `run_pipeline.py`:** full runs (and resumes starting before **04b**)
auto-**skip** standalone **04b** and run **04c** with **`--with-04b-download --workers 4`**
(streaming download + four parallel days; per-day staging deleted by default). Use
**`--only 04b`** or **`--from 04b`** for the legacy NCAR-only downloader.

## Stages 04b / 04c (GridRad)

- **04b** (`scripts/04b_download_gridrad.py`): default is **one convective day at a time**
  (12 UTC → 12 UTC; plan + download per label). Staging:
  `gridrad(_severe)/by_convective_day/YYYYMMDD/`. **`--plan-all-days-first`** restores
  the legacy global plan-then-download flow. **`--workers`** defaults to **1**
  (parallel HTTP GETs *within* the current day only; respect NCAR throttling guidance).
  Hourly sources: **d841000** (V3.1, through 2017) then **d841001** (V4.2 warm-season
  Apr–Aug fallback for 2018+ when Severe is absent).
- **04c** (`scripts/04c_fill_gridrad_gap.py`): default **`--workers 1`** (sequential days).
  After each day finishes, **`delete_gridrad_inputs_for_day`** removes that day’s trees
  under `by_convective_day/YYYYMMDD/` in both `gridrad/` and `gridrad_severe/` unless
  **`--keep-gridrad-inputs`**. **`--with-04b-download`** chains **04b**’s
  **`download_for_day_adaptive`** before **`process_day`** (severe-first: download
  GridRad-Severe when the catalog lists it; skip hourly unless severe is absent or
  does not cover the full 12 UTC → 12 UTC window; hourly tries **d841000** then
  **d841001** for Apr–Aug 2018+). With **`--workers > 1`**, each worker
  process uses its own HTTP session (04b is loaded once per worker via a pool
  initializer; mind **`workers × --04b-download-workers`** vs NCAR throttling).
- **04c reflectivity:** use sparse **`Reflectivity(Index)` + `index`** (not **`Nradecho`**, which is not dBZ). **v2.2.3+** applies native echo-frequency filter + clutter removal (`_gridrad_qc.py`) before SHI unless `--no-gridrad-native-qc`.
- **04c disk / workers:** `run_pipeline.py` passes **`--workers 4`** by default. With **`--with-04b-download`**, up to four concurrent day trees under `gridrad_severe/` can use ~8–12 GB each. On constrained disks, run **`scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2`** (or `1`) directly instead of `run_pipeline.py --only 04c`.
- **04c resume / backfill:** **`--missing-only`** processes only convective days without an output GeoTIFF (skips existing `mesh_*.tif`). **`--from-date`** / **`--until-date`** bound the window. Manifest rebuild: **`--manifest-only`**.

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

Before any full pipeline execution **or any git commit**:

```bash
./scripts/quality_gate.sh
```

Then review `docs/REVIEW_PRE_RUN.md` before launching production stages.

## Key Constants

These come from `scripts/_config.py`.

| Constant | Value | Meaning |
|---|---:|---|
| `NROWS` | 520 | Grid rows, north to south |
| `NCOLS` | 1180 | Grid columns, west to east |
| `DX` | 0.05 degree | Cell size |
| `LAT_MAX` | 50.005 | North edge of row 0 |
| `LON_MIN` | -125.005 | West edge of col 0 |
| `DAMAGE_THRESH_MM` | 25.4 | 1-inch damage onset (occurrence, Stage 13 severe-cell counts) |
| `EVENT_ACTIVE_THRESH_MM` | 29.0 | Cintineo/Wendt skill threshold (Stage 08 events, Stage 05 winter filter) |
| `GPD_THRESH_MM_DEFAULT` | 50.8 | 2-inch EVT tail starting threshold |
| `MAX_HAIL_MM` | 300.0 | Physical QA cap on hail diameter values |
| `RNG_SEED` | 42 | Stochastic RNG seed |
| `N_SIM_YEARS` | 50000 | Catalog length |
| `POOL_RADIUS_KM` | 150 | Stage 10 smoothing radius |
| `DECAY_KM` | 75 | Stage 10 exponential decay |
| `N_REGIONS_DEFAULT` | 6 | K-means EVT regions |
| `TRANSLATE_CELLS` | +/-3 | Stage 13 spatial translation |
| `MAX_CENTROID_KM_DAY` | 150.0 | Stage 08 merge check |

## Current Status

Repository identity is **v2.3.0** on branch **`v2.3.0`**, with `origin` as the
sole remote. Pipeline run status is **unverified since 2026-07-09**; do not
assert completion or reuse historical archive counts as current. The one
canonical run-state section, verification steps, and ordered next actions are
in [`docs/RUN_NOTES.md`](docs/RUN_NOTES.md#canonical-current-run-state).

The Stage 05 path is five core artifact passes plus site-specific remediation
as a sixth layer, enabled by default. SPC reports are validation-only and are
**never** applied to hazard rasters (AGENTS rule #3). Optional
`train_artifact_classifier.py` / `--retrain-models` may train a diagnostic
classifier from Stage 06 pairs after a deterministic Stage 05 → Stage 06
baseline; that artifact is not a hazard-input path.

## Production Run Summary (v2.2.1, 2026-06-30 — superseded)

Prior full run (pre–Stage 01 eastern-CONUS fix). Keep numbers for historical comparison only;
do not cite as final v2.2.2 hazard results.

| Stage | Key result (superseded) |
|-------|------------|
| 05 | 9,797 corrected days; era-pooled QM |
| 06 | 173,766 SPC validation pairs |
| 08 | 8,798 events; λ ≈ 303 yr⁻¹ at 29 mm |
| 09–12 | Analytical RP maps through 50,000 yr |
| 13 | 50k-yr stochastic catalog (~5.4 h) |
| 14 | Figures + validation report |

## Run Operations

Do not use a stale screen-session name as evidence of current state. Before
resuming, follow the checks in
[`docs/RUN_NOTES.md`](docs/RUN_NOTES.md#canonical-current-run-state). That
section also owns the two-pass baseline → Stage 06 → optional classifier
workflow and all current next actions.

## Documentation Quick Reference

| Need | Read |
|---|---|
| Current run state and next commands | `docs/RUN_NOTES.md` |
| Session handoff | `docs/HANDOFF.md` |
| Scientific methodology | `docs/methodology.md` |
| Per-stage implementation | `docs/technical_documentation.md` |
| Output schemas | `docs/data_dictionary.md` |
| Reproduction guide | `docs/reproduce.md` (local + §14 AWS Fargate) |
| AWS Fargate adapter | `aws/README.md` |
| AWS adapter design | `docs/superpowers/specs/2026-07-17-aws-fargate-adapter-design.md` |
| Data / Zenodo archival | `docs/DATA_AVAILABILITY.md` |
| Uncertainty disclosures | `docs/uncertainty.md` |
| Extended AI operating rules | `docs/ai_instructions.md` |
| Stable identity and historical work log | `docs/project_memory.md` |
| Full review findings | `docs/REVIEW_2026-05-01.md` |
| Pre-run audit | `docs/REVIEW_PRE_RUN.md` |
| 2026-08-05 agent audit + reaudit | `docs/AGENT_AUDIT_2026-08-05.md` |
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
