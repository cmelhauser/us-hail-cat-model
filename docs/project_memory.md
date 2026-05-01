# Project Memory

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Canonical Project Identity

- **Name:** CONUS Hail Catastrophe Model
- **Current version:** v2.1
- **Model type:** hail hazard model
- **Domain:** continental United States
- **Primary hazard input:** radar-derived MESH / MESH75
- **Grid:** 0.05°, 520 rows × 1180 columns
- **Core architecture:** 15-stage Python pipeline
- **Core stochastic design:** sparse event resampling
- **Primary output:** gridded hail hazard return-period maps and stochastic event diagnostics
- **Not included:** production exposure, financial loss, or claims-calibrated vulnerability

---

## 2. Current State

The project has been upgraded from v2.0 to v2.1. This was not a full redesign. It was a hardening update focused on defensibility, testability, and run-readiness.

The v2.1 project now includes:

- updated methodology;
- updated technical documentation;
- updated data dictionary;
- updated reproduction guide;
- updated README;
- migration notes;
- literature review;
- plain-language explainer;
- pre-run review document;
- AI instructions for future work.

The critical code and methodology emphasis is that sparse event storage must remain authoritative, especially for Stage 13.

---

## 3. Core Design Principles

### Radar-first hazard

Radar-derived MESH is the main hazard input. SPC reports are validation and calibration support only.

### Sparse-first event handling

Events are stored as active-cell arrays:

```text
rows, cols, vals
```

This avoids dense event cubes and enables efficient stochastic simulation.

### Fallback-safe modeling

Optional ML components may improve calibration or filtering, but deterministic fallback must always work.

### Dual tail review

Analytical return-period maps and stochastic return-period maps should be compared. Large divergence is a model-risk signal.

### Documentation and tests are part of the model

Any future methodology change must update tests and documentation.

---

## 4. High-Risk Stages

### Stage 05

Handles source calibration and environmental filtering. It must run with or without optional model artifacts.

### Stage 08

Builds the historical event catalog. It must preserve physical merge constraints and sparse storage.

### Stage 09

Fits frequency-severity distributions. It must emit threshold diagnostics.

### Stage 12

Applies topographic correction and CONUS mask. It must keep correction factors bounded.

### Stage 13

Generates the stochastic catalog. It must remain sparse-safe and must not reconstruct all events as dense grids.

---

## 5. Current v2.1 Upgrade Themes

- Conditional GridRad calibration with fallback.
- Probabilistic environmental filtering with fallback.
- Centroid and intensity checks for event grouping.
- Automated GPD threshold diagnostics.
- Sparse stochastic translation and scaling.
- Topographic correction using elevation relative to freezing level when available.
- Expanded validation and testing.
- Documentation synchronized to implementation.

---

## 6. Known Scientific Limitations

These should remain tracked in future work:

1. Long return periods remain extrapolative.
2. Spatial dependence is simplified.
3. Climate non-stationarity is not embedded.
4. GridRad gap-fill uncertainty remains.
5. Vulnerability is placeholder only.
6. SPC validation is biased and incomplete.

---

## 7. Future Work Priorities

Priority order:

1. Run the full pipeline.
2. Review validation and tail diagnostics.
3. Build a post-run validation dashboard.
4. Add non-stationarity diagnostics.
5. Improve spatial dependence.
6. Add exposure integration.
7. Add claims-calibrated vulnerability if data become available.
8. Consider a v3.0 generative storm swath model.

---

## 8. Compact Context for Future AI Agents

```text
Project: CONUS Hail Cat Model v2.1.
Radar-first hail hazard model on 0.05° CONUS grid.
Pipeline has 15 stages.
SPC reports are validation only.
Stage 08 stores sparse event arrays.
Stage 13 must remain sparse-safe and must not build dense event cubes.
v2.1 adds fallback-safe calibration/filtering, event merge checks, threshold diagnostics, topographic correction, expanded tests, and full documentation.
Hazard only; vulnerability is placeholder and not claims-calibrated.
```

---

## 9. Pre-Run Commands

Before full run:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

After outputs exist:

```bash
python run_pipeline.py --validate
```
