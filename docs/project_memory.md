# Project Memory

**CONUS Hail Catastrophe Model v2.2**
**Last updated: 2026-06-30 (`v2.2.1` — full production run complete; Stages 01–15 validated)**

---

## 1. Canonical Project Identity

- **Name:** CONUS Hail Catastrophe Model
- **Current version:** v2.2.1 (dev branch); v2.2.0 on `main` until merge
- **Model type:** hail hazard model
- **Domain:** continental United States
- **Primary hazard input:** radar-derived MESH / MESH75
- **Grid:** 0.05°, 520 rows × 1180 columns
- **Core architecture:** 15-stage Python pipeline
- **Core stochastic design:** sparse event resampling
- **Primary output:** gridded hail hazard return-period maps and stochastic event diagnostics
- **Not included:** production exposure, financial loss, or claims-calibrated vulnerability

---

## 2. Current State (as of 2026-06-30)

Branch `v2.2.1` is active development; model `v2.2.1` on `v2.2.1`; `v2.2.0` remains on `main` until merged.

**v2.2.1 production run complete (2026-06-30):** full pipeline Stages 01–15 validated with `--skip-ml`.

| Metric | Value |
|--------|------:|
| Convective-day archive | 9,797 (5,023 MYRORSS + 2,714 GridRad + 2,060 MRMS) |
| Corrected MESH75 | 9,797 days; era-pooled QM; 29 mm winter filter |
| Historical events | 8,798 at 29 mm (~303 yr⁻¹) |
| Stochastic catalog | 50,000 yr; 15.17M synthetic events; σ = 0.225 |
| Stage 13 wall time | ~5.4 h (memmap-backed annual maxima) |

All stages 01–15: **complete** and output validation passed.

**Infrastructure complete.** All project metadata, CI, docs, and code-helper files have been written. Stage scripts now import shared constants from `_config.py`, shared logging from `_logging.py`, and shared I/O helpers from `_io.py` where needed.

**Known discrepancies:**

1. `MAX_CENTROID_KM_DAY`: **resolved 2026-05-03** — stage 08 corrected to `150.0`, matching `_config.py` and `methodology.md §2`. Test `test_max_centroid_km_day_stage08_matches_config` is now a passing assertion.
2. σ_perturb documentation: `docs/methodology.md §13` and `docs/uncertainty.md §5.1` match the implementation in `calibrate_sigma()`: monthly CV for months March–September, median across eligible months, clipped to [0.10, 0.40].

---

## 3. Core Design Principles

### Radar-first hazard

Radar-derived MESH is the main hazard input. SPC reports are validation and calibration support only.

### Sparse-first event handling

Events are stored as active-cell arrays:

```text
rows, cols, vals
```

This avoids dense event cubes and enables efficient stochastic simulation.

### Fallback-safe modeling

Optional ML components may improve calibration or filtering, but deterministic fallback must always work. `--skip-ml` must produce a complete, valid output.

### Dual tail review

Analytical return-period maps and stochastic return-period maps should be compared. Large divergence is a model-risk signal.

### Source coverage is explicit

Do not infer MYRORSS source availability from GeoTIFF values or file size. Use the Stage 01 manifest statuses (`missing_source`, `no_hail_pixels`, `ok`, and read-error variants). The manifest file is `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`.

### Documentation and tests are part of the model

Any future methodology change must update tests and documentation in the same commit.

---

## 4. High-Risk Stages

### Stage 05

Handles source calibration and environmental filtering. Must run with or without optional ML artifacts (`--skip-ml`).

### Stage 08

Builds the historical event catalog. Preserves physical merge constraints (centroid displacement ≤ 150 km/day — canonical value confirmed and corrected in stage 08 script on 2026-05-03) and sparse storage.

### Stage 09

Fits frequency-severity distributions. Must emit threshold diagnostics to `threshold_selection.csv`.

### Stage 11b

Prepares the DEM input for Stage 12 from NOAA/NCEI ETOPO 2022 60 arc-second surface elevation. Writes `data/analysis/topography/elevation_0.05deg.tif` on the canonical grid.

### Stage 12

Applies topographic correction and CONUS mask. Must keep correction factors bounded (1.0–1.25 with ERA5 FL; 1.0–1.20 fallback).

### Stage 13

Generates the stochastic catalog. Must remain sparse-safe. Must not reconstruct any event as a dense grid at any point in the loop.

---

## 5. v2.1 Upgrade Themes

