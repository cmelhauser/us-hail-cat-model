# SKILL.md — CONUS Hail Catastrophe Model v2.1

> **For AI agents and developers.** This file is the single fastest way to
> orient yourself to this project. Read it before touching anything. For depth
> on any topic, follow the links into `docs/`.
>
> Auto-detection note: Claude Code reads `CLAUDE.md`; Codex reads `AGENTS.md`.
> This file (`SKILL.md`) is not auto-injected but will be found in any
> directory listing. Reference it explicitly in your system prompt if needed.
>
> Last updated: 2026-05-02 (post full-repo scan).

---

## What This Project Is

A **radar-based probabilistic hail hazard model** for the Continental United
States. It ingests three NOAA/NCAR radar datasets, applies bias correction and
EVT fitting, and generates return-period hazard maps and a 50,000-year
stochastic event catalog.

- **Version:** 2.1.0 (hardening release; no methodology redesign from v2.0)
- **Output:** gridded hail hazard — hazard only, not loss
- **Grid:** 0.05°, 520 rows × 1180 columns, CONUS
- **Record:** MYRORSS 1998–2011 · GridRad 2012–2019 · MRMS 2020–present
- **Pipeline:** 15 stages, all written and tested; first full run started 2026-05-01 via Codex
- **Python:** 3.10+ (current run environment: 3.9.6 via `.venv` — upgrade at next rebuild)

---

## Non-Negotiable Rules

Violating any of these requires explicit user sign-off and a version bump.

| # | Rule |
|---|------|
| 1 | **Stage 13 is sparse-safe.** Never build `(n_events, 520, 1180)` dense arrays. Operate on `rows, cols, vals` only. |
| 2 | **Stage 05 has a deterministic fallback.** `--skip-ml` must produce a complete, valid output with no optional ML artifact. |
| 3 | **SPC = validation only.** Never a hazard input. |
| 4 | **`event_peaks.npz` is authoritative.** Sparse arrays are the source of truth for Stage 13. |
| 5 | **0.05° grid is fixed in v2.1.** No other resolution. Any change = version bump + full rerun. |
| 6 | **Never commit data files.** `.tif`, `.npy`, `.npz`, `.nc`, `.grib2`, `.parquet`, `.pkl` are gitignored. |
| 7 | **Update tests and docs** whenever methodology or output schemas change. |
| 8 | **Grid constants come from `scripts/_config.py`.** Do not redefine `NROWS`, `NCOLS`, `DX`, `LAT_MAX`, `LON_MIN` in stage scripts. The refactor is complete across all 15 stages. |
| 9 | **Preserve source-coverage metadata.** Stage 01 GeoTIFF zeros alone do not distinguish missing source files from no-hail days; use `manifest_stage01_myrorss.csv`. |

---

## Known Issues / Discrepancies

No active constant-drift issues are known. `MAX_CENTROID_KM_DAY` was resolved on 2026-05-03, and the `_config.py`, `_logging.py`, and `_io.py` refactors are now wired into all stage scripts.

---

## Repository Layout

