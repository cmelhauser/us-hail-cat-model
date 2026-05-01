# Changelog

All notable changes to the CONUS Hail Catastrophe Model are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Expanded pytest suite with stage-level unit tests for all 15 stages.
- `docs/ai_instructions.md` — operating instructions for AI-assisted development.
- `docs/project_memory.md` — canonical project state snapshot.
- `docs/migration_plan.md` — v1→v2→v2.1→v3 evolution roadmap.
- `docs/executive_summary.md` — 5-minute overview for non-technical readers.
- `docs/explainer.md` — plain-language explanation of model methodology.
- `docs/UPGRADE_NOTES.md` — v2.0→v2.1 migration notes.
- `REVIEW_PRE_RUN.md` — pre-execution audit artifact.
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
