# AI Instructions for Future Work

**CONUS Hail Catastrophe Model v2.1**
**Last updated: 2026-05-02 (post full-repo scan)**

---

## 1. Purpose

This document gives future AI agents and developers explicit instructions for working on the CONUS Hail Catastrophe Model. It exists to prevent accidental regressions, memory blowups, documentation drift, and methodology changes that break the model's defensibility.

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
11. Use the Stage 01 MYRORSS manifest to distinguish missing source days from available-source no-hail days.
12. Import grid constants from `scripts/_config.py` rather than redefining them inline.

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
11. Infer MYRORSS source availability from GeoTIFF file size or all-zero raster values.
12. Run `git commit`, `git push`, `git checkout`, or `git merge` from the sandbox bash tool — the sandbox cannot unlink `.git/index.lock`.

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

**Canonical value:** `MAX_CENTROID_KM_DAY = 150.0` per `methodology.md §2` and `_config.py`. Stage 08 was corrected to 150.0 on 2026-05-03. No discrepancy remains.

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

**σ_perturb calibration:** The actual `calibrate_sigma()` method computes monthly CV (coefficient of variation) for events in months March–September, takes the median of those monthly CVs, and clips to [0.10, 0.40]. This is more conservative than a global inter-annual variance estimator. `docs/methodology.md §13` and `docs/uncertainty.md §5.1` now reflect this.

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
- run_pipeline stage selection and dry run;
- **no duplicated grid constants across stage scripts** (test to be written);
- **integration smoke: full pipeline on synthetic 5×5 grid** (test dir to be created).

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
8. **Check for inline grid constants** — stage scripts should import shared values from `_config.py`; treat new inline grid constants as regressions.

---

## 9. Confirmed State After 2026-05-02 Scan

### Files created 2026-05-01 (while pipeline was running)

**Project metadata:**
- `LICENSE`, `CHANGELOG.md`, `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`

**Python/CI infrastructure:**
- `pyproject.toml`, `.pre-commit-config.yaml`, `environment.yml`
- `Dockerfile`, `.dockerignore`
- `.github/workflows/tests.yml` (CI: Python 3.10/3.11/3.12, ruff, mypy, pytest, codecov)
- `.github/ISSUE_TEMPLATE/{bug,methodology,feature}.md`, `.github/PULL_REQUEST_TEMPLATE.md`

**Documentation:**
- `docs/README.md` (documentation index with reading paths)
- `docs/uncertainty.md` (six-category uncertainty budget)

**Code helpers (wired into stage scripts):**
- `scripts/_config.py` — single source of truth for grid constants, paths, physical constants, EVT/RP/stochastic defaults
- `scripts/_logging.py` — `get_logger()` factory

### Confirmed outstanding items

**Code refactors:**
- ✅ `_config.py` import refactor complete: all 15 stage scripts import shared constants/paths.
- ✅ `_logging.py` migration complete: all 15 stage scripts use `get_logger()`.
- ✅ `scripts/_io.py` written and wired for shared `write_geotiff`, `haversine_km`, and `latlon_to_grid` helpers.
- ✅ `MAX_CENTROID_KM_DAY`, `DAMAGE_THRESH_MM`, `MAX_HAIL_MM`, and `RP_YEARS` now come from `_config.py` in the stages that need them.

**Remaining test opportunities:**
- Property-based tests for Stage 13 invariants (hypothesis)
- Performance regression test for Stage 13
- Golden-output regression tests after first full run

**Docs already added from the review pass:**
- `docs/sensitivity.md` — hyperparameter sweep plan
- `docs/benchmarks.md` — published RP comparison framework
- `docs/FAQ.md`
- `docs/vulnerability_derivation.md`
- `docs/methodology.md §0` notation glossary

**Science / methodology gaps to close:**
- `docs/methodology.md §13`: keep σ_perturb description aligned with actual code (monthly CV, not inter-annual variance)
- Topographic correction coefficient (0.25) uncited
- GPD threshold scoring weight rationale not documented
- Source-homogeneity KS test (Stage 05, post-run)
- Event independence diagnostic (Stage 08, post-run)

**Deferred (needs first-run outputs):**
- Regression / golden-output tests
- Bootstrap CIs on Stage 09 RP estimates

---

## 10. Compact Project Context

```text
CONUS Hail Cat Model v2.1 is a radar-first hail hazard model on a 0.05° CONUS grid.
It uses MYRORSS, GridRad, MRMS, ERA5, and SPC validation.
15-stage Python pipeline. Run via run_pipeline.py.
SPC reports are validation only — never a hazard input.
Stage 08 builds a sparse event catalog (event_peaks.npz: rows/cols/vals per event).
Stage 13 must remain sparse-safe — no dense event cubes.
Stage 05 must work with --skip-ml.
Stage 01 produces manifest_stage01_myrorss.csv — use it for source QA.
scripts/_config.py = single source of truth for constants and is imported by all stage scripts.
scripts/_logging.py = get_logger() factory wired into all stage scripts.
OPEN DOC WATCH: methodology.md §13 and uncertainty.md §5.1 document monthly CV Mar–Sep for σ_perturb; keep them aligned with code if Stage 13 changes.
First full run started 2026-05-01 via Codex.
Git commits must be run from the user's terminal, not the sandbox.
```