```
us-hail-cat-model/
├── SKILL.md                    ← you are here
├── docs/HANDOFF.md                  ← session handoff doc (read first in a new chat)
├── docs/REVIEW_PRE_RUN.md           ← pre-execution audit (read before any run)
├── docs/REVIEW_2026-05-01.md        ← comprehensive post-v2.1 review (frozen)
├── docs/RUN_NOTES.md                ← first-run context and commands
├── CHANGELOG.md                ← version history
├── CITATION.cff                ← academic citation
├── CONTRIBUTING.md             ← dev workflow and PR standards
├── pyproject.toml              ← project metadata, ruff/mypy/pytest config
├── environment.yml             ← conda environment (Python 3.11, all geo deps)
├── Dockerfile                  ← reproducible container
├── run_pipeline.py             ← pipeline entry point (see CLI below)
│
├── scripts/
│   ├── _config.py              ← grid constants, paths, EVT defaults (single source of truth)
│   ├── _logging.py             ← shared logger factory (get_logger)
│   ├── 01_download_myrorss.py
│   ├── 02_download_mrms_mesh.py
│   ├── 03_download_spc.py
│   ├── 04a_download_era5_isotherms.py
│   ├── 04b_fill_gridrad_gap.py
│   ├── 05_apply_mesh_bias_correction.py  ← HIGH RISK: fallback must work
│   ├── 06_validate_mesh_vs_spc.py
│   ├── 07_build_hail_climo.py
│   ├── 08_build_event_catalog.py         ← HIGH RISK: sparse output; centroid cap = 150.0 km/day
│   ├── 09_fit_cdf_regional.py            ← HIGH RISK: threshold diagnostics
│   ├── 10_build_smooth_cdf.py
│   ├── 11_build_occurrence_probs.py
│   ├── 12_apply_conus_mask.py            ← HIGH RISK: topography bounds
│   ├── 13_generate_stochastic_catalog.py ← HIGH RISK: sparse-safe required
│   ├── 14_build_vulnerability.py         ← PLACEHOLDER: not claims-calibrated
│   └── 15_render_figures.py
│
├── tests/                      ← 28 pytest files; one per stage + conftest
│   ├── conftest.py             ← load_stage() helper + load_script fixture
│   ├── test_01_*.py … test_15_*.py
│   ├── test_stage*.py          ← deeper unit tests for high-risk stages
│   ├── test_run_pipeline.py
│   └── integration/              ← synthetic smoke/integration tests
│
├── docs/
│   ├── README.md               ← documentation index (start here)
│   ├── methodology.md          ← full scientific methodology
│   ├── technical_documentation.md  ← per-stage implementation
│   ├── data_dictionary.md      ← output schemas and units
│   ├── reproduce.md            ← step-by-step run instructions
│   ├── uncertainty.md          ← six-category uncertainty budget
│   ├── executive_summary.md
│   ├── explainer.md
│   ├── literature_review.md
│   ├── migration_plan.md
│   ├── ai_instructions.md      ← extended AI operating instructions
│   ├── project_memory.md       ← canonical project state + work log
│   └── figures/                ← generated at run time (gitignored)
│
├── data/                       ← gitignored; generated at run time
│   ├── historical/             ← raw + corrected MESH, ERA5, SPC, events
│   ├── analysis/               ← CDF params, RP maps, occurrence, topography, vulnerability
│   └── stochastic/             ← 50k-yr catalog, RP maps, PET tables
│
└── logs/                       ← gitignored; one .log per stage
```

---

## Pipeline CLI

All commands run from repo root with `.venv/bin/python` (or `python` in the
activated env / Docker container).

```bash
# Full run (recommended cautious order)
python run_pipeline.py --only 01
python run_pipeline.py --only 02
python run_pipeline.py --only 03
python run_pipeline.py --only 04a
python run_pipeline.py --only 04b
python run_pipeline.py --only 05 --skip-ml   # deterministic calibration
python run_pipeline.py --from 06 --skip-ml

# After all outputs exist
python run_pipeline.py --validate

# Stage 13 sparse-safe smoke test before full stochastic run
python scripts/13_generate_stochastic_catalog.py --n-years 1000

# Useful flags
--from N          # run stages N through 15
--only N          # run exactly stage N
--skip 14,15      # exclude stages
--dry-run         # validate config and I/O paths without executing
--validate        # re-run output validation for all stages
--skip-ml         # force deterministic fallback in Stage 05
--retrain-models  # retrain optional ML artifacts in Stage 05
```

---

## Stage 01 Data Provenance

Stage 01 reads MYRORSS MESH timesteps from public S3. Early archive days may be
stored as plain `.netcdf`; later days are often `.netcdf.gz`. The downloader
must accept both forms and write one daily GeoTIFF at
`data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`.

Daily GeoTIFF rasters use `0.0` for no MESH signal, so the raster by itself does
not say whether the day had no source files or had source files with no hail
pixels. The authoritative distinction is the Stage 01 manifest:

`data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`

Manifest statuses:

| Status | Meaning |
|---|---|
| `missing_source` | No MYRORSS NetCDF objects were available for that day. |
| `no_hail_pixels` | Source files existed, but no valid CONUS hail pixels were found. |
| `ok` | Source files existed and produced at least one active 0.05° cell. |
| `ok_with_read_errors` | Some source files failed to read, but the day still produced active cells. |
| `no_hail_pixels_with_read_errors` | Some source files failed and no active cells were produced. |
| `error` | All source files failed to read. |

---

## Pre-Run Checklist

Always run before any full pipeline execution:

