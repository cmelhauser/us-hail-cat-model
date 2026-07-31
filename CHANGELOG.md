# Changelog

All notable changes to the CONUS Hail Catastrophe Model are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **AWS GridRad day fan-out:** `workflow.gridrad_fanout` in `aws/config/pipeline.yaml`
  runs one Stage **04c** Fargate task per convective day (default 2 vCPU / 16 GB /
  50 GiB, `max_concurrent: 10`), with CLI overrides
  (`--gridrad-from-date` / `--until-date` / `--max-concurrent` / `--no-gridrad-fanout`)
  and a post-pass `--manifest-only` rebuild. See `aws/README.md`.
- **Stage 04c merge-safe `gridrad_days.txt`:** flock union-merge and window rebuild on
  `--manifest-only` so parallel day tasks do not truncate the Stage 05 era label file.

### Changed

- **Origin-only remotes:** `docs/GIT_REMOTES.md`, `scripts/setup_git_remotes.sh`,
  `AGENTS.md`, `CONTRIBUTING.md`, and related docs now treat
  `cmelhauser/us-hail-cat-model` as the sole remote. Stale non-origin remotes
  are removed by the setup script.
- **AI collaborator attribution:** **theonlymuffinbot** is documented as the
  project pseudonym for all AI collaboration (not a separate repository) in
  `LICENSE`, `README.md`, `CITATION.cff`, `.zenodo.json`, `AGENTS.md`,
  `CONTRIBUTING.md`, `docs/ai_instructions.md`, and PNAS AI disclosures.
- **Development readiness sync (2026-07-30):** README/CITATION/Zenodo/DATA_AVAILABILITY
  and orientation docs aligned to **v2.3.0**; public URLs corrected to
  **cmelhauser**; CI triggers document `main` + `v*`; status tables no longer
  claim `main` is stuck on 2.2.1.
- **AWS LocalStack/E2E:** LocalStack Community 4.x gates ECS (Pro); add
  `pipeline.localstack.yaml`, laptop-monitor E2E stubs for `downloads-only` and
  `full`, and LocalStack-friendly exitCode handling in `ecs_client`.

### Added

- **AWS Fargate adapter (`aws/`)** — optional cloud runner that does **not** modify stage
  scripts. Parallel ECS Fargate tasks for Stages **01** (MYRORSS), **02** (MRMS), and
  **04c** (GridRad), then a finalize task for **03 / 04a / 05–14**, with shared state on
  EFS. Includes:
  - `aws/config/pipeline.yaml` — single parameter file for CDK deploy and runtime
  - `aws/cdk/` — Python CDK stack (ECS, EFS, ECR, IAM, CloudWatch)
  - `aws/run_pipeline_aws.py` — local boto3 orchestrator (`full`, `downloads-only`,
    `finalize`, `dry-run`)
  - `aws/hail_aws/` — typed YAML loader, ECS client, workflow planner
  - LocalStack Community **`4.14.0`** compose file + `aws/tests` (100% coverage gate on
    `hail_aws` + CLI)
  - Design/plan: `docs/superpowers/specs/2026-07-17-aws-fargate-adapter-design.md`,
    `docs/superpowers/plans/2026-07-17-aws-fargate-adapter.md`
  - Install extras: `pip install -e ".[aws]"` (PyYAML, boto3, aws-cdk-lib)

## [2.3.0] — 2026-07-09

### Added

- **`scripts/_artifact_features.py`** — geometry-aware feature builder (range, azimuth,
  local texture, era) for optional artifact ML.
- **`scripts/train_artifact_classifier.py`** — trains `artifact_classifier.pkl` from
  Stage **06** SPC pairs (severe = positive; high-MESH no-report = negative).
- **`docs/radar_artifact_ml_plan.md`** — Tier 0–2 roadmap and ablation metrics.
- **Literature check `rp_ring_energy`** — range-profile CV on 100-yr analytical RP map.

### Changed

- **Stage 05** — optional `artifact_classifier.pkl` down-weights residual artifact cells
  after rule passes (`--skip-ml` bypasses; deterministic fallback when missing).
- **`--retrain-models`** on Stage **05** invokes `train_artifact_classifier.py`.
- **`MODEL_VERSION`** → **2.3.0** (full rebuild: **04c** → **14** after Tier 0 + train).

---

## [2.2.3] — 2026-07-09

### Added

