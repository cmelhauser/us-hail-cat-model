# Project Memory

**CONUS Hail Catastrophe Model v2.1**

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

## 2. Current State

The project has been upgraded from v2.0 to v2.1. This was not a full redesign. It was a hardening update focused on defensibility, testability, and run-readiness.

The v2.1 project now includes:

- updated methodology;
- updated technical documentation;
- updated data dictionary;
- updated reproduction guide;
- updated README;
- migration notes;
- literature review;
- plain-language explainer;
- pre-run review document;
- AI instructions for future work.

The critical code and methodology emphasis is that sparse event storage must remain authoritative, especially for Stage 13.

Stage 01 also now preserves MYRORSS source provenance. It reads both plain
`.netcdf` and gzipped `.netcdf.gz` MYRORSS archive objects and writes
`data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`. The manifest is
the authoritative distinction between missing source days and days where source
files existed but produced no hail pixels; all-zero GeoTIFFs alone do not carry
that distinction.

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

Optional ML components may improve calibration or filtering, but deterministic fallback must always work.

### Dual tail review

Analytical return-period maps and stochastic return-period maps should be compared. Large divergence is a model-risk signal.

### Documentation and tests are part of the model

Any future methodology change must update tests and documentation.

### Source coverage is explicit

Do not infer MYRORSS source availability from GeoTIFF values or file size. Use
the Stage 01 manifest statuses (`missing_source`, `no_hail_pixels`, `ok`, and
read-error variants).

---

## 4. High-Risk Stages

### Stage 05

Handles source calibration and environmental filtering. It must run with or without optional model artifacts.

### Stage 08

Builds the historical event catalog. It must preserve physical merge constraints and sparse storage.

### Stage 09

Fits frequency-severity distributions. It must emit threshold diagnostics.

### Stage 12

Applies topographic correction and CONUS mask. It must keep correction factors bounded.

### Stage 13

Generates the stochastic catalog. It must remain sparse-safe and must not reconstruct all events as dense grids.

---

## 5. Current v2.1 Upgrade Themes

- Conditional GridRad calibration with fallback.
- Probabilistic environmental filtering with fallback.
- Centroid and intensity checks for event grouping.
- Automated GPD threshold diagnostics.
- Sparse stochastic translation and scaling.
- Topographic correction using elevation relative to freezing level when available.
- Expanded validation and testing.
- Documentation synchronized to implementation.
- Stage 01 source manifest and plain/gz NetCDF archive handling.

---

## 6. Known Scientific Limitations

These should remain tracked in future work:

1. Long return periods remain extrapolative.
2. Spatial dependence is simplified.
3. Climate non-stationarity is not embedded.
4. GridRad gap-fill uncertainty remains.
5. Vulnerability is placeholder only.
6. SPC validation is biased and incomplete.

---

## 7. Work Log — 2026-05-01

First full pipeline run started via Codex (commit `38a6879`, Python 3.9.6
`.venv`, branch `v2.1`). While the run executed, the following were added as
new files (no modifications to any running scripts):

### Completed ✅

**Project metadata:**
- `LICENSE` (MIT + data-source licence notes)
- `CHANGELOG.md` (v1.0 → v2.0 → v2.1 history)
- `CITATION.cff` (machine-readable academic citation)
- `CONTRIBUTING.md` (dev workflow, methodology-change policy)
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1)
- `SECURITY.md` (pickle-file and download-integrity caveats)
- `pyproject.toml` (project metadata, ruff/mypy/pytest/coverage config)
- `.pre-commit-config.yaml` (ruff, mypy, pre-commit-hooks, detect-secrets)
- `environment.yml` (conda env: Python 3.11 + all geo deps)
- `Dockerfile` + `.dockerignore` (reproducible container, micromamba/jammy)

**GitHub infrastructure:**
- `.github/workflows/tests.yml` (CI: lint + type-check + unit tests 3.10/3.11/3.12 + coverage)
- `.github/ISSUE_TEMPLATE/bug.md`
- `.github/ISSUE_TEMPLATE/methodology.md`
- `.github/ISSUE_TEMPLATE/feature.md`
- `.github/PULL_REQUEST_TEMPLATE.md`

**Documentation:**
- `docs/README.md` (index with three reading paths and per-document summaries)
- `docs/uncertainty.md` (six-category uncertainty budget + bootstrap CI sketch)
- `SKILL.md` (repo root; dense AI/developer orientation file)

**Code helpers (draft, not yet wired into stage scripts):**
- `scripts/_config.py` (single source of truth for grid constants + paths + EVT defaults)
- `scripts/_logging.py` (`get_logger()` factory to replace 15× print-based `log()`)

**File organisation:**
- `REVIEW_PRE_RUN.md` renamed to `REVIEW_PRE_RUN.md` (sits alongside `REVIEW_2026-05-01.md`)
- All references to `REVIEW_PRE_RUN.md` updated across docs

### Outstanding after run completes ⏳

In priority order:

1. **`_config.py` import refactor** — replace inline `NROWS = 520` etc. in each stage script.
2. **`_logging.py` migration** — replace print-based `log()` in each stage script.
3. **Run manifest** — implement in `run_pipeline.py` (code snippet in `REVIEW_2026-05-01.md §B.9`).
4. **Integration smoke test** — `tests/integration/test_smoke_synthetic.py`.
5. **Regression / golden-output tests** — requires first-run outputs.
6. **Bootstrap CIs on Stage 09 RP estimates** — sketch in `docs/uncertainty.md §3.1`.
7. **`requirements.txt` header fix** — update from v2.0/Python 3.9 to v2.1/Python 3.10.
8. **Python 3.10+ `.venv`** — rebuild environment at next convenient point.
9. **Validate README completeness** — confirm §5 (Vulnerability) and all docs listed.
10. **`docs/sensitivity.md`** — hyperparameter sweep plan.
11. **`docs/benchmarks.md`** — published RP comparison framework.

---

## 8. Future Work Priorities

1. Complete first full pipeline run; review Stage 15 figures and tail diagnostics.
2. Apply `_config.py` and `_logging.py` refactors stage-by-stage.
3. Add bootstrap CI outputs to Stage 09.
4. Build integration and regression tests.
5. Build a post-run validation dashboard.
6. Add non-stationarity diagnostics (Mann-Kendall).
7. Improve spatial dependence documentation (extremogram).
8. Add exposure integration.
9. Add claims-calibrated vulnerability if data become available.
10. Consider a v3.0 generative storm swath model.

---

## 8. Compact Context for Future AI Agents

```text
Project: CONUS Hail Cat Model v2.1.
Radar-first hail hazard model on 0.05° CONUS grid.
Pipeline has 15 stages.
SPC reports are validation only.
Stage 08 stores sparse event arrays.
Stage 13 must remain sparse-safe and must not build dense event cubes.
v2.1 adds fallback-safe calibration/filtering, event merge checks, threshold diagnostics, topographic correction, expanded tests, and full documentation.
Hazard only; vulnerability is placeholder and not claims-calibrated.
```

---

## 9. Pre-Run Commands

Before full run:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

After outputs exist:

```bash
python run_pipeline.py --validate
```
