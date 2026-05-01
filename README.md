# CONUS Hail Catastrophe Model v2.1

[![Version](https://img.shields.io/badge/version-v2.1-blue)]()
[![Status](https://img.shields.io/badge/status-methodology_hardening-orange)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)]()
[![Tests](https://img.shields.io/badge/tests-required-critical)]()

A **radar-based probabilistic hail hazard model** for the Continental United States using NOAA MESH data, ERA5 reanalysis, and stochastic event simulation.

---

## 📌 Table of Contents

- [Overview](#overview)
- [What This Model Does](#what-this-model-does)
- [Version & Scope](#version--scope)
- [Critical Implementation Rules](#critical-implementation-rules)
- [Architecture Overview](#architecture-overview)
- [Pipeline Stages](#pipeline-stages)
- [Core Data Sources](#core-data-sources)
- [Quick Start](#quick-start)
- [Validation Workflow](#validation-workflow)
- [Stochastic Simulation (Stage 13)](#stochastic-simulation-stage-13)
- [Outputs](#outputs)
- [Recommended Use](#recommended-use)
- [Limitations](#limitations)
- [Documentation](#documentation)
- [License](#license)

---

## Overview

This repository implements **v2.1** of the CONUS Hail Catastrophe Model.

It produces:
- High-resolution hail hazard maps (0.05° grid)
- Extreme value return-period estimates (10–50,000 years)
- A stochastic event catalog
- Validation and diagnostic outputs

---

## What This Model Does

The model estimates hail hazard using a **homogenized radar-derived dataset**:

- MYRORSS (historical)
- GridRad (gap-fill)
- MRMS (operational)

It answers:

1. How often hail occurs at each location  
2. How large hail can plausibly become  
3. Analytical vs stochastic tail behavior  
4. Where tail estimates are unstable  

---

## Version & Scope

**v2.1 = methodology hardening (NOT redesign)**

Focus areas:
- Calibration robustness  
- Environmental filtering  
- Event grouping  
- EVT diagnostics  
- Sparse-safe stochastic simulation  
- Testing + documentation  

The **15-stage pipeline remains unchanged** from v2.0. The runner has 16 executable entries because Stage 04 is split into `04a` and `04b`.

---

## ⚠️ Critical Implementation Rules

These are **non-negotiable**:

### 1. Sparse Event Storage
- Events stored as `(rows, cols, vals)`
- ❌ Never construct dense event cubes

### 2. Stage 13 Must Be Sparse-Safe
- ❌ No `(n_events, lat, lon)` arrays  
- ✔ Sparse-only operations
- ✔ Stochastic RP maps must be CONUS-masked before rendering

### 3. Deterministic Fallback (Stage 05)
- Must support `--skip-ml`

### 4. SPC Reports
- Validation only  
- ❌ Not hazard input

### 5. Vulnerability
- Placeholder only  
- ❌ Not claims-calibrated  

---

## 🧠 Architecture Overview

### High-Level Flow

```
Radar Data ─┐
            ├──► Bias Correction ─► Climatology ─► Event Catalog ─► EVT ─► Hazard Maps
ERA5 ───────┘                               │
                                            ▼
                                     Stochastic Simulation
                                            ▼
                                      Return Period Maps
```

---

### Pipeline (Mermaid)

```mermaid
flowchart LR
    A[Radar Ingestion] --> B[Bias Correction]
    B --> C[Climatology]
    C --> D[Event Catalog]
    D --> E[EVT Fitting]
    E --> F[Spatial Smoothing]
    F --> G[Occurrence Probabilities]
    G --> H[Mask + Topography]
    H --> I[Stochastic Catalog]
    I --> J[Diagnostics + Outputs]
```

---

## Pipeline Stages

| Stage | Component                | Purpose                     |
|------:|--------------------------|-----------------------------|
| 01–02 | Radar ingestion          | MYRORSS + MRMS             |
| 03    | SPC data                 | Validation                 |
| 04    | ERA5 + GridRad           | Gap fill                   |
| 05    | Bias correction          | + filtering                |
| 06    | Validation               | SPC comparison             |
| 07    | Climatology              | Spatial baseline           |
| 08    | Event catalog            | Sparse representation      |
| 09    | EVT fitting              | Tail modeling              |
| 10    | Spatial smoothing        | Stability                  |
| 11    | Occurrence probabilities | Frequency modeling         |
| 12    | Mask + topography        | Physical realism           |
| 13    | Stochastic catalog       | Event simulation           |
| 14    | Vulnerability            | Placeholder                |
| 15    | Figures                  | Diagnostics                |

---

## Core Data Sources

| Dataset                  | Period        | Role                             |
|-------------------------|--------------|----------------------------------|
| MYRORSS MESH            | 1998–2011     | Historical radar                 |
| GridRad / Severe        | 2012–2019     | Gap-fill                         |
| MRMS MESH               | 2020–present  | Operational radar                |
| ERA5                    | 1991–2020     | Thermodynamics                   |
| SPC reports             | 2004–present  | Validation only                  |
| DEM (optional)          | Static        | Terrain correction               |

---

## 🚀 Quick Start

### Setup

```bash
git clone <repo>
cd us-hail-cat-model
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### Pre-run Validation (**REQUIRED**)

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

---

### Run Full Pipeline

```bash
python run_pipeline.py
```

---

## 🔍 Validation Workflow

```bash
python run_pipeline.py --validate
```

Review:

- Stage 06 → SPC validation  
- Stage 09 → EVT diagnostics  
- Stage 13 → stochastic outputs  
- Stage 15 → analytical vs stochastic comparison  

---

## ⚠️ Stochastic Simulation (Stage 13)

**Highest-risk stage in the model**

### Rules
- Must use sparse arrays  
- Must NOT construct dense grids  

### Smoke Test

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

### Full Run

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 50000
```

---

## 📦 Outputs

- Corrected daily MESH75 rasters  
- Sparse event catalog  
- EVT return-period maps  
- Stochastic return-period maps  
- Exceedance probability tables  
- Validation diagnostics  
- Tail stability indicators  

---

## Recommended Use

Use as a **transparent hazard layer**.

Before underwriting or regulatory use:

- Review validation outputs  
- Inspect EVT thresholds  
- Compare analytical vs stochastic tails  
- Document assumptions  

---

## Limitations

- Hazard only (no exposure/loss modeling)  
- Long return periods are extrapolated  
- Spatial dependence simplified  
- GridRad gap-fill limitations  
- SPC validation incomplete  
- Vulnerability not calibrated  
- Climate non-stationarity not modeled  

---

## 📚 Documentation

Located in `/docs`:

- `methodology.md`  
- `technical_documentation.md`  
- `data_dictionary.md`  
- `reproduce.md`  
- `REVIEW_PRE_RUN.md`  

Generated rasters, logs, and rendered figures under `docs/figures/` are intentionally ignored by git.

---

## License

MIT  
