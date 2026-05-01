# Migration Plan

**CONUS Hail Catastrophe Model**  
**Path:** v1.0 → v2.0 → v2.1

---

## 1. Purpose

This document explains the evolution of the hail catastrophe model. v2.0 replaced the report-based v1.0 hazard foundation with radar-derived MESH. v2.1 hardens the v2.0 methodology without changing the overall model generation.

---

## 2. v1.0 to v2.0 Summary

### v1.0

v1.0 used SPC storm reports as the primary hazard input and attempted to correct reporting bias through population-based debiasing.

Limitations:

- Population-density bias.
- Road-network and spotter-network bias.
- Diurnal reporting bias.
- Report-size rounding.
- Sparse rural data.
- Weak basis for gridded tail fitting.

### v2.0

v2.0 replaced SPC reports with radar-derived MESH as the primary hazard input.

Major changes:

- MYRORSS, GridRad, and MRMS radar sources.
- 0.05° CONUS grid.
- MESH75 recalibration.
- ERA5 isotherms for GridRad SHI computation.
- Regional GPD ξ pooling.
- Sparse event catalog.
- 50,000-year stochastic catalog.
- SPC retained for validation only.

---

## 3. v2.0 to v2.1 Summary

v2.1 is not a v3.0 rewrite. It is a defensibility and robustness upgrade.

### What stays the same

- 15-stage pipeline.
- 0.05° grid.
- Radar-based hazard foundation.
- MESH75 correction.
- Event-resampling stochastic catalog.
- Lognormal + GPD CDF framework.
- Regional ξ pooling.
- Sparse event storage.

### What changes

| Area | v2.0 | v2.1 |
|---|---|---|
| GridRad calibration | global quantile mapping | conditional calibration with quantile fallback |
| Environmental filtering | hard thresholds | probabilistic filtering plus safety floors |
| Event grouping | overlap/gap/duration rules | adds centroid and intensity sanity checks |
| GPD threshold | MRL validation of default | automated threshold selection diagnostics |
| Spatial dependence | mostly implicit | diagnosed and optionally sampled with lightweight copula |
| Topography | fixed 5% per km | elevation/freezing-level survival factor |
| Stochastic events | dense reconstruction in Stage 13 risk | sparse-safe event perturbation |
| Diagnostics | validation and comparison plots | tail stability and analytical-vs-stochastic divergence flags |

---

## 4. v2.1 Implementation Phases

### Phase 1 — Low-risk statistical hardening

1. Add automated GPD threshold diagnostics to Stage 09.
2. Add analytical-vs-stochastic difference maps to Stage 15.
3. Add event-merge centroid and intensity checks to Stage 08.
4. Expand validation outputs in Stage 06.

### Phase 2 — Calibration and filtering

1. Add conditional GridRad calibration model in Stage 05.
2. Add probabilistic environmental filter in Stage 05.
3. Add calibration and filter diagnostics.
4. Add fallback behavior when ML model files are unavailable.

### Phase 3 — Sparse-safe stochastic upgrade

1. Refactor Stage 13 to avoid dense event cube reconstruction.
2. Apply translation directly to sparse rows/cols.
3. Apply percentile-dependent intensity scaling to sparse vals.
4. Add light sparse shape perturbation.
5. Add stochastic diagnostics.

### Phase 4 — Topographic and dependence diagnostics

1. Upgrade Stage 12 topographic factor to use freezing level where available.
2. Add correlation-decay diagnostics for spatial dependence.
3. Optionally add local Gaussian-copula sampling.

---

## 5. Script-Level Migration Notes

### Stage 05

Add optional model files:

```text
data/analysis/calibration/gridrad_cqm_model.pkl
data/analysis/calibration/hail_filter_model.pkl
```

Fallback behavior must remain:

```text
if ML model missing:
    use quantile mapping and hard environmental filters
```

### Stage 08

Add merge rejection rules:

```text
centroid displacement > 150 km/day → reject merge
peak intensity ratio > 3× → reject merge
```

### Stage 09

Add:

```text
select_threshold(region_data)
threshold_selection.csv
```

### Stage 12

Upgrade topographic correction:

```text
factor = 1 + α × elevation_km / freezing_level_km
```

Fallback to elevation-only if freezing level unavailable.

### Stage 13

Refactor from dense-event workflow to sparse-event workflow:

```text
rows, cols, vals = load_sparse_event(template_id)
rows, cols = translate_sparse(rows, cols)
vals = scale_sparse(vals)
update_active_annual_max(rows, cols, vals)
```

### Stage 15

Add diagnostic figure outputs:

```text
analytical_vs_stochastic_delta_*.png
tail_stability_flags.png
gpd_threshold_map.png
source_distribution_comparison.png
```

---

## 6. Documentation Migration

All documentation should use version **2.1** and describe v2.1 as an incremental methodology hardening update.

Documents updated in this package:

```text
README.md
executive_summary.md
methodology.md
technical_documentation.md
data_dictionary.md
reproduce.md
explainer.md
literature_review.md
migration_plan.md
```

---

## 7. Testing Migration

v2.1 should add unit tests for all stages, with special focus on:

- Raster shape and orientation.
- Bias correction fallback behavior.
- Environmental filtering monotonicity.
- Event grouping edge cases.
- Sparse event save/load consistency.
- GPD threshold selection stability.
- Return-period monotonicity.
- CONUS mask application.
- Sparse-safe stochastic simulation.
- Vulnerability MDR monotonicity.
- Figure-render smoke tests.

Recommended test layout:

```text
tests/test_stage01_myrorss.py
tests/test_stage02_mrms.py
tests/test_stage03_spc.py
tests/test_stage04a_era5.py
tests/test_stage04b_gridrad.py
tests/test_stage05_bias_correction.py
tests/test_stage06_validation.py
tests/test_stage07_climo.py
tests/test_stage08_events.py
tests/test_stage09_cdf.py
tests/test_stage10_smooth_cdf.py
tests/test_stage11_occurrence.py
tests/test_stage12_mask_topo.py
tests/test_stage13_stochastic.py
tests/test_stage14_vulnerability.py
tests/test_stage15_figures.py
```

---

## 8. Acceptance Criteria for v2.1

v2.1 is complete when:

1. All 15 stages run or validate successfully.
2. Stage 05 can run with or without ML model files.
3. Stage 08 produces sparse events with no duration-cap violations.
4. Stage 09 writes `threshold_selection.csv` and stable CDF parameters.
5. Stage 13 avoids dense event cube reconstruction in production mode.
6. Stage 15 renders analytical-vs-stochastic diagnostics.
7. Documentation consistently describes v2.1 methodology.
8. Unit tests pass on synthetic fixtures.

---

## 9. Future v3.0 Candidates

v2.1 intentionally avoids major redesign. Potential v3.0 work includes:

- Fully generative storm swath model.
- Max-stable or Brown-Resnick spatial extremes.
- Non-stationary climate-conditioned frequency/severity model.
- Claims-calibrated vulnerability by roof age/material/region.
- Exposure integration and financial loss simulation.
- Portfolio-level aggregate loss model.

---

## 10. Summary

v2.0 made the model radar-based. v2.1 makes it more defensible. The update preserves the pipeline while improving calibration, filtering, event logic, tail fitting, stochastic realism, topographic treatment, and diagnostics.
