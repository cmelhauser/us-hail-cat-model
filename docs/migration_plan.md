# Migration Plan

**CONUS Hail Catastrophe Model**  
**Path:** v1.0 → v2.0 → v2.1

---

## 1. Purpose

This document explains the evolution of the model. v2.0 moved the model from report-based hail hazard to radar-based hail hazard. v2.1 hardens the v2.0 model for defensibility and pre-run readiness.

---

## 2. v1.0 Summary

v1.0 used SPC reports as the primary hazard input.

Limitations:

- population-density bias;
- road-network bias;
- spotter-network bias;
- diurnal reporting bias;
- rounded hail sizes;
- sparse rural observations;
- weak gridded tail support.

---

## 3. v2.0 Summary

v2.0 replaced SPC reports with radar-derived MESH as the primary hazard input.

Major changes:

- MYRORSS, GridRad, and MRMS radar sources;
- 0.05° CONUS grid;
- MESH75 correction;
- ERA5 isotherms for GridRad SHI computation;
- regional GPD ξ pooling;
- sparse event catalog;
- 50,000-year stochastic catalog;
- SPC validation only.

---

## 4. v2.0 to v2.1 Summary

v2.1 is not v3.0. It is a hardening release.

### What stays the same

- 15-stage pipeline.
- Radar-first hazard.
- 0.05° grid.
- MESH75 correction.
- Event-resampling stochastic catalog.
- Lognormal + GPD CDF framework.
- Regional ξ pooling.
- Sparse event storage.

### What changes

| Area | v2.0 | v2.1 |
|---|---|---|
| GridRad calibration | global quantile mapping | optional conditional calibration with fallback |
| Filtering | hard thresholds | optional probabilistic filter with fallback |
| Event grouping | overlap/gap/duration | adds centroid and intensity checks |
| GPD threshold | default threshold with MRL review | automated threshold diagnostics |
| Topography | fixed 5% per km | freezing-level-aware bounded correction |
| Stochastic simulation | dense reconstruction risk | sparse-safe perturbation |
| Diagnostics | basic validation and comparisons | tail-stability and analytical/stochastic divergence review |
| Tests | limited | expanded stage-level tests |
| Documentation | v2.0 methodology | synchronized v2.1 documentation |

---

## 5. v2.1 Implementation Phases

### Phase 1 — Statistical hardening

- Add threshold diagnostics.
- Add event merge checks.
- Expand validation.
- Add analytical/stochastic comparison.

### Phase 2 — Calibration and filtering

- Add optional calibration and filter artifact hooks.
- Preserve deterministic fallback.

### Phase 3 — Sparse stochastic upgrade

- Operate on `rows, cols, vals`.
- Avoid dense event cubes.
- Add sparse translation, scaling, and optional shape perturbation.

### Phase 4 — Tests and documentation

- Add tests for all stages.
- Add pre-run review.
- Synchronize README and docs.

---

## 6. Acceptance Criteria

v2.1 is ready when:

1. scripts compile;
2. tests pass;
3. `run_pipeline.py --dry-run` works;
4. Stage 05 runs without optional ML files;
5. Stage 08 sparse event outputs validate;
6. Stage 09 emits threshold diagnostics;
7. Stage 13 smoke test runs sparse-safe;
8. docs describe actual behavior.

---

## 7. Future v3.0 Candidates

Potential v3.0 work:

- fully generative storm swath model;
- max-stable spatial extremes;
- non-stationary climate-conditioned hazard;
- claims-calibrated vulnerability;
- exposure and financial loss simulation;
- portfolio aggregation.

---

## 8. Summary

v2.0 made the model radar-based. v2.1 makes it more defensible, testable, and operationally safe.
