# Session Handoff — CONUS Hail Catastrophe Model v2.1

> Paste this file at the start of a new chat to restore full project context.
> Last updated: 2026-05-02 (post full-repo scan, pipeline running via Codex).

---

## Repository

- **Local:** `/Users/melhauserc/GitHub/us-hail-cat-model`
- **Branch:** `v2.1` (active dev) — synced with `main` at commit `e4413dc`
- **Working tree:** clean (as of 2026-05-02 scan)

---

## What This Project Is

A radar-based probabilistic hail hazard model for the Continental United States.
15-stage Python pipeline on a fixed 0.05° CONUS grid (520 × 1180 cells). Ingests
NOAA MESH data from three sources, fits regional GPD extreme-value distributions
via L-moments, and generates a 50,000-year stochastic event catalog. **Hazard only
— no exposure, no financial loss, no claims-calibrated vulnerability.**

---

## Architecture — Four Phases

| Phase | Stages | Role |
|-------|--------|------|
| Ingestion & Calibration | 01–05 | MYRORSS / GridRad / MRMS ingestion, ERA5 isotherms, bias correction, ML filtering |
| Event Catalog | 06–08 | SPC validation, climatology, sparse event grouping |
| EVT Fitting | 09–11 | Regional GPD (L-moments), spatial smoothing, exceedance probabilities |
| Hazard Output | 12–15 | CONUS mask, topographic correction, 50k-yr stochastic catalog, vulnerability placeholder, figures |

---

## Pipeline Scripts (exact filenames)

```
01_download_myrorss.py          08_build_event_catalog.py
02_download_mrms_mesh.py        09_fit_cdf_regional.py
03_download_spc.py              10_build_smooth_cdf.py
04a_download_era5_isotherms.py  11_build_occurrence_probs.py
04b_fill_gridrad_gap.py         12_apply_conus_mask.py
05_apply_mesh_bias_correction.py 13_generate_stochastic_catalog.py
06_validate_mesh_vs_spc.py      14_build_vulnerability.py
07_build_hail_climo.py          15_render_figures.py

scripts/_config.py   ← all grid constants, paths, EVT defaults (NOT yet imported by stage scripts)
scripts/_logging.py  ← get_logger() factory (NOT yet wired into stage scripts)
```

Runner: `python run_pipeline.py [--from N] [--only N] [--skip N,N] [--dry-run] [--validate] [--skip-ml] [--retrain-models]`

---

## Non-Negotiable Rules

1. **Stage 13 must be sparse-safe.** No `(n_events, 520, 1180)` arrays. Translation, scaling, and perturbation operate on `rows, cols, vals` only.
2. **Stage 05 must have a deterministic fallback.** `--skip-ml` must produce complete valid output with no ML artifacts.
3. **SPC = validation only.** Never a hazard input.
4. **`event_peaks.npz`** (rows/cols/vals per event_id) is the authoritative event store.
5. **0.05° grid is fixed.** No other resolutions in v2.1.
6. **Never commit data files.** `.tif`, `.npy`, `.npz`, `.grib2`, `.parquet`, `.csv` outputs are gitignored.
7. **`scripts/_config.py` is the single source of truth for grid constants.** Once the refactor is applied, never define `NROWS`, `NCOLS`, `DX`, `LAT_MAX`, `LON_MIN` inline in a stage script.
8. **Stage 01 manifest is authoritative** for distinguishing missing-source days from true no-hail days. Do not infer source availability from GeoTIFF values alone.

---

## Key Constants (all in `scripts/_config.py`)

| Constant | Value |
|----------|-------|
| NROWS | 520 |
| NCOLS | 1180 |
| DX | 0.05° |
| LAT_MAX | 50.005°N |
| LAT_MIN | 23.995°N |
| LON_MIN | −125.005°W |
| LON_MAX | −65.995°W |
| CRS | EPSG:4326 |
| MESH75 formula | 15.096 × SHI^0.206 (Murillo & Homeyer 2021) |
| N_SIM_YEARS | 50,000 |
| TRANSLATE_CELLS | ±3 |
| POOL_RADIUS_KM | 150 km (75 km decay) |
| N_REGIONS_DEFAULT | 6 (K-means) |
| RNG_SEED | 42 |
| MAX_CENTROID_KM_DAY | 150.0 ← _config; **stage 08 script has 100.0 — mismatch to fix** |

---

## Git Rule for This Repo

**Never run `git commit`, `git push`, `git checkout`, or `git merge` from the sandbox bash tool.** The sandbox creates `.git/index.lock` during git operations but cannot unlink it (Operation not permitted), which blocks all subsequent git commands. Prepare the exact command sequence and ask the user to run it in their terminal. `git status` and `git add -A` are safe for verification only.

---

## Confirmed State After 2026-05-02 Full-Repo Scan

### What's done ✅

