# AI Instructions for Future Work

**CONUS Hail Catastrophe Model v2.4.1**
**Last updated: 2026-08-06 (`v2.4.1`; origin-only remotes; CI on `main` + `v*`;
mandatory `./scripts/quality_gate.sh` before every commit; 100% coverage gates;
see also `docs/RUN_NOTES.md` for live pipeline rebuild status)**

---

## 1. Purpose

This document gives future AI agents and developers explicit instructions for working on the CONUS Hail Catastrophe Model. It exists to prevent accidental regressions, memory blowups, documentation drift, and methodology changes that break the model's defensibility.

**AI collaborator identity:** Credit all AI collaboration under the project
pseudonym **theonlymuffinbot**. That name is an attribution label for AI work
(code, docs, tests, diagnostics, monitoring, manuscript drafting)—not a
separate GitHub repository. Scientific accountability remains with Christopher
Melhauser. Push and open PRs only against `origin`
(`cmelhauser/us-hail-cat-model`); see `docs/GIT_REMOTES.md`.

---

## 2. Always Do

When changing the project:

1. Preserve the 14-stage hazard pipeline (01–14) unless the user explicitly requests a future major-version redesign.
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
13. Prefer the optional `aws/` Fargate adapter for cloud runs rather than rewriting
    stage scripts for S3/EFS; keep stage path assumptions (`data/`, `logs/`) intact.
    Follow `aws/README.md` end-to-end (Secrets Manager JSON field names, ECR push,
    smoke ladder). Do not treat LocalStack Community as proof of Fargate spend safety.
14. Keep **100%** statement coverage on `scripts/` + `run_pipeline.py` and on the
    AWS adapter (`hail_aws` + `run_pipeline_aws.py`). Never lower
    `fail_under` in `pyproject.toml` or CI `--cov-fail-under` without explicit
    user sign-off and a versioned policy change.
15. Before every `git commit`, run `./scripts/quality_gate.sh`, keep
    `AGENTS.md` / `docs/ai_instructions.md` / operator docs synchronized with
    the change, and do not use `--no-verify` unless the user explicitly orders
    it. Push only when CI on `main` / `v*` will stay green.

---

## 3. Never Do

Do not:

1. Build dense `(n_events, 520, 1180)` event cubes in production.
2. Make Stage 05 dependent on optional ML artifacts.
3. Use SPC reports as the primary hazard surface.
4. Change grid constants without a model-version bump.
5. Implement vulnerability or loss modules without explicit hazard-only scope review (future work only; see `docs/methodology.md` §14).
6. Ignore analytical/stochastic divergence.
7. Remove validation outputs to simplify runtime.
8. Replace deterministic logic with black-box-only logic.
9. Change output file names without updating the data dictionary.
10. Assume missing SPC reports mean radar false alarms.
11. Infer MYRORSS source availability from GeoTIFF file size or all-zero raster values.
12. Commit generated data, logs, rendered figures, local bootstrap files, or model artifacts (including diagnostic summaries under `data/analysis/`).
13. Use any Git remote other than **`origin`** (`cmelhauser/us-hail-cat-model`), or open PRs against another repository. Use `git push -u origin HEAD` and `gh pr create --repo cmelhauser/us-hail-cat-model --base main` only. See `docs/GIT_REMOTES.md`.

---

## 4. High-Risk Stages

### Stage 05 — Bias correction and filtering

Must support:

- MESH75 correction;
- GridRad quantile fallback;
- **range-dependent debias** when `range_debias.npz` exists (`--no-range-debias` to disable);
- **GridRad artifact filter** (four passes on GridRad days: isolated speckle, inner-range radial ring, azimuthal annulus, background filament; **fifth pass** spatiotemporal range-ring persistence from a 21-day trailing window; `--no-speckle-filter` to disable);
- optional conditional calibration;
- optional probabilistic filtering;
- deterministic fallback with `--skip-ml`.

After debias or artifact-filter changes: use **`python scripts/rerun_stage05.py`** (or
`run_pipeline.py --only 05 --clean-from 05 --skip-ml --skip-calibration`) to wipe Stages
05–14 outputs and rebuild the corrected archive **in the foreground**. Do not launch Stage 05
via `nohup`/`&` from agent shells — the process dies when the session ends.

After Stage 05 completes: run `radar_artifact_diagnostic.py`, then Stage 06; review the
GridRad−MYRORSS diff map before Stages 07–14.

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

### Stage 11b — DEM preparation

Must ensure:

- NOAA/NCEI ETOPO 2022 source provenance is preserved;
- source GeoTIFF is cached under `data/analysis/topography/source/`;
- `elevation_0.05deg.tif` is finite, nonnegative, and on the canonical grid.

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

### Stage 14 — Figures

Must render diagnostics that expose model risk, including analytical vs stochastic comparison. CONUS raster map PNGs must use `scripts/_mapping.py` (Lambert Conformal projection, admin_0 country and admin_1 US state boundaries).

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
- figure smoke tests (including `tests/test_mapping.py` when cartopy is installed);
- run_pipeline stage selection and dry run;
- **no duplicated grid constants across stage scripts**;
- **integration smoke: full pipeline on synthetic tiny-grid fixtures**.

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

## 9. Confirmed State After 2026-07-30

Current repository state:

- Active branch: **`v2.4.1`** (model **2.4.1**). Sole remote: **`origin`**
  (`cmelhauser/us-hail-cat-model`). AI collaborator pseudonym: **theonlymuffinbot**.
- GitHub Actions CI: Python 3.10/3.11/3.12 unit tests with **100%**
  `scripts`+`run_pipeline` coverage, policy check, dry-run; AWS job at **100%**
  `hail_aws`; integration on push to `main`/`v*` (and PRs targeting those
  branches). Local mandate: `./scripts/quality_gate.sh` before every commit
  (also wired in `.pre-commit-config.yaml`). Lint: `ruff` / `mypy` via pre-commit.