- **`scripts/_gridrad_qc.py`** — GridRad-native echo-frequency filter (`Necho/Nobs < 0.6`)
  and 4-step clutter removal analogue applied in Stage **04c** before SHI (disable with
  `--no-gridrad-native-qc`).

### Changed

- **Stage 05** — site-specific WSR-88D remediation **on by default** (`site_remediation=True`).
- **Azimuthal ring pass** — uses **10 km** range bins (`RADIAL_RING_BIN_EDGES_KM`) matching
  radial and persistence passes (was coarser `DEFAULT_RANGE_BIN_EDGES_KM`).
- **`MODEL_VERSION`** → **2.2.3** (requires Stage **04c** re-run for GridRad QC + Stage **05+**
  rebuild for remediation/azimuth fixes).

---

## [2.2.2] — 2026-07-08

### Added

- **Stage 01 MYRORSS sparse-grid coordinate fix** — `pixel_x`/`pixel_y` were swapped vs
  WDSS-II `SparseLatLonGrid` convention (`pixel_x` = row/lat, `pixel_y` = col/lon). The bug
  truncated MYRORSS hail to west of ~−96°W; full CONUS re-ingest required.
- **Stage 05 spatiotemporal range-ring persistence (pass 5)** —
  `remove_persistent_range_artifacts()` uses a **21-day** trailing window of pre-filter
  GridRad rasters; chronically active (site, range) annuli are zeroed while burst cells
  and coordinated storm annuli are retained. Replaces site-specific remediation as the
  default fifth pass (`site_remediation=False`).
- **Lambert map rendering** — `scripts/_mapping.py` uses `imshow` + Plate Carrée cell-edge
  extent on geo axes; diagnostic multi-panel maps drop `sharex`/`sharey`.
- **Per-source mean annual max maps** — fixed mean-annual-max statistic in
  `radar_artifact_diagnostic.py` (`_mean_annual_max_from_year_peaks`).

### Changed

- **GridRad artifact filter** — five passes: speckle → radial ring → azimuthal → filament →
  **spatiotemporal persistence** (site-specific remediation remains optional, off by default).

### Operations (2026-07-08)

- Stage 01 MYRORSS re-ingest **complete** (5,023/5,023; validation passed).
- Pre-Stage 05 geotransform / eastern-CONUS QA passed.
- Stages **05–14** rebuild launched (`run_pipeline.py --from 05 --skip-ml`, screen
  `hail_from05`) after `clean_from_stage("05")`. Prior hazard products superseded.

- **`scripts/_mapping.py`:** shared Lambert Conformal CONUS map helpers (central lon
  −96°, lat 39°, standard parallels 33°/45°); Natural Earth **admin_0** country
  outlines and **admin_1** US state lines. Stage 14 and diagnostic map PNGs
  (`radar_artifact_diagnostic`, `hail_day_climatology`, `render_pnas_article_figures`)
  now use these helpers instead of ad hoc plate-carée `imshow` plots.
- **`tests/test_mapping.py`:** projection, extent, raster plotting, and save-map smoke tests.

### Added

- **Site-specific WSR-88D remediation (pass 5)** — nine radars flagged on the GridRad−MYRORSS
  diff map (KBLX, KDOX, KEMX, KGRR, KGWX, KHPX, KILN, KLRX, KTLX) receive stricter
  artifact filtering and a polar spoke test in `remove_flagged_site_artifacts()`.

### Changed

- **Radial range-ring pass (inner-range baseline)** — `remove_radial_range_rings()` now
  compares outer bins (≥50 km) to an inner-range baseline (≤75 km) in addition to ±1/±2
  neighbor bins, catching wide mid-range plateaus (Oklahoma / Plains overlap). Detection
  thresholds tightened to **1.12×** / **1.18×** (was 1.20× / 1.25×); cell margin **5 mm**
  (was 8 mm).

### Added

- **Stage 05 radial range-ring pass** — `remove_radial_range_rings()` in `scripts/_radar_geometry.py`
  compares each (nearest WSR-88D site, 10 km range bin) to adjacent radial bins and an
  inner-range baseline; targets uniform NEXRAD annuli that isolated-speckle and azimuthal
  passes miss. GridRad filter chain is four passes (speckle → radial ring → azimuthal →
  filament).
