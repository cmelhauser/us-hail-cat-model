# AI Instructions for Future Work

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Purpose

This document gives future AI agents and developers explicit instructions for working on the CONUS Hail Catastrophe Model. It exists to prevent accidental regressions, memory blowups, documentation drift, and methodology changes that break the model’s defensibility.

---

## 2. Always Do

When changing the project:

1. Preserve the 15-stage pipeline unless the user explicitly requests a future major-version redesign.
2. Preserve file paths and output schemas unless a migration is documented.
3. Keep raster operations vectorized whenever possible.
4. Use sparse event arrays for event storage and stochastic simulation.
5. Add tests when changing methodology or code.
6. Update documentation when changing outputs, assumptions, or stage behavior.
7. Preserve deterministic fallback behavior when adding optional ML.
8. Keep logs and outputs interpretable for technical review.
9. Use a run manifest for full runs.
10. Clearly distinguish hazard from loss.

---

## 3. Never Do

Do not:

1. Build dense `(n_events, 520, 1180)` event cubes in production.
2. Make Stage 05 dependent on optional ML artifacts.
3. Use SPC reports as the primary hazard surface.
4. Change grid constants without a model-version bump.
5. Treat Stage 14 vulnerability curves as claims-calibrated.
6. Ignore analytical/stochastic divergence.
7. Remove validation outputs to simplify runtime.
8. Replace deterministic logic with black-box-only logic.
9. Change output file names without updating the data dictionary.
10. Assume missing SPC reports mean radar false alarms.

---

## 4. High-Risk Stages

### Stage 05 — Bias correction and filtering

Must support:

- MESH75 correction;
- GridRad quantile fallback;
- optional conditional calibration;
- optional probabilistic filtering;
- deterministic fallback with `--skip-ml`.

### Stage 08 — Event catalog

Must preserve:

- damage threshold;
- temporal grouping;
- buffered footprint overlap;
- duration cap;
- centroid and intensity checks;
- sparse `event_peaks.npz`.

### Stage 09 — CDF fitting

Must output:

- CDF parameters;
- RP maps;
- fitting report;
- threshold diagnostics;
- MRL diagnostic plots.

### Stage 12 — Mask and topography

Must ensure:

- correction factors are bounded;
- no correction is applied outside CONUS;
- neutral fallback if DEM is absent.

### Stage 13 — Stochastic catalog

Must operate on:

```text
rows, cols, vals
```

Must not reconstruct all event templates into dense grids.

### Stage 15 — Figures

Must render diagnostics that expose model risk, including analytical vs stochastic comparison.

---

## 5. Required Test Categories

Tests should cover:

- grid constants;
- block maximum;
- SPC parsing;
- ERA5 variable checks;
- SHI/MESH75 conversion;
- Stage 05 fallback behavior;
- environmental filter monotonicity;
- event grouping edge cases;
- sparse NPZ consistency;
- GPD threshold diagnostics;
- RP monotonicity;
- topographic correction bounds;
- sparse stochastic translation and scaling;
- MDR monotonicity;
- figure smoke tests;
- run_pipeline stage selection and dry run.

---

## 6. Documentation Rules

When changing code, update:

- `README.md` for user-facing behavior;
- `docs/methodology.md` for scientific assumptions;
- `docs/technical_documentation.md` for implementation behavior;
- `docs/data_dictionary.md` for outputs and schemas;
- `docs/reproduce.md` for run commands;
- `docs/REVIEW_PRE_RUN.md` if the change affects run readiness.

If a new output is added, it must appear in the data dictionary.

If a new assumption is added, it must appear in the methodology.

---

## 7. Before Full Runs

Always run:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

For Stage 13, run a smaller stochastic smoke test before 50,000 years:

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

---

## 8. Review Behavior

When asked to review the project:

1. Check Stage 05 fallback behavior.
2. Check Stage 08 sparse outputs.
3. Check Stage 09 threshold diagnostics.
4. Check Stage 13 sparse safety.
5. Check docs and tests remain synchronized.
6. Identify scientific limitations separately from implementation bugs.
7. Avoid overengineering v2.1 into a v3.0 redesign unless explicitly requested.

---

## 9. New Files Added 2026-05-01 (While Pipeline Was Running)

The following files were created on 2026-05-01 while the first full pipeline
run executed. They are additive (no changes to existing scripts or outputs).

### Project metadata
- `LICENSE` — MIT, with data-source licence notes (NOAA, NCAR RDA, Copernicus, SPC)
- `CHANGELOG.md` — versioned history: v1.0 → v2.0 → v2.1
- `CITATION.cff` — machine-readable academic citation (Murillo & Homeyer 2021 as primary reference)
- `CONTRIBUTING.md` — dev workflow, branch naming, methodology-change policy
- `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1
- `SECURITY.md` — vulnerability reporting; pickle-file and download-integrity caveats
- `pyproject.toml` — project metadata, ruff/mypy/pytest/coverage config, `[dev]` extras
- `.pre-commit-config.yaml` — ruff, mypy, pre-commit-hooks, detect-secrets, yamllint
- `environment.yml` — conda environment (Python 3.11, all geo deps) for Docker

### GitHub infrastructure
- `.github/workflows/tests.yml` — CI: lint + type-check + unit tests (3.10/3.11/3.12) + dry-run + coverage
- `.github/ISSUE_TEMPLATE/bug.md`
- `.github/ISSUE_TEMPLATE/methodology.md`
- `.github/ISSUE_TEMPLATE/feature.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `Dockerfile` — reproducible container (micromamba/jammy base)
- `.dockerignore`

### Documentation
- `docs/README.md` — documentation index with three reading paths
- `docs/uncertainty.md` — six-category uncertainty budget with quantitative ranges
  and implementation sketch for bootstrap CIs (v2.2 priority)

### Code (draft, not yet wired into stage scripts)
- `scripts/_config.py` — single source of truth for grid constants, repo paths,
  physical constants, EVT/RP/stochastic defaults. Stage scripts still inline-define
  NROWS/NCOLS/etc. — migration to import from `_config` is the next post-run task.
- `scripts/_logging.py` — `get_logger(stage_name, log_dir)` helper to replace
  the 15 per-stage `log()` print functions. Migration instructions in docstring.

### Key outstanding items (see REVIEW_2026-05-01.md for full list)
- `requirements.txt` header still says v2.0 / Python 3.9 — fix at next env rebuild
- Stage scripts still inline grid constants — apply `_config.py` import refactor
  stage-by-stage after the run completes
- Stage scripts still use print-based `log()` — apply `_logging.py` refactor post-run
- Run manifest not yet implemented in `run_pipeline.py`
- Integration smoke test not yet written
- Bootstrap CIs on RP estimates not yet implemented (awaiting first-run outputs)

---

## 10. Compact Project Context

```text
CONUS Hail Cat Model v2.1 is a radar-first hail hazard model on a 0.05° CONUS grid. It uses MYRORSS, GridRad, MRMS, ERA5, and SPC validation. It has a 15-stage pipeline. Stage 08 creates sparse event arrays. Stage 13 must remain sparse-safe. The model produces hazard, not loss. Vulnerability is placeholder. v2.1 adds fallback-safe calibration/filtering, event merge checks, threshold diagnostics, bounded topography, expanded tests, and complete documentation. On 2026-05-01 the first full pipeline run began. While it ran, project metadata (LICENSE, CHANGELOG, CITATION, pyproject.toml, Dockerfile, CI workflow, issue templates), docs (README index, uncertainty budget), and code helpers (_config.py, _logging.py) were added as new files without modifying any running scripts.
```
