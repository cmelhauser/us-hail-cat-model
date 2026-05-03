# Project Memory

**CONUS Hail Catastrophe Model v2.1**
**Last updated: 2026-05-02 (post full-repo scan)**

---

## 1. Canonical Project Identity

- **Name:** CONUS Hail Catastrophe Model
- **Current version:** v2.1
- **Model type:** hail hazard model
- **Domain:** continental United States
- **Primary hazard input:** radar-derived MESH / MESH75
- **Grid:** 0.05°, 520 rows × 1180 columns
- **Core architecture:** 15-stage Python pipeline
- **Core stochastic design:** sparse event resampling
- **Primary output:** gridded hail hazard return-period maps and stochastic event diagnostics
- **Not included:** production exposure, financial loss, or claims-calibrated vulnerability

---

## 2. Current State (as of 2026-05-02)

Branch `v2.1` is synced with `main` at commit `e4413dc`. Working tree clean.

First full pipeline run started 2026-05-01 via Codex. Still in progress as of 2026-05-02.

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

### 2026-05-01 ✅ Completed

First full pipeline run executed via Codex (Python 3.9.6, branch `v2.1`).
All items below were added as new files while the run executed — no running scripts were modified.
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
- `SKILL.md` (repo-root AI/developer orientation)

**Code helpers (on disk and wired into stage scripts):**
- `scripts/_config.py` — single source of truth for all grid constants, paths, EVT defaults
- `scripts/_logging.py` — `get_logger()` factory replacing stage-local print-based `log()` helpers
- `scripts/_io.py` — shared `write_geotiff`, `haversine_km`, and `latlon_to_grid` helpers used by stages that need them

**Refactoring:**
- `README.md` — full professional rewrite
- `PRE_RUN_REVIEW.md` renamed → `docs/REVIEW_PRE_RUN.md`; all cross-references updated

### 2026-05-01 — Stage 01 Manifest ✅

Stage 01 updated to produce `manifest_stage01_myrorss.csv`. Reads both plain `.netcdf` and gzipped `.netcdf.gz` MYRORSS archive objects. Manifest committed at `e4413dc`, merged to `main`.

### 2026-05-03 — Pre-pipeline fixes and PNAS article update ✅

- `scripts/08_build_event_catalog.py`: `MAX_CENTROID_KM_DAY` corrected 100.0 → 150.0 (canonical per methodology.md §8.2 and _config.py)
- `tests/test_no_duplicated_constants.py`: MAX_CENTROID xfail converted to passing assertion
- `docs/pnas_article_ai_hail_model.md`: comprehensive update — author line (Christopher Melhauser, Ph.D., Independent Researcher, Google Scholar URL), repository URL, AI model names (`claude-sonnet-4-6`, `claude-opus-4-6`, `gpt-5.5-medium`), v2.1 stage descriptions (event merge logic, EVT threshold diagnostics, topographic correction, sparse safety), missing references (Cintineo 2012, Brown 2015), pipeline stage table rewritten, benchmark discussion paragraph added
- `docs/methodology.md §0`: notation glossary written (grid, hazard, occurrence, EVT, stochastic, topographic, vulnerability, abbreviations)
- All stale MAX_CENTROID references cleared: SKILL.md, HANDOFF.md, project_memory.md, ai_instructions.md

### 2026-05-02 — Full Repo Scan ✅

Complete grep scan and refactor of all 15 stage scripts confirming:
- 15/15 scripts import shared configuration from `_config.py`
- 15/15 scripts use `_logging.get_logger()` instead of print-based `log()` helpers
- Shared `_io.py` helpers are wired where needed (`write_geotiff`, `haversine_km`, `latlon_to_grid`)
- `RP_YEARS`, `DAMAGE_THRESH_MM`, `MAX_HAIL_MM`, and `MAX_CENTROID_KM_DAY` are sourced from `_config.py` where used
- 28 test files exist; no `tests/integration/` directory
- Missing docs: sensitivity.md, benchmarks.md, FAQ.md, vulnerability_derivation.md

Updated: docs/HANDOFF.md, SKILL.md, docs/project_memory.md, docs/ai_instructions.md

---

## 8. Immediate Priorities (next session)

In order:

1. **Review Stage 15 figures** once pipeline run completes
2. **Regression tests** — freeze golden outputs after first run
3. **Bootstrap CIs on Stage 09 RP estimates** once first-run outputs exist
6. **Bootstrap CIs on Stage 09 RP estimates** — sketch in `docs/uncertainty.md §3.1`
7. **Rebuild `.venv` to Python 3.10+** — current venv is Python 3.9.6 (EOL Oct 2025)
8. **PNAS article Results section** — fill in after pipeline completes

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
Project: CONUS Hail Cat Model v2.1.
Radar-first hail hazard model on 0.05° CONUS grid (520×1180).
15-stage Python pipeline. Run via run_pipeline.py.
SPC reports are validation only — never a hazard input.
Events stored as sparse arrays (rows, cols, vals). Stage 13 must never build dense event cubes.
Stage 05 must always work with --skip-ml (no ML artifacts required).
Stage 01 produces a source manifest — use it to distinguish missing-source days from no-hail days.
scripts/_config.py = single source of truth for all grid constants and is imported by all stage scripts.
scripts/_logging.py = get_logger() factory wired into all stage scripts.
MAX_CENTROID_KM_DAY=150.0 canonical (stage 08 corrected 2026-05-03; matches _config.py and methodology.md §8.2).
σ_perturb: monthly CV (Mar-Sep events ≥10), median, clipped [0.10,0.40] — documented in methodology.md §13.4 and uncertainty.md §5.1.
Git commits must be run from the user's terminal — sandbox cannot unlink .git/index.lock.
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