- Conditional GridRad calibration with quantile-mapping fallback.
- Probabilistic environmental filtering with hard-threshold safety floor.
- Centroid displacement and intensity jump checks for event grouping.
- Automated GPD threshold diagnostics.
- Sparse-safe stochastic translation and scaling.
- Freezing-level-aware topographic correction (bounded).
- Stage 01 source manifest distinguishing missing-source days from true no-hail days.
- Expanded pytest suite with stage-level unit tests.
- Full documentation synchronized to implementation.
- Project infrastructure: CI, Docker, pyproject.toml, pre-commit, issue templates.

---

## 6. Known Scientific Limitations

1. Long return periods remain extrapolative (>~500 yr exceed the observed record).
2. Spatial dependence is simplified; inter-event correlation is not modeled.
3. Climate non-stationarity is not embedded in the hazard fit.
4. GridRad gap-fill uncertainty at the 2011 and 2020 source transitions.
5. Vulnerability is placeholder only; not claims-calibrated.
6. SPC validation is spatially biased and incomplete (rural underreporting).

---

## 7. Work Log

### 2026-06-27 ✅ GridRad V4.2 hourly fallback (d841001)

- **04b** now queries **d841001** (GridRad V4.2 warm-season hourly, Apr–Aug 2008–2021)
  after **d841000** (V3.1) when Severe is absent or incomplete, for convective days
  after 2017. Recovers additional Apr–Aug 2018–2020 gap days previously marked
  `missing_source`.
- **04c** source tags: `gridrad-hourly-v31`, `gridrad-hourly-v42`.
- Re-run: `scripts/04c_fill_gridrad_gap.py --with-04b-download --missing-only`.

### 2026-06-27 ✅ Stage 04c primary ingest complete

- Production runs **2026-06-08 → 2026-06-27** wrote **2,501** gap-era TIFFs (**2012-01-01 → 2020-10-10**).
- Manifest `manifest_stage04c_gridrad.csv` complete for all **3,209** convective days.
- **`--missing-only`** backfill launched for days still without a GeoTIFF (708 queued).
- Mesh archive: **9,584** TIFFs (5,023 MYRORSS + 2,501 GridRad + 2,060 MRMS).
- Mesh peak diagnostic regenerated under `data/analysis/mesh_daily_peaks/`.
- Run-status docs synchronized: `AGENTS.md`, `RUN_NOTES.md`, `HANDOFF.md`, `project_memory.md`, `ai_instructions.md`.

### 2026-06-08 ✅ Stage 04c severe-first GridRad policy

- **04c** with `--with-04b-download` now calls **`download_for_day_adaptive`** (severe-first).
- **`find_gridrad_files`** merges hourly only for timesteps not covered by staged severe.
- **`scripts/_io.py`:** `staged_nc_files_for_convective_day`, `convective_window_coverage_ok`.
- Docs synced: `AGENTS.md`, `technical_documentation.md`, `reproduce.md`, `FAQ.md`,
  `RUN_NOTES.md`, `data_dictionary.md`, `CHANGELOG.md`, `README.md`.

### 2026-06-08 ✅ Stage 02 (MRMS) complete

- Stage 02 finished after **86.4 hours** at **06:19 EDT**.
- **2,060** convective-day MRMS rasters (**2020-10-14 → 2026-06-04**); manifest 2,059 `ok`, 1 `ok_with_read_errors`.
- Output validation passed; peak MESH **299.9 mm**.
- Combined mesh archive at the time: **7,083** TIFFs (5,023 MYRORSS + 2,060 MRMS); gap era ingest started same day.
- **Stage 04c** production run launched 2026-06-08.
- Run-status docs synchronized: `AGENTS.md`, `RUN_NOTES.md`, `HANDOFF.md`, `project_memory.md`, `ai_instructions.md`.

### 2026-05-20 ✅ Stage 04c reflectivity fix + mesh diagnostic

- **04c** now reconstructs sparse **`Reflectivity(Index)`** (dBZ) instead of using **`Nradecho`** for SHI; longitudes normalized from 0–360°.
- Gap-fill GeoTIFFs carry GDAL tags (`MAX_MESH75_MM`, `ACTIVE_CELLS`, …) for operational QA.
- **04c** run stopped for disk full; 2013 GridRad staging removed; restart with `--workers 2` documented in `RUN_NOTES.md` / `HANDOFF.md`.
- **`scripts/diagnostics/summarize_mesh_daily_peaks.py`** and tracked **`data/analysis/mesh_daily_peaks/`** added; `.gitignore` exception for that path only.
- Documentation synchronized across `technical_documentation.md`, `methodology.md`, `data_dictionary.md`, `FAQ.md`, `reproduce.md`, `RUN_NOTES.md`, `HANDOFF.md`, `README.md`, `AGENTS.md`, `CHANGELOG.md`, `pnas_article_ai_hail_model.md`.

