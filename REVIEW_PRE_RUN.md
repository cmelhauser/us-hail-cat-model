# Pre-Run Review and Hardening Report

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Purpose

This document records the pre-run review and hardening pass completed before executing the full v2.1 pipeline. It is intended to be committed as a permanent audit artifact.

The review focused on:

- methodology holes;
- code logic risks;
- memory risks;
- stage boundary consistency;
- deterministic fallback behavior;
- sparse event safety;
- test coverage;
- documentation alignment;
- run-readiness.

---

## 2. Overall Assessment

The v2.1 project is methodologically strong and structurally sound for a public-data hail hazard model. The most important architecture choices are correct:

- radar-first hazard input;
- 0.05° common grid;
- MESH75 correction;
- sparse event storage;
- regional EVT pooling;
- analytical and stochastic return-period comparison.

The largest risks before hardening were not conceptual. They were implementation risks:

1. accidental dense event reconstruction in Stage 13;
2. optional ML artifacts causing brittle Stage 05 behavior;
3. event-grouping false merges;
4. subjective GPD threshold selection;
5. documentation/code drift.

---

## 3. High-Priority Findings and Required Fixes

### Finding 1 — Stage 13 dense event reconstruction risk

**Issue:**  
A stochastic implementation that reconstructs all historical events into a dense `(n_events, 520, 1180)` cube can waste memory and contradict the sparse event design.

**Impact:**  
Memory pressure, slower simulation, and possible failure during 50,000-year stochastic runs.

**Required resolution:**  
Stage 13 must operate directly on sparse event arrays:

```text
rows, cols, vals
```

Translation, scaling, and shape perturbation should update these arrays directly.

**Status:**  
Documented as a critical v2.1 implementation rule and covered by tests.

---

### Finding 2 — Stage 05 optional ML artifact brittleness

**Issue:**  
v2.1 supports optional conditional calibration and probabilistic filtering. If artifacts are missing, Stage 05 must not fail.

**Impact:**  
Pipeline could become unusable without trained models.

**Required resolution:**  
Stage 05 must fall back to deterministic quantile mapping and deterministic environmental filters. `--skip-ml` must force fallback.

**Status:**  
Documented and test-targeted.

---

### Finding 3 — Event grouping false merges

**Issue:**  
Overlap and temporal-gap rules alone can merge unrelated convective systems.

**Impact:**  
Event catalog bias, incorrect event footprints, distorted stochastic templates.

**Required resolution:**  
Add centroid displacement and peak intensity jump checks.

**Status:**  
Included in v2.1 methodology and testing plan.

---

### Finding 4 — GPD threshold subjectivity

**Issue:**  
Fixed thresholds plus MRL plots are not sufficiently auditable for long-return-period hazard maps.

**Impact:**  
Long-tail estimates may be unstable or hard to defend.

**Required resolution:**  
Stage 09 should emit `threshold_selection.csv` with candidate threshold diagnostics.

**Status:**  
Required by documentation and tests.

---

### Finding 5 — Documentation/code drift

**Issue:**  
Several v2.1 changes affected README, methodology, technical documentation, reproduction instructions, data dictionary, and migration notes.

**Impact:**  
Future AI agents or reviewers could misunderstand actual behavior.

**Required resolution:**  
Replace all documentation with full synchronized v2.1 files.

**Status:**  
Completed in this documentation package.

---

## 4. Methodology Risks Remaining

The following are tracked but not blockers for v2.1:

1. **Spatial dependence remains lightweight.**  
   Full max-stable spatial extremes are deferred.

2. **Climate non-stationarity is not modeled.**  
   Trend diagnostics are recommended, but the main model remains stationary.

3. **Vulnerability is placeholder.**  
   Stage 14 is not claims-calibrated.

4. **GridRad gap uncertainty remains.**  
   Conditional calibration helps but cannot fully recover missed short-lived peaks.

5. **SPC validation is imperfect.**  
   SPC reports are not complete truth.