- Stage helper refactor complete: `_config.py`, `_logging.py`, `_io.py`,
  `_mapping.py`, `_radar_geometry.py`, `_gridrad_qc.py`, `_artifact_features.py`.
- **Stage 01 complete** (5,023 convective-day MYRORSS rasters through 2011-12-31;
  sparse-grid coordinate fix).
- **Stages 02–04a / 03 complete**; GridRad gap-era archive under Stage **04c**.
- **Mesh archive:** **9,797** TIFFs (5,023 + 2,714 + 2,060).
- **v2.4.1 rebuild:** from **04c** (native QC) through **14** — see `docs/RUN_NOTES.md`.
- Diagnostic summaries (gitignored; regenerate or load externally):
  `data/analysis/mesh_daily_peaks/`, `data/analysis/hail_day_climatology/`.

### Files created 2026-05-01 (while pipeline was running)

**Project metadata:**
- `LICENSE`, `CHANGELOG.md`, `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`

**Python/CI infrastructure:**
- `pyproject.toml`, `.pre-commit-config.yaml`, `environment.yml`
- `Dockerfile`, `.dockerignore`
- `.github/workflows/tests.yml` (CI: Python 3.10/3.11/3.12, py_compile, pytest, dry-run, codecov; integration on push)
- `.github/ISSUE_TEMPLATE/{bug,methodology,feature}.md`, `.github/PULL_REQUEST_TEMPLATE.md`

**Documentation:**
- `docs/README.md` (documentation index with reading paths)
- `docs/uncertainty.md` (six-category uncertainty budget)

**Code helpers (wired into stage scripts):**
- `scripts/_config.py` — single source of truth for grid constants, paths, physical constants, EVT/RP/stochastic defaults
- `scripts/_logging.py` — `get_logger()` factory

### Confirmed outstanding items

**Code refactors:**
- ✅ `_config.py` import refactor complete: all 14 stage scripts import shared constants/paths.
- ✅ `_logging.py` migration complete: all 14 stage scripts use `get_logger()`.
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
- `docs/methodology.md` §14 (future loss work)
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

**Immediate run priorities (2026-07-08):**
- Monitor Stages 05–14 rebuild (`screen -r hail_from05`; `logs/pipeline_from05.run.log`).
- After Stage 06: `scripts/diagnostics/radar_artifact_diagnostic.py` (refit debias; verify speckle / eastern CONUS).
- After full run: `--validate`; regenerate Stage 14 + `render_pnas_article_figures.py`; freeze manuscript Results/Abstract from `pnas_article_metrics.json`.
- Do not cite pre–eastern-fix (2026-06-30) hazard numbers as final v2.2.2.

**Prior priorities (2026-07-06):**
- Monitor Stages 05–07 rebuild (`logs/pipeline_05_07.run.log`).
- Run `scripts/diagnostics/radar_artifact_diagnostic.py` after Stage 06 to refit debias and verify speckle / diff-map rings.
- Compare stochastic RP maps before/after inner-range radial pass before Stages 08–14.

**Prior priorities (2026-06-27):**
- Confirm Stage 04c `--missing-only` backfill is finished (or accept manifest `missing_source` days).
- Re-run Stages 05–14 with `--skip-ml` against the full dataset.
- Run Stage 13 smoke (`--n-years 1000`) before the full 50,000-year catalog.
- Regenerate mesh-era diagnostic if ingest changes: `scripts/diagnostics/summarize_mesh_daily_peaks.py`.
- Regenerate hail-day climatology after Stage 05: `scripts/diagnostics/hail_day_climatology.py`.
- Regenerate radar artifact diagnostic after Stage 05/06: `scripts/diagnostics/radar_artifact_diagnostic.py`.
- Run literature validation suite after Stages 05–13: `scripts/diagnostics/literature_validation_suite.py` (15 checks; missing inputs warn-and-skip via `_diagnostic_io.py`).

**Stage 04a CDS access note:** Stage 04a needs more than a valid
`~/.cdsapirc`. The Copernicus account used for the token must also accept the
ERA5 monthly pressure-level and single-level dataset licences. If CDS returns
`403 Client Error: Forbidden` with `required licences not accepted`, accept both
dataset licences from the CDS download pages, then retry Stage 04a.

---

## 10. Compact Project Context

```text
CONUS Hail Cat Model v2.2 is a radar-first hail hazard model on a 0.05° CONUS grid.
It uses MYRORSS, GridRad, MRMS, ERA5, and SPC validation.
14-stage Python pipeline. Run via run_pipeline.py.
SPC reports are validation only — never a hazard input.
Stage 08 builds a sparse event catalog (event_peaks.npz: rows/cols/vals per event).
Stage 13 must remain sparse-safe — no dense event cubes.
Stage 05 must work with --skip-ml.
Stage 01/02 manifests (manifest_stage01_myrorss.csv, manifest_stage02_mrms.csv) — use for source QA.
scripts/_config.py = single source of truth for constants and is imported by all stage scripts.
scripts/_logging.py = get_logger() factory wired into all stage scripts.
OPEN DOC WATCH: methodology.md §13 and uncertainty.md §5.1 document monthly CV Mar–Sep for σ_perturb; keep them aligned with code if Stage 13 changes.
First full run started 2026-05-01 via Codex.
Active branch: v2.4.1. Model 2.4.1 (12 UTC → 12 UTC convective days).
Sole remote: origin (cmelhauser/us-hail-cat-model). AI collaborator: theonlymuffinbot.
Stage 01 + 02 + 04c primary ingest complete (9,584 mesh TIFFs). Stages 05–14 are the active blocker.
```