### 2026-05-01 ✅ Completed

First full pipeline run started via Codex (Python 3.9.6, originally coordinated
on branch `v2.1` before the project moved back to `main`).
All items below were added as new files while the run executed.
Committed and merged to `main` at `e582d5d`.

**Project metadata:**
- `LICENSE`, `CHANGELOG.md`, `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`

**Python/CI infrastructure:**
- `pyproject.toml` (requires-python ≥3.10, ruff, mypy, pytest, coverage)
- `.pre-commit-config.yaml` (ruff, mypy, pre-commit-hooks, detect-secrets)
- `environment.yml` (conda: Python 3.11 + all geo deps)
- `Dockerfile` + `.dockerignore` (micromamba/jammy, health check)
- `.github/workflows/tests.yml` (CI: Python 3.10/3.11/3.12 matrix, ruff, mypy, pytest, codecov)
- `.github/ISSUE_TEMPLATE/{bug,methodology,feature}.md`, `.github/PULL_REQUEST_TEMPLATE.md`

**Documentation:**
- `docs/README.md` (documentation index with reading paths)
- `docs/uncertainty.md` (six-category uncertainty budget)
- `docs/PR_v1_to_v2.1.md` (full PR description for the v1.0 → v2.1 arc)
- `AGENTS.md` (repo-root AI/developer orientation)

**Code helpers (on disk and wired into stage scripts):**
- `scripts/_config.py` — single source of truth for all grid constants, paths, EVT defaults
- `scripts/_logging.py` — `get_logger()` factory replacing stage-local print-based `log()` helpers
- `scripts/_io.py` — shared `write_geotiff`, `haversine_km`, and `latlon_to_grid` helpers used by stages that need them

**Refactoring:**
- `README.md` — full professional rewrite
- `PRE_RUN_REVIEW.md` renamed → `docs/REVIEW_PRE_RUN.md`; all cross-references updated

### 2026-05-01 — Stage 01 Manifest ✅

Stage 01 updated to produce `manifest_stage01_myrorss.csv`. Reads both plain `.netcdf` and gzipped `.netcdf.gz` MYRORSS archive objects. Manifest committed at `e4413dc`, merged to `main`.

### 2026-05-04 — Stage 01 Physical QA Repair ✅

Stage 01 now enforces a post-processing QA scan over MYRORSS rasters. The QA
bound is `MAX_HAIL_MM = 300.0`; non-finite, negative, or larger values are reset
to `0.0`, and the manifest `active_cells_0p05`, `max_mesh_mm`, and `status`
fields are refreshed. The completed Stage 01 archive was repaired with
`python scripts/01_download_myrorss.py --qa-only`: the prior 250.0 mm pass repaired 199 files and 3,852 cells, including one non-finite file; after raising the bound to 300.0 mm, a full rescan found 0 files or cells requiring repair. Post-repair validation passed and no Stage 01 raster or manifest maximum exceeds 300.0 mm.

The same shared QA helper is now wired into Stage 02, Stage 04b, and Stage 05,
so raw MRMS, GridRad-derived gap-fill, and corrected MESH75 outputs all enforce
the same finite/non-negative/300.0 mm value invariant.

### 2026-05-03 — Pre-pipeline fixes and PNAS article update ✅

- `scripts/08_build_event_catalog.py`: `MAX_CENTROID_KM_DAY` corrected 100.0 → 150.0 (canonical per methodology.md §8.2 and _config.py)
- `tests/test_no_duplicated_constants.py`: MAX_CENTROID xfail converted to passing assertion
- `docs/pnas_article_ai_hail_model.md`: comprehensive update — author line (Christopher Melhauser, Ph.D., Independent Researcher, Google Scholar URL), repository URL, AI model names (`claude-sonnet-4-6`, `claude-opus-4-6`, `gpt-5.5-medium`), v2.1 stage descriptions (event merge logic, EVT threshold diagnostics, topographic correction, sparse safety), missing references (Cintineo 2012, Brown 2015), pipeline stage table rewritten, benchmark discussion paragraph added
- `docs/methodology.md §0`: notation glossary written (grid, hazard, occurrence, EVT, stochastic, topographic, vulnerability, abbreviations)
- All stale MAX_CENTROID references cleared: AGENTS.md, HANDOFF.md, project_memory.md, ai_instructions.md