- **Pipeline cleanup and blocking Stage 05 rerun** — `scripts/_pipeline_cleanup.py` removes
  generated outputs from a given stage onward; `scripts/rerun_stage05.py` waits for any running
  Stage 05, cleans 05+, and reruns Stage 05 in the foreground. `run_pipeline.py` adds
  `--clean-from` and runs stage scripts from repo root (fixes import paths).
- **Stage 05 PID file** — `logs/stage05.pid` while Stage 05 is running (for wait/detection).

## [2.2.2] — 2026-07-05

### Changed

- **Stage 14 figures** — renamed `scripts/15_render_figures.py` → `scripts/14_render_figures.py`;
  pipeline stage ID **15 → 14** (vulnerability stage removed in prior release; figures now occupy
  stage 14). Updated `run_pipeline.py`, tests, and documentation references.

### Removed

- **Stage 14 vulnerability** — deleted `scripts/14_build_vulnerability.py`, related tests, and
  `docs/vulnerability_derivation.md`. Repository is hazard-only; exposure/MDR/loss are future work
  (`docs/methodology.md` §14, PNAS manuscript).

### Added

- **`scripts/_radar_geometry.py`:** CONUS WSR-88D site geometry (~140 sites), nearest-radar
  distance grid, SPC-collocated range-dependent debias fit/apply, GridRad speckle spike removal.
- **`scripts/diagnostics/radar_artifact_diagnostic.py`:** speckle scores, range-binned annual
  maxima, GridRad−MYRORSS difference maps, and `range_debias.npz` from Stage 06 pairs.
- **Stage 05 range debias:** applies `data/analysis/calibration/range_debias.npz` when present
  (`--no-range-debias` to disable); per-era factors normalized at 125 km from nearest radar.
- **Stage 05 GridRad speckle filter:** zeros isolated spikes (>2.5× local 3×3 median;
  `--no-speckle-filter` to disable).
- **`docs/DATA_AVAILABILITY.md`:** Zenodo/ORCID archival plan, publication-bundle tarball
  layout, and DOI placeholders (ORCID `0009-0000-4234-5419`; code DOI via GitHub Release).
- **`.zenodo.json`:** Zenodo metadata for GitHub–Zenodo integration on release.
- **`scripts/diagnostics/hail_day_climatology.py`:** per-cell hail-days-per-year climatology
  at six literature MESH75 thresholds; outputs under `data/analysis/hail_day_climatology/` (gitignored).
- **Stage 13 memory-safe full catalog:** disk-backed `np.memmap` for annual maxima, streamed
  Parquet event summaries (`StochasticEventWriter`), chunked empirical RP computation; temp
  memmap removed after successful run.

### Changed

- **Data policy:** `data/analysis/mesh_daily_peaks/` and `data/analysis/hail_day_climatology/` are gitignored like other generated outputs; store diagnostic bundles externally and regenerate with the diagnostic scripts.
- **`CITATION.cff`:** ORCID `0009-0000-4234-5419` for Christopher Melhauser.
- **Model v2.2.1 (retained in v2.2.2):** `EVENT_ACTIVE_THRESH_MM = 29.0` (Cintineo 2012; Wendt & Jirak 2021) for
  Stage 08 event footprints and Stage 05 subtropical-winter environmental filter; `DAMAGE_THRESH_MM`
  (25.4 mm) unchanged for occurrence products and severe-cell counts.
- **Stage 05:** era-pooled MYRORSS (2005–2011) vs GridRad (2012–2019) quantile mapping when
  same-day overlap is insufficient (replaces identity fallback for gap-era calibration).
- **Stage 05 (2026-07-05):** range-dependent debias + GridRad speckle filter rerun on full
  archive; mean pixels filtered **5.8% → 17.2%**; GridRad speckle fraction **9.7% → 6.1%**
  (diagnostic on corrected archive).

### Production

- **Full v2.2.1 hazard run complete (2026-06-30):** Stages 05–14 on 9,797 convective days;
  8,798 events at 29 mm; 50,000-yr stochastic catalog (15.17M events); all output validation passed.
- **Stage 05 debias rerun (2026-07-05):** corrected archive rebuilt with range debias and
  speckle filter; downstream Stages 06–14 rerun in progress for updated event/stochastic outputs.

## [2.2.1] — 2026-06-27

### Added

- **Stage 04c production ingest (2026-06-08 → 2026-06-27):** **2,501** gap-era convective-day
  GeoTIFFs (**2012-01-01 → 2020-10-10**); manifest `manifest_stage04c_gridrad.csv` complete
  for all **3,209** days. Combined mesh archive: **9,584+** TIFFs (MYRORSS + GridRad + MRMS).