**Project metadata / infrastructure:**
- `LICENSE`, `CHANGELOG.md`, `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- `pyproject.toml`, `.pre-commit-config.yaml`, `environment.yml`
- `Dockerfile`, `.dockerignore`
- `.github/workflows/tests.yml` (CI: Python 3.10/3.11/3.12, ruff, mypy, pytest, codecov)
- `.github/ISSUE_TEMPLATE/{bug,methodology,feature}.md`, `.github/PULL_REQUEST_TEMPLATE.md`

**Docs written:**
- `docs/README.md` (documentation index)
- `docs/uncertainty.md` (six-category uncertainty budget)
- All other docs (methodology, technical_documentation, data_dictionary, reproduce, ai_instructions, project_memory, literature_review, executive_summary, explainer, migration_plan)

**Code helpers (on disk, not yet wired in):**
- `scripts/_config.py` — single source of truth for all grid constants, paths, physical/EVT/stochastic defaults
- `scripts/_logging.py` — `get_logger()` factory

**Tests:** 28 test files cover all 15 stages (test_01 through test_15, test_run_pipeline, test_stage\*)

**README.md** — professional rewrite: Python badge corrected to 3.10+, Mermaid removed, pipeline table with exact filenames

### What's NOT done (confirmed by grep scan) ❌

**Critical code refactors (safe to do post-run):**
- `_config.py` import refactor: **0 of 15 stage scripts** import from `_config`. Scripts with inline grid constants: 01, 02, 04b, 05, 06, 07, 08, 09, 10, 11, 12, 13, 15 (13 scripts). Scripts 03, 04a, 14 have no grid constants and need no refactor.
- `_logging.py` migration: **0 of 15 stage scripts** import from `_logging`. All 15 have print-based `def log(msg)`.
- Also inline in stage scripts: `RP_YEARS` (09, 10, 13, 15); `DAMAGE_THRESH_MM` (08, 13); `MAX_HAIL_MM` (13)
- **Known discrepancy: stage 08 `MAX_CENTROID_KM_DAY = 100.0` vs `_config.py` value of `150.0`** — fix this during the _config refactor

**Missing docs (now resolved):**
- ✅ `docs/sensitivity.md` — hyperparameter sweep plan (stages 08/09/10/12/13; sweep ranges, cliff risks, execution schedule)
- ✅ `docs/benchmarks.md` — published RP comparison framework (Cintineo 2012, Murillo 2021, Wendt & Jirak 2021; regional sanity checks)
- ✅ `docs/FAQ.md` — common questions on data, pipeline, methodology, uncertainty, errors
- ✅ `docs/vulnerability_derivation.md` — MDR curve sources (Brown 2015, IBHS), limitations, calibration roadmap
- ❌ Notation glossary `docs/methodology.md §0` — (REVIEW §E.11) — still pending

**Missing code:**
- Run manifest in `run_pipeline.py` — user says in progress
- ✅ `tests/integration/test_smoke_synthetic.py` — written (stage 08→13 end-to-end, 50-year synthetic smoke)
- ✅ `tests/test_no_duplicated_constants.py` — written (values vs _config.py; MAX_CENTROID_KM_DAY tracked as xfail)
- GeoTIFF provenance metadata tags (REVIEW §C.7)
- Retry/backoff on download stages 01, 02, 03, 04a, 04b (REVIEW §C.6)
- `scripts/_io.py` — shared write_geotiff/haversine/latlon_to_grid helpers
- Source-homogeneity KS test in Stage 05 (REVIEW §E.6)
- Event independence diagnostic (index of dispersion) in Stage 08 (REVIEW §E.4)
- Spatial dependence diagnostic (extremogram) in Stage 09 (REVIEW §E.5)
- σ_perturb calibration documented in methodology.md (actual method: monthly CV March–September, clipped [0.10, 0.40])

**Deferred (needs first-run outputs):**
- Regression / golden-output tests
- Bootstrap CIs on Stage 09 RP estimates (`docs/uncertainty.md §3.1`)

---

## Immediate Next Priorities (in order)

1. **`_config.py` import refactor** — replace inline constants in 13 stage scripts. **Fix `MAX_CENTROID_KM_DAY` discrepancy (stage 08 = 100.0, _config = 150.0)** — decide canonical value before refactor.
2. **`_logging.py` migration** — replace `def log(msg)` in all 15 stage scripts with `get_logger()`.
3. **`scripts/_io.py`** — consolidate duplicated `write_geotiff`, `haversine`, `latlon_to_grid` helpers.
4. **Review Stage 15 figures** once Codex run completes — analytical vs stochastic RP comparison.
5. **Regression tests** — freeze golden outputs; add checksum tests.
6. **Bootstrap CIs on Stage 09 RP estimates** — sketch in `docs/uncertainty.md §3.1`.
7. **Notation glossary** — `docs/methodology.md §0` (REVIEW §E.11).
8. **Rebuild `.venv` to Python 3.10+** — current venv is Python 3.9.6 (EOL Oct 2025).

**Completed in this session (2026-05-02):**
- ✅ `docs/sensitivity.md` — hyperparameter sweep plan
- ✅ `docs/benchmarks.md` — published RP comparison framework
- ✅ `docs/FAQ.md` — common questions
- ✅ `docs/vulnerability_derivation.md` — MDR curve sources and limitations
- ✅ `tests/integration/test_smoke_synthetic.py` — stage 08→13 end-to-end smoke test
- ✅ `tests/test_no_duplicated_constants.py` — constant values vs _config.py
- ✅ `docs/README.md` updated with new documents
- ✅ `SKILL.md` status table updated

---

## Documentation Quick-Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | Repo-root orientation for AI agents and new developers |
| `docs/methodology.md` | Scientific assumptions and formulas |
| `docs/technical_documentation.md` | Per-stage implementation notes |
| `docs/data_dictionary.md` | All output file schemas |
| `docs/reproduce.md` | Reproduction guide |
| `docs/uncertainty.md` | Six-category uncertainty budget |
| `docs/ai_instructions.md` | AI operating instructions |
| `docs/project_memory.md` | Canonical project state (this file's parent) |
| `docs/REVIEW_PRE_RUN.md` | Pre-execution audit checklist |
| `docs/REVIEW_2026-05-01.md` | Comprehensive post-v2.1 review, action plan with ✅/⏳ status |

---

## Pre-Run Commands

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

Recommended first-run stage order:
```
01 → 02 → 03 → 04a → 04b → 05 (--skip-ml) → 06 → 07 → 08 → 09 → 10 → 11 → 12
→ 13 (--n-years 1000 smoke first) → 13 (full 50k) → 14 → 15
```