6. **Topographic correction is first-order.**  
   It is not a full melting model.

---

## 5. Code Logic Areas to Watch During First Full Run

### Stage 01

- Confirm MYRORSS file count, including both `.netcdf` and `.netcdf.gz` source objects.
- Check output shape and CRS.
- Watch for partial files incorrectly skipped as complete.
- Review `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv` so
  `missing_source` days are not confused with available-source `no_hail_pixels`
  days.

### Stage 02

- Confirm MRMS orientation after flip.
- Check output transform and longitude convention.

### Stage 03

- Confirm SPC CSV parsing across years.
- Check header-only files do not pollute validation.

### Stage 04a

- Confirm ERA5 download succeeds.
- Check median 0°C and −20°C heights.

### Stage 04b

- Confirm GridRad-Severe is used when available.
- Watch active-column counts.
- Confirm ERA5 fallback is not used unexpectedly.

### Stage 05

- Confirm calibration mode in logs.
- Confirm `--skip-ml` behavior.
- Review pixel counts before and after filtering.
- Check GridRad correction ratios.

### Stage 06

- Confirm validation pair count.
- Review size-bin bias.
- Review day/night detection differences.

### Stage 07

- Confirm 366 climatology rasters.
- Review annual hail days for plausible maxima.

### Stage 08

- Confirm duration cap.
- Review event counts by year.
- Check sparse NPZ array lengths.

### Stage 09

- Inspect `threshold_selection.csv`.
- Review ξ values.
- Check RP map monotonicity.

### Stage 10

- Monitor runtime.
- Review smoothed maps for artifacts.

### Stage 11

- Confirm occurrence probabilities decrease with threshold.

### Stage 12

- Confirm correction factors stay within bounds.
- Confirm outside-CONUS masking.

### Stage 13

- Run `--n-years 1000` first.
- Confirm no dense event cube is created.
- Review stochastic RP maps and PET tables.

### Stage 14

- Confirm MDR curves are monotonic.
- Keep placeholder caveat clear.

### Stage 15

- Confirm figures render.
- Confirm analytical/stochastic comparison exists.

---

## 6. Required Pre-Run Commands

Before full execution:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

After outputs exist:

```bash
python run_pipeline.py --validate
```

Stage 13 smoke test:

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

---

## 7. Test Coverage Expectations

The test suite should include:

- block-maximum correctness;
- raster shape/CRS checks;
- SPC parsing tests;
- ERA5 interpolation sanity;
- SHI/MESH75 conversion tests;
- Stage 05 fallback tests;
- environmental filter monotonicity;
- event grouping edge cases;
- sparse event save/load consistency;
- GPD threshold diagnostics;
- return-period monotonicity;
- topographic correction bounds;
- sparse stochastic translation/scaling;
- vulnerability monotonicity;
- figure-render smoke tests;
- run_pipeline selection/dry-run tests.

---

## 8. Acceptance Criteria

The project is run-ready when:

1. Python files compile.
2. Unit tests pass.
3. `run_pipeline.py --dry-run` succeeds.
4. Stage 05 runs without optional ML artifacts.
5. Stage 08 emits valid sparse events.
6. Stage 09 writes threshold diagnostics.
7. Stage 13 completes a 1,000-year sparse-safe smoke run.
8. Documentation matches actual implementation.

---

## 9. Recommended Post-Run Review

After the first full run:

1. Review Stage 06 validation metrics.
2. Review source-bias diagnostics.
3. Review event counts by year.
4. Review GPD ξ and threshold maps.
5. Compare analytical and stochastic maps at 100, 500, 1,000, and 10,000 years.
6. Document high-divergence regions.
7. Archive logs, manifest, and figures.

---

## 10. Conclusion

The v2.1 hardening pass makes the model more defensible by aligning methodology, implementation expectations, test coverage, and documentation. The main remaining risks are scientific modeling limitations rather than immediate run-blocking code-structure problems.