### 2026-05-02 — Full Repo Scan ✅

Complete grep scan and refactor of all 15 stage scripts confirming:
- 15/15 scripts import shared configuration from `_config.py`
- 15/15 scripts use `_logging.get_logger()` instead of print-based `log()` helpers
- Shared `_io.py` helpers are wired where needed (`write_geotiff`, `haversine_km`, `latlon_to_grid`)
- `RP_YEARS`, `DAMAGE_THRESH_MM`, `MAX_HAIL_MM`, and `MAX_CENTROID_KM_DAY` are sourced from `_config.py` where used
- 28 pytest files exist, including `tests/integration/test_smoke_synthetic.py`
- Missing docs: sensitivity.md, benchmarks.md, FAQ.md, vulnerability_derivation.md

Updated: docs/HANDOFF.md, AGENTS.md, docs/project_memory.md, docs/ai_instructions.md

---

### 2026-05-03 — CI import fix ✅

- `tests/conftest.py`: adds repo root and `scripts/` to `sys.path` before stage
  module collection, preventing GitHub Actions from resolving repo `_io.py` to
  Python's stdlib `io` module.
- GitHub Actions PR checks pass on Python 3.10, 3.11, and 3.12.
- Commit: `e4c9331`.

## 8. Immediate Priorities

In order:

1. **Confirm Stage 04c `--missing-only` backfill is finished** (or accept manifest `missing_source` days).
2. **Re-run Stages 05–15 with `--skip-ml`** against the full dataset; this includes Stage 11b DEM preparation before Stage 12.
3. **Run Stage 13 smoke then full catalog** (`--n-years 1000`, then 50,000 years).
4. **Regenerate mesh-era diagnostic** if ingest changes (`scripts/diagnostics/summarize_mesh_daily_peaks.py`).
5. **Regenerate hail-day climatology** after Stage 05 (`scripts/diagnostics/hail_day_climatology.py`).
5. **Review Stage 15 figures** once production outputs exist.
6. **Regression tests** — freeze golden outputs after first production run.
7. **Bootstrap CIs on Stage 09 RP estimates** once first-run outputs exist.
8. **Rebuild `.venv` to Python 3.10+** — current run venv is Python 3.9.6 (EOL Oct 2025).
9. **PNAS article Results section** — fill in after pipeline completes.

---

## 9. Future Work (v2.2+)

1. Add bootstrap CI outputs to Stage 09 (confidence bounds on RP maps).
2. Build post-run validation dashboard.
3. Add non-stationarity diagnostics (Mann-Kendall trend test on annual MESH maxima).
4. Improve spatial dependence documentation (extremogram, tail dependence).
5. Add exposure integration.
6. Add claims-calibrated vulnerability if data become available.
7. Consider a v3.0 generative storm swath model.

---

## 10. Compact Context for AI Agents

```text
Project: CONUS Hail Cat Model v2.2.
Radar-first hail hazard model on 0.05° CONUS grid (520×1180).
15-stage Python pipeline. Run via run_pipeline.py.
SPC reports are validation only — never a hazard input.
Events stored as sparse arrays (rows, cols, vals). Stage 13 must never build dense event cubes.
Stage 05 must always work with --skip-ml (no ML artifacts required).
Active branch: v2.2.1. Model 2.2.1. Full production run complete 2026-06-30 (Stages 01–15).
9,797 mesh TIFFs; 8,798 events at 29 mm; 50k-yr stochastic catalog validated.
Stage 01/02 manifests distinguish missing-source days from no-hail days.
Mesh peak diagnostic: scripts/diagnostics/summarize_mesh_daily_peaks.py.
Hail-day climatology: scripts/diagnostics/hail_day_climatology.py.
scripts/_config.py = single source of truth for all grid constants and is imported by all stage scripts.
scripts/_logging.py = get_logger() factory wired into all stage scripts.
MAX_CENTROID_KM_DAY=150.0 canonical (stage 08 corrected 2026-05-03; matches _config.py and methodology.md §8.2).
σ_perturb: monthly CV (Mar-Sep events ≥10), median, clipped [0.10,0.40] — documented in methodology.md §13.4 and uncertainty.md §5.1.
```

---

## 11. Pre-Run Commands

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

After outputs exist:

```bash
python run_pipeline.py --validate
```
