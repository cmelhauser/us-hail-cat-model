# Changelog

All notable changes to the CONUS Hail Catastrophe Model are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [2.2.1] — 2026-05-28

### Added

- **`docs/GIT_REMOTES.md`** and **`scripts/setup_git_remotes.sh`:** document and enforce push/PR to `origin` (`cmelhauser`) only, not `upstream`.
- Agent/contributor rules in `AGENTS.md`, `CONTRIBUTING.md`, `docs/ai_instructions.md`.

### Changed

- Operational docs synced for **v2.2.1** dev branch vs **2.2.0** model on `main`.
- **`docs/literature_review.md` §3.6:** literature basis for 12 UTC → 12 UTC convective-day aggregation.
- **`docs/technical_documentation.md`**, **`docs/UPGRADE_NOTES.md`**, handoff/uncertainty/data-dictionary headers aligned to v2.2.

## [2.2.0] — 2026-05-28

**Breaking methodology change.** Daily MESH rasters now use **12 UTC → 12 UTC convective days** (label = date at window start). v2.1 calendar-UTC (00Z–00Z) production GeoTIFFs are not comparable; re-run Stages **01**, **02**, and **04c** (and downstream **05–15**) on a clean `mesh_0.05deg/` tree.

### Changed

- **`MODEL_VERSION`:** `2.2.0`; **`CONVECTIVE_DAY_START_HOUR_UTC`:** `12` in `scripts/_config.py`.
- **Stages 01, 02:** List timesteps from two UTC calendar archive prefixes, filter by observation time, write `mesh_YYYYMMDD.tif` with GDAL tag `CONVECTIVE_WINDOW_UTC`.
- **Stages 04b, 04c:** Download and process convective days; stage GridRad under `by_convective_day/YYYYMMDD/`; filter timesteps by parsed filename UTC.
- **Documentation:** Convective-day definition in `docs/methodology.md` §2.6, `docs/data_dictionary.md`, `AGENTS.md`, `docs/FAQ.md`, `docs/pnas_article_ai_hail_model.md`, and related pipeline docs.

### Added

- **`scripts/_io.py`:** Convective-day helpers (`convective_day_window_utc`, `observation_utc_to_convective_day`, `parse_observation_utc_from_name`, `mesh_path_for_convective_day`, `filter_keys_for_convective_day`, …).
- **`tests/test_convective_day.py`:** Unit tests for assignment and filtering edge cases.

---

## [2.1.x] — 2026-05-20

### Fixed

- **Stage 04c:** GridRad gap-fill now reads **sparse `Reflectivity(Index)`** (reconstructed to 3-D dBZ) instead of treating **`Nradecho`** as reflectivity. The previous reader produced all-zero daily rasters on most **hourly-only** days.
- **Stage 04c:** Normalize GridRad longitudes from 0–360° before CONUS masking and 0.05° indexing.
- **Stage 04c:** Register Stage **04b** in `sys.modules` before `exec_module` so `ProcessPoolExecutor` workers load the downloader without dataclass errors.
- **Stage 08:** `MAX_CENTROID_KM_DAY` corrected from `100.0` to `150.0` to match
  `scripts/_config.py` and `docs/methodology.md §8.2`. Canonical value is 150 km/day.
- **`tests/test_no_duplicated_constants.py`:** Converted `MAX_CENTROID_KM_DAY` xfail
  to a normal passing assertion.
- **`CITATION.cff`:** Repository URL corrected (`melhauserc` → `cmelhauser`);
  Cintineo et al. (2012) reference title, author initial, and page range corrected.

### Changed

- **Documentation:** Era boundaries (GridRad through **2020-10-13**, MRMS from **2020-10-14**), Stage **04c** sparse reflectivity ingestion, disk/workers guidance, and run status synced across `AGENTS.md`, `docs/HANDOFF.md`, `docs/RUN_NOTES.md`, `docs/project_memory.md`, `docs/technical_documentation.md`, `docs/reproduce.md`, `docs/FAQ.md`, and related methodology/data docs.
- **`.gitignore`:** Allow versioned `data/analysis/mesh_daily_peaks/` only; all other `data/**` remains ignored.

### Added

- **Stage 02:** `--workers N` (default 8) uses parallel threads per calendar day
  for S3 fetch plus GRIB decode; `--workers 1` restores fully sequential I/O.
  Thread-local boto3 clients avoid sharing one client across threads.
- **Stage 04c:** `--workers N` (default 4) uses parallel worker processes across
  calendar days for GridRad gap-fill. This avoids the GIL and isolates netCDF
  reads; `--workers 1` restores sequential execution.
- **Stage 04b/04c:** GridRad acquisition is now explicit. Stage 04b downloads
  GridRad inputs from NCAR RDA/GDEX, and Stage 04c performs the gap-fill compute.
- **Stage 01:** `--workers N` (default 8) uses parallel threads per calendar day
  for S3 fetch plus NetCDF decode + sparse parse; `--workers 1` restores fully
  sequential I/O. Thread-local boto3 clients avoid sharing one client across threads.
- **`scripts/_io.py`:** Shared I/O helpers (`write_geotiff`, `haversine_km`,
  `latlon_to_grid`) extracted from stage scripts and wired into all stages that need them.
- **Stage 04c:** GDAL diagnostic tags on gap-fill GeoTIFFs (`MAX_MESH75_MM`, `ACTIVE_CELLS`, `SOURCE`, `DATE`) and per-day progress logging with peak hail.
- **`docs/pnas_article_ai_hail_model.md`:** GridRad era dates, 04b/04c split, sparse Reflectivity SHI ingestion, AI audit examples.
- **`scripts/diagnostics/summarize_mesh_daily_peaks.py`:** Daily mesh peak CSV, percentiles, and ECDF under `data/analysis/mesh_daily_peaks/`.
- **Stage refactor:** All 15 stage scripts now import shared constants from `_config.py`
  and shared logging from `_logging.py`.