```bash
python -m py_compile run_pipeline.py scripts/*.py   # syntax check all scripts
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

Then review `docs/REVIEW_PRE_RUN.md` (the permanent audit artifact).

---

## Key Constants (from `scripts/_config.py`)

| Constant | Value | Meaning |
|---|---|---|
| `NROWS` | 520 | Grid rows (N→S) |
| `NCOLS` | 1180 | Grid columns (W→E) |
| `DX` | 0.05° | Cell size (~5.5 km) |
| `LAT_MAX` | 50.005°N | North edge of row 0 |
| `LON_MIN` | −125.005°E | West edge of col 0 |
| `DAMAGE_THRESH_MM` | 25.4 mm | 1-inch damage threshold |
| `MAX_HAIL_MM` | 250.0 mm | Hard cap on MESH75 |
| `RNG_SEED` | 42 | Stochastic RNG seed |
| `N_SIM_YEARS` | 50,000 | Catalog length |
| `RP_YEARS` | (10,25,50,100,200,250,500,1000,5000,10000,50000) | Return periods |
| `POOL_RADIUS_KM` | 150 km | Stage 10 smoothing radius |
| `DECAY_KM` | 75 km | Stage 10 exponential decay |
| `N_REGIONS_DEFAULT` | 6 | K-means EVT regions |
| `TRANSLATE_CELLS` | ±3 | Stage 13 spatial translation |
| `MAX_CENTROID_KM_DAY` | 150.0 | Stage 08 merge check (fixed 2026-05-03; matches `_config.py`) |

---

## Current Status (as of 2026-05-02 scan)

| Area | Status |
|---|---|
| All 15 stage scripts | ✅ Written and syntax-checked |
| Tests (unit) | ✅ 28 test files, all stages covered |
| Tests (integration) | ✅ `tests/integration/test_smoke_synthetic.py` written |
| Tests (no-dup-constants) | ✅ `tests/test_no_duplicated_constants.py` written |
| First full pipeline run | ⏳ In progress (started 2026-05-01, via Codex) |
| Project metadata | ✅ LICENSE, CHANGELOG, CITATION, CONTRIBUTING, COC, SECURITY |
| Python project config | ✅ pyproject.toml, .pre-commit-config.yaml |
| CI/CD | ✅ .github/workflows/tests.yml |
| Docker | ✅ Dockerfile + environment.yml + .dockerignore |
| GitHub infra | ✅ Issue templates, PR template |
| docs/README.md | ✅ Documentation index |
| docs/uncertainty.md | ✅ Six-category uncertainty budget |
| docs/sensitivity.md | ✅ Written (hyperparameter sweep plan, stages 08/09/10/12/13) |
| docs/benchmarks.md | ✅ Written (published RP comparison framework) |
| docs/FAQ.md | ✅ Written |
| docs/vulnerability_derivation.md | ✅ Written (MDR sources, limitations, calibration path) |
| scripts/_config.py | ✅ Written; **15/15 stage scripts import from it** |
| scripts/_logging.py | ✅ Written; **15/15 stage scripts import from it** |
| scripts/_io.py | ✅ Written; shared `write_geotiff`, `haversine_km`, and `latlon_to_grid` are imported by stage scripts where needed |
| Stage 01 source manifest | ✅ Implemented |
| Pipeline run manifest | ⏳ In progress |
| Bootstrap CIs on RP maps | ⏳ Pending first-run outputs |
| Regression / golden tests | ⏳ Pending first-run outputs |
| MAX_CENTROID_KM_DAY mismatch | ✅ Resolved 2026-05-03 — stage 08 corrected to 150.0 |
| σ_perturb doc accuracy | ✅ Methodology and uncertainty docs now match the monthly CV implementation |

---

## What To Do After The First Run Completes

In priority order:

1. **Review Stage 15 figures** once the full pipeline finishes — analytical vs stochastic RP comparison.
2. **Write regression tests** against first-run golden outputs.
3. **Add bootstrap CIs to Stage 09** (sketch in `docs/uncertainty.md §3.1`).
5. **Write regression tests** against first-run golden outputs.
6. **Add bootstrap CIs to Stage 09** (sketch in `docs/uncertainty.md §3.1`).
7. **Upgrade `.venv` to Python 3.10+** (current = 3.9.6, EOL Oct 2025).

---

## Documentation Quick-Reference

| Need | Read |
|---|---|
| Why things are the way they are | `docs/methodology.md` |
| What each stage does | `docs/technical_documentation.md` |
| What each output file contains | `docs/data_dictionary.md` |
| How to run the model | `docs/reproduce.md` |
| What uncertainties to disclose | `docs/uncertainty.md` |
| What the AI agent rules are | `docs/ai_instructions.md` |
| What the current project state is | `docs/project_memory.md` |
| What the full review found | `docs/REVIEW_2026-05-01.md` |
| What was checked before running | `docs/REVIEW_PRE_RUN.md` |
| Session handoff | `docs/HANDOFF.md` |
| How to contribute | `CONTRIBUTING.md` |
| Version history | `CHANGELOG.md` |

---

## Stack

Python 3.10+ · numpy · pandas · scipy · rasterio · xarray · regionmask ·
cartopy · lmoments3 · pyarrow · matplotlib · boto3 · s3fs · cfgrib · eccodes ·
netCDF4 · h5py · scikit-learn · cdsapi · tqdm · requests · tenacity

External accounts required: NCAR RDA (GridRad), Copernicus CDS (ERA5).