- **`--missing-only`** backfill mode for retrying days without an output GeoTIFF.
- **d841001** (GridRad V4.2 warm-season hourly) hourly fallback and source tags
  (`gridrad-hourly-v31`, `gridrad-hourly-v42`).
- **`tests/integration/test_gridrad_hourly_fallback.py`:** end-to-end 04b adaptive → 04c discovery.
- Process-safe manifest upserts via file lock in **`scripts/_io.py`**.

### Changed

- **Stage 04b / 04c:** Added **d841001** (GridRad V4.2 warm-season hourly, Apr–Aug
  2008–2021) as an hourly fallback after **d841000** (V3.1) when GridRad-Severe is
  absent or incomplete. Recovers additional gap-era warm-season days in 2018–2020 that
  previously logged `missing_source`. Re-run **`--missing-only`** backfill to ingest.
- **Stage 04c / 04b:** Severe-first GridRad acquisition when `--with-04b-download` is set.
  GridRad-Severe (5-min) is downloaded when the THREDDS catalog lists timesteps for the
  convective window; hourly GridRad is skipped unless severe is unavailable or does not
  cover the full 12 UTC → 12 UTC day (hourly then fills gaps). Processing prefers severe
  and merges hourly only for uncovered timesteps (`gridrad-severe-5min+hourly-fill`).
- **`scripts/_io.py`:** Shared helpers for staged NetCDF discovery and convective-window
  coverage checks (`staged_nc_files_for_convective_day`, `convective_window_coverage_ok`, …).
- Documentation, PNAS draft, and agent instructions synced to v2.2.1 ingest state.

### Fixed

- **`tests/test_01_download_myrorss.py`:** Manifest classification test now calls
  `classify_mesh_source_day` from `_io.py` (replaces removed `classify_day`).

### Added (2026-05-28)

- **`docs/GIT_REMOTES.md`** and **`scripts/setup_git_remotes.sh`:** document and enforce push/PR to `origin` (`cmelhauser/us-hail-cat-model`) only.
- Agent/contributor rules in `AGENTS.md`, `CONTRIBUTING.md`, `docs/ai_instructions.md`.

### Changed (2026-05-28)

- Operational docs synced for **v2.2.1** dev branch vs **2.2.0** model on `main`.
- **`docs/literature_review.md` §3.6:** literature basis for 12 UTC → 12 UTC convective-day aggregation.
- **`docs/technical_documentation.md`**, **`docs/UPGRADE_NOTES.md`**, handoff/uncertainty/data-dictionary headers aligned to v2.2.

## [2.2.0] — 2026-05-28

**Breaking methodology change.** Daily MESH rasters now use **12 UTC → 12 UTC convective days** (label = date at window start). v2.1 calendar-UTC (00Z–00Z) production GeoTIFFs are not comparable; re-run Stages **01**, **02**, and **04c** (and downstream **05–14**) on a clean `mesh_0.05deg/` tree.

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

**Hardening release.** Same 14-stage pipeline and 0.05° grid as v2.0. No
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
- Expanded pytest suite with stage-level unit tests for all 14 stages.
- `docs/ai_instructions.md` — operating instructions for AI-assisted development.
- `docs/project_memory.md` — canonical project state snapshot.
- `docs/migration_plan.md` — v1→v2→v2.1→v3 evolution roadmap.
- `docs/executive_summary.md` — 5-minute overview for non-technical readers.
- `docs/explainer.md` — plain-language explanation of model methodology.
- `docs/UPGRADE_NOTES.md` — v2.0→v2.1 migration notes.
- `docs/PR_v1_to_v2.1.md` — reviewer-facing PR narrative for
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
- Stage 14 figure rendering with analytical vs stochastic comparison.

### Removed

- SPC-based hazard estimation from v1.0 (SPC retained for validation only).
- Population trend model from v1.0.

---

## [1.0.0] — 2025-Q2

**Initial release.** SPC-report-based hail hazard model with population trend
adjustment. Replaced by v2.0.

---

[2.1.0]: https://github.com/cmelhauser/us-hail-cat-model/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/cmelhauser/us-hail-cat-model/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/cmelhauser/us-hail-cat-model/releases/tag/v1.0.0