- **`docs/methodology.md §0`:** Notation glossary (grid, hazard, occurrence, EVT,
  stochastic, topographic correction, vulnerability, abbreviations).
- **`docs/pnas_article_ai_hail_model.md`:** Author line (Christopher Melhauser,
  Ph.D., Independent Researcher), Google Scholar URL, repository URL, AI model
  identifiers, v2.1 stage descriptions, two missing references, pipeline stage
  table rewritten, benchmark discussion paragraph added.

---

## [2.1.0] — 2026-05-01

**Hardening release.** Same 15-stage pipeline and 0.05° grid as v2.0. No
methodology redesign; all changes improve defensibility, testability, and
run-readiness.

### Added

- **Stage 05**: Optional conditional ML calibration (`gridrad_cqm_model.pkl`)
  with quantile-mapping fallback when `--skip-ml` is set or the artifact is
  absent.
- **Stage 05**: Optional probabilistic environmental filter
  (`hail_filter_model.pkl`) replacing the previous hard-threshold-only filter.
  Hard thresholds remain as a safety floor.
- **Stage 05**: `--skip-ml` and `--retrain-models` CLI flags for reproducible
  deterministic runs and in-situ retraining.
- **Stage 08**: Centroid displacement check (≤ 150 km/day) and intensity jump
  check (≤ 3×) for event merge decisions.
- **Stage 08**: `merge_quality_flag` column in event catalog.
- **Stage 09**: Automated threshold selection diagnostics →
  `threshold_selection.csv` (columns: `n_exc`, `ξ`, `σ`, `MRL`, `stability`,
  `GOF`).
- **Stage 12**: Freezing-level-aware topographic correction factor (bounded
  1.0–1.25 with ERA5 FL; 1.0–1.20 fallback).
- **Stage 13**: Fully sparse-safe stochastic simulation. No dense
  `(n_events, 520, 1180)` arrays anywhere in the catalog generation loop.
- **Stage 01**: MYRORSS source-coverage manifest
  (`manifest_stage01_myrorss.csv`) distinguishing missing source days from
  available-source no-hail days.
- Expanded pytest suite with stage-level unit tests for all 15 stages.
- `docs/ai_instructions.md` — operating instructions for AI-assisted development.
- `docs/project_memory.md` — canonical project state snapshot.
- `docs/migration_plan.md` — v1→v2→v2.1→v3 evolution roadmap.
- `docs/executive_summary.md` — 5-minute overview for non-technical readers.
- `docs/explainer.md` — plain-language explanation of model methodology.
- `docs/UPGRADE_NOTES.md` — v2.0→v2.1 migration notes.
- `docs/PR_v1_to_v2.1.md` — reviewer-facing upstream PR narrative for
  the v1.0→v2.0→v2.1 arc.
- `docs/REVIEW_PRE_RUN.md` — pre-execution audit artifact.
- `run_pipeline.py`: `--from N`, `--only N`, `--skip`, `--dry-run`,
  `--validate`, `--skip-ml`, `--retrain-models` CLI.

### Changed

- **Stage 09**: Default GPD threshold selection now uses automated diagnostics
  in addition to MRL plot inspection.
- **Stage 12**: Topographic correction coefficient is now freezing-level-aware
  (previously fixed 5%/km).
- **Stage 13**: Sparse event storage (`event_peaks.npz`) is now authoritative;
  dense event reconstruction is prohibited.
- All documentation synchronized to v2.1.
- **Stage 01**: MYRORSS ingestion accepts both plain `.netcdf` and gzipped
  `.netcdf.gz` archive objects.

### Fixed

- Grid constant duplication identified as a known issue; centralization to
  `scripts/_config.py` is a v2.1 deliverable (see Added below).
- `requirements.txt` header corrected from v2.0 to v2.1.

---

## [2.0.0] — 2025-Q4

**Radar-first redesign.** Complete rewrite from v1.0 (SPC-based) to v2.0
(radar-based).

### Added

- Three-source radar pipeline: MYRORSS (1998–2011) → GridRad (2012–2019) →
  MRMS (2020–present).
- MESH75 hazard metric (Murillo & Homeyer 2021 corrected formula).
- ERA5 monthly 0°C / −20°C isotherms for GridRad SHI computation.
- Regional GPD ξ pooling via L-moments (K-means, k=6 regions).
- Dual return-period products: analytical (CDF) + empirical (stochastic).
- Stochastic event-resampling catalog (50,000 years, calibrated σ perturbation,
  ±3-cell spatial translation).
- Divergence flag between analytical and empirical RP products.
- 5-class lognormal vulnerability curves (placeholder, literature-based).
- Stage 08 event grouping by spatial overlap, temporal gap, and duration.
- Stage 09 regional EVT fitting with GPD tail + lognormal body.
- Stage 10 spatially-pooled CDF smoothing (150 km radius, 75 km decay).
- Stage 11 occurrence probability rasters at 8 thresholds.
- Stage 12 CONUS masking + topographic correction.
- Stage 15 figure rendering with analytical vs stochastic comparison.

### Removed

- SPC-based hazard estimation from v1.0 (SPC retained for validation only).
- Population trend model from v1.0.

---

## [1.0.0] — 2025-Q2

**Initial release.** SPC-report-based hail hazard model with population trend
adjustment. Replaced by v2.0.

---

[2.1.0]: https://github.com/melhauserc/us-hail-cat-model/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/melhauserc/us-hail-cat-model/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/melhauserc/us-hail-cat-model/releases/tag/v1.0.0
