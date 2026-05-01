# CONUS Hail Catastrophe Model v2.1

**Status:** Methodology hardening update to v2.0
**Domain:** Continental United States hail hazard modeling
**Primary output:** 0.05° gridded hail hazard return-period maps, stochastic event catalog, validation diagnostics, and placeholder vulnerability curves 

---

## Version

This repository implements **v2.1** of the CONUS Hail Catastrophe Model.

v2.1 is a **methodology hardening release** of v2.0 focused on:

* calibration robustness
* environmental filtering improvements
* event grouping quality
* extreme value threshold diagnostics
* sparse-safe stochastic simulation
* expanded testing and documentation

This is **not a structural redesign (v3.0)**. The 15-stage pipeline remains intact.

---

## What This Project Builds

This repository builds a transparent, radar-based hail catastrophe model for the continental United States. It estimates damaging hail hazard at every 0.05° grid cell (~5.5 km resolution) using a homogenized record of radar-derived Maximum Expected Size of Hail (MESH) observations from MYRORSS, GridRad, and operational MRMS. 

The model is designed to answer:

1. How often does hail occur at each location?
2. How large can hail plausibly become for return periods from 10 to 50,000 years?
3. How do analytical extreme-value estimates compare with a stochastic event catalog?
4. Where are tail estimates unstable or sensitive to assumptions? 

---

## Why v2.1 Exists

v2.0 removed most reporting bias by shifting from SPC-driven hazard to radar-based hazard.

v2.1 improves **defensibility and production readiness** by addressing:

* conditional calibration vs global bias correction
* probabilistic vs hard-threshold filtering
* physically consistent event grouping
* auditable EVT threshold selection
* sparse-safe stochastic simulation
* topographic realism
* explicit validation and model-risk diagnostics 

---

## ⚠️ Critical Implementation Rules (v2.1)

These are **non-negotiable** for correct model behavior:

1. **Sparse event storage is authoritative**

   * Events stored as `(rows, cols, vals)`
   * Never construct dense event cubes

2. **Stage 13 must be sparse-safe**

   * No `(n_events, 520, 1180)` arrays
   * All perturbations operate on sparse arrays

3. **Stage 05 must support deterministic fallback**

   * Model must run without ML artifacts
   * `--skip-ml` must work

4. **SPC reports are validation only**

   * Not primary hazard input

5. **Vulnerability is placeholder**

   * Not claims-calibrated

---

## Core Data Sources

| Dataset                  |             Period | Role                             |   |
| ------------------------ | -----------------: | -------------------------------- | - |
| MYRORSS MESH             |          1998–2011 | Historical radar MESH reanalysis |   |
| GridRad / GridRad-Severe | 2012–2019 gap-fill | SHI → MESH75                     |   |
| MRMS MESH                |       2020–present | Operational radar                |   |
| ERA5                     |          1991–2020 | Thermodynamic fields             |   |
| SPC reports              |       2004–present | Validation only                  |   |
| DEM (optional)           |             static | Topographic correction           |   |

---

## Pipeline Overview

The pipeline has 15 stages (unchanged from v2.0):

| Stage | Script                   | Purpose        |
| ----: | ------------------------ | -------------- |
| 01–02 | Radar ingestion          | MYRORSS + MRMS |
|    03 | SPC data                 | Validation     |
|    04 | ERA5 + GridRad           | Gap fill       |
|    05 | Bias correction          | + filtering    |
|    06 | Validation               | SPC comparison |
|    07 | Climatology              |                |
|    08 | Event catalog            | Sparse         |
|    09 | EVT fitting              | + diagnostics  |
|    10 | Spatial smoothing        |                |
|    11 | Occurrence probabilities |                |
|    12 | Mask + topography        |                |
|    13 | Stochastic catalog       |                |
|    14 | Vulnerability            | Placeholder    |
|    15 | Figures                  | Diagnostics    |

---

## Quick Start (v2.1 Safe Run)

### 1. Setup

```bash
git clone <repo>
cd us-hail-cat-model
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 2. Pre-run validation (REQUIRED)

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

---

### 3. Run full pipeline

```bash
python run_pipeline.py
```

---

## Stochastic Simulation (Stage 13)

⚠️ This is the **highest-risk stage**

* Must operate on sparse arrays
* Must NOT build dense event grids

### Smoke test

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

### Full run

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 50000
```

---

## Validation Workflow

After running:

```bash
python run_pipeline.py --validate
```

Review:

1. Stage 06 → SPC validation
2. Stage 09 → threshold diagnostics
3. Stage 13 → stochastic maps
4. Stage 15 → analytical vs stochastic comparison

---

## Key Outputs

* Corrected daily MESH75 rasters
* Event catalog + sparse event arrays
* EVT return-period maps
* Stochastic return-period maps
* Probable exceedance tables
* Validation diagnostics
* Tail stability indicators 

---

## Recommended Use

Use as a **transparent hazard layer**.

Before underwriting or regulatory use:

* review validation outputs
* review EVT thresholds
* compare analytical vs stochastic tails
* document assumptions

---

## Limitations

* Hazard only (no exposure or loss)
* Long return periods are extrapolative
* Spatial dependence simplified
* GridRad gap-fill imperfect
* SPC validation incomplete
* Vulnerability not calibrated
* Climate non-stationarity not modeled 

---

## Documentation

See `/docs`:

* methodology.md
* technical_documentation.md
* data_dictionary.md
* reproduce.md
* PRE_RUN_REVIEW.md

---

## License

MIT
