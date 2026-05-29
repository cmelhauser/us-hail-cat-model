# Session Handoff — CONUS Hail Catastrophe Model v2.2

> Paste this file at the start of a new chat to restore full project context.
> Last updated: 2026-05-28 (**v2.2.0** convective-day migration: 12 UTC → 12 UTC daily MESH; full re-ingest from Stages 01/02/04c required).

---

## Repository

- **Local:** `/Users/melhauserc/GitHub/us-hail-cat-model`
- **Branch:** **`v2.2.1`** — active development (`origin` only). **`main`** has model **v2.2.0** (convective days).
- **Working tree:** should be kept clean except for intentional documentation or
  code edits in the current session
- **Historical note:** `v2.1` has been merged and is no longer the active
  development branch.

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
04b_download_gridrad.py         04c_fill_gridrad_gap.py
12_apply_conus_mask.py
05_apply_mesh_bias_correction.py 13_generate_stochastic_catalog.py
06_validate_mesh_vs_spc.py      14_build_vulnerability.py
07_build_hail_climo.py          15_render_figures.py

scripts/diagnostics/summarize_mesh_daily_peaks.py  ← optional mesh-era peak CSV/ECDF

scripts/_config.py   ← all grid constants, paths, EVT defaults (wired into all stage scripts)
scripts/_logging.py  ← get_logger() factory (wired into all stage scripts)
scripts/_io.py       ← shared write_geotiff (optional GDAL tags), haversine_km, latlon_to_grid
```

Runner: `python run_pipeline.py [--from N] [--only N] [--skip N,N] [--dry-run] [--validate] [--skip-ml] [--retrain-models]`

---

## Non-Negotiable Rules

1. **Stage 13 must be sparse-safe.** No `(n_events, 520, 1180)` arrays. Translation, scaling, and perturbation operate on `rows, cols, vals` only.
2. **Stage 05 must have a deterministic fallback.** `--skip-ml` must produce complete valid output with no ML artifacts.
3. **SPC = validation only.** Never a hazard input.
4. **`event_peaks.npz`** (rows/cols/vals per event_id) is the authoritative event store.
5. **0.05° grid is fixed.** No other resolutions in v2.1.
6. **Never commit data files.** `.tif`, `.npy`, `.npz`, `.grib2`, `.parquet`, and most `.csv` outputs are gitignored. **Exception:** `data/analysis/mesh_daily_peaks/` (tracked diagnostic summaries).
7. **`scripts/_config.py` is the single source of truth for grid constants.** Never define `NROWS`, `NCOLS`, `DX`, `LAT_MAX`, `LON_MIN` inline in a stage script.
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
| MAX_CENTROID_KM_DAY | 150.0 (canonical; stage 08 corrected to match 2026-05-03) |

---

## Confirmed State After 2026-05-03 Scan

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
- `docs/methodology.md §0` — notation glossary added 2026-05-03
- All other docs (technical_documentation, data_dictionary, reproduce, ai_instructions, project_memory, literature_review, executive_summary, explainer, migration_plan, sensitivity, benchmarks, FAQ, vulnerability_derivation)

**Code helpers (on disk and wired into stage scripts):**
- `scripts/_config.py` — single source of truth; **15/15 stage scripts import from it**
- `scripts/_logging.py` — `get_logger()` factory; **15/15 stage scripts import from it**
- `scripts/_io.py` — `write_geotiff`, `haversine_km`, `latlon_to_grid`; imported by stage scripts where needed

**Tests:** 28 pytest files cover all 15 stages (test_01 through test_15, test_run_pipeline, test_stage\*); integration smoke test and no-dup-constants test written. GitHub Actions is green on Python 3.10, 3.11, and 3.12 at commit `c0b35b8`.

**README.md** — professional rewrite: Python badge corrected to 3.10+, Mermaid removed, pipeline table with exact filenames

### What's NOT done ❌

**Critical code refactors:**
- ✅ `_config.py` import refactor complete across all 15 stage scripts.
- ✅ `_logging.py` migration complete across all 15 stage scripts.
- ✅ `scripts/_io.py` shared helpers are wired where needed.

**Missing code:**
- GeoTIFF provenance metadata tags (REVIEW §C.7)
- Retry/backoff on download stages 01, 02, 03, 04a, 04b (REVIEW §C.6)
- Source-homogeneity KS test in Stage 05 (REVIEW §E.6)
- Event independence diagnostic (index of dispersion) in Stage 08 (REVIEW §E.4)
- Spatial dependence diagnostic (extremogram) in Stage 09 (REVIEW §E.5)

**Deferred (needs production run outputs):**
- Regression / golden-output tests
- Bootstrap CIs on Stage 09 RP estimates (`docs/uncertainty.md §3.1`)

---

## Pipeline Run Status (as of 2026-05-20)

**Stage 04c (2026-05-20):** Reflectivity reader fixed (sparse `Reflectivity`, not `Nradecho`; 0–360° lon fix). Bad 2012 gap TIFFs from the old reader were deleted and **04c** restarted with `--with-04b-download --workers 4` (`logs/04c_fill_gridrad_gap.run.log`). Run later hit **disk full** (`[Errno 28]`): process stopped, stale `gridrad/` / `gridrad_severe/` trees under **2013** removed (~35 GB). **Restart** with direct script and **`--workers 2`** (or `1`) — `run_pipeline.py` still defaults to `--workers 4`. Days without gap TIFF after the stop (example): `20130612`, `20130616`, `20130617`.

**Mesh peak diagnostic:** `scripts/diagnostics/summarize_mesh_daily_peaks.py` writes tracked summaries under `data/analysis/mesh_daily_peaks/` (see `docs/data_dictionary.md`).

The Codex-run pipeline on 2026-05-01 ran **Stages 05–15 prematurely** before Stage 01 finished.
All Stages 05–15 output is **placeholder, not production** — built on 31 events from May 2011 only.
Stage 08 validation **explicitly failed**: "Too few events: 31".

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 01 (MYRORSS) | ✅ Complete + QA repaired | 5,023 rasters through 2011-12-31. Earlier 250.0 mm QA repaired 199 files / 3,852 cells; 300.0 mm rescan found 0 remaining issues and validation passed. |
| Stage 02 (MRMS) | ⏳ Running | Detached `screen` session `hail_stage02_mrms`. |
| Stage 03 (SPC) | ✅ Complete | SPC CSV files downloaded. |
| Stage 04a (ERA5) | ❌ Not run | Log file is empty. Must run after Stage 01. |
| Stage 04b/04c (GridRad) | ⏸ Paused (2026-05-20) | **04c** reflectivity fix applied; run stopped for disk cleanup. Restart: `scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2`. Re-delete any gap TIFFs from the old reader before trusting distributions. |
| Stage 05–15 | ⚠️ Placeholder | Ran against 31 May-2011 files only. All outputs invalid for production use. |

**Re-run sequence once Stage 02 finishes:**
```bash
.venv/bin/python run_pipeline.py --only 04a    # ERA5 isotherms
# GridRad gap-fill (prefer --workers 2 on constrained disks; run_pipeline defaults to 4):
.venv/bin/python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2
# Or: run_pipeline.py --only 04c  (always passes --with-04b-download --workers 4)
# Legacy full GridRad archive first: run_pipeline.py --only 04b, then 04c without --with-04b-download.
.venv/bin/python run_pipeline.py --from 05 --skip-ml   # Re-run all remaining stages
# After Stage 13 smoke passes (default n_years=1000), do the full 50k run:
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 1000
.venv/bin/python scripts/13_generate_stochastic_catalog.py --n-years 50000
.venv/bin/python run_pipeline.py --only 14
.venv/bin/python run_pipeline.py --only 15
.venv/bin/python run_pipeline.py --validate
```

---

## Immediate Next Priorities (in order)

1. **Restart Stage 04c** with `--workers 2` after disk cleanup; let Stage 02 (MRMS) finish. Do not re-run Stage 01 unless explicitly requested (`--qa-only` for repair only).
2. **Run Stage 04a** (ERA5 isotherms) if not already complete; confirm CDS licences.
3. **Re-run Stages 05–15** (`--from 05 --skip-ml`) after Stages 02 and 04c complete.
4. **Full 50,000-year stochastic catalog** — re-run Stage 13 after Stage 12 completes.
5. **Regression tests** — freeze golden outputs; add checksum tests.
6. **Bootstrap CIs on Stage 09 RP estimates** — sketch in `docs/uncertainty.md §3.1`.
7. **Rebuild `.venv` to Python 3.10+** — current run venv is Python 3.9.6 (EOL Oct 2025).

**Completed in session 2026-05-02:**
- ✅ `docs/sensitivity.md` — hyperparameter sweep plan
- ✅ `docs/benchmarks.md` — published RP comparison framework
- ✅ `docs/FAQ.md` — common questions
- ✅ `docs/vulnerability_derivation.md` — MDR curve sources and limitations
- ✅ `tests/integration/test_smoke_synthetic.py` — stage 08→13 end-to-end smoke test
- ✅ `tests/test_no_duplicated_constants.py` — constant values vs _config.py
- ✅ `docs/README.md` updated with new documents
- ✅ AI-agent status table updated

**Completed in session 2026-05-03:**
- ✅ `docs/pnas_article_ai_hail_model.md` — comprehensive review and update: v2.1 stage descriptions, missing references (Cintineo 2012, Brown 2015), AI model names corrected, author line filled (Christopher Melhauser, Ph.D., Independent Researcher), Google Scholar URL, repository URL, pipeline stage table rewritten
- ✅ `scripts/08_build_event_catalog.py` — `MAX_CENTROID_KM_DAY` corrected from 100.0 → 150.0 (canonical value per `methodology.md §8.2` and `_config.py`)
- ✅ `tests/test_no_duplicated_constants.py` — MAX_CENTROID xfail converted to passing assertion
- ✅ All stale MAX_CENTROID discrepancy references cleared across AGENTS.md, HANDOFF.md, project_memory.md, ai_instructions.md
- ✅ `docs/methodology.md §0` — notation glossary added
- ✅ Hurricane-model bootstrap document was kept local and must not be committed to this repository.

**Completed in session 2026-05-03 (continued — pipeline audit):**
- ✅ `docs/HANDOFF.md` — corrected false claims about refactor status; added pipeline run status table and re-run sequence

---

## Documentation Quick-Reference

| File | Purpose |
|------|---------|
| `AGENTS.md` | Repo-root orientation for AI agents and new developers |
| `docs/methodology.md` | Scientific assumptions and formulas |
| `docs/technical_documentation.md` | Per-stage implementation notes |
| `docs/data_dictionary.md` | All output file schemas |
| `docs/reproduce.md` | Reproduction guide |
| `docs/RUN_NOTES.md` | Live run status and restart commands |
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
01 → 02 → 03 → 04a → 04c → 05 (--skip-ml) → 06 → 07 → 08 → 09 → 10 → 11 → 11b → 12
→ 13 (--n-years 1000 smoke first) → 13 (full 50k) → 14 → 15
```
