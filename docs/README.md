# CONUS Hail Catastrophe Model v2.1

**Status:** Methodology hardening update to v2.0  
**Domain:** Continental United States hail hazard modeling  
**Primary output:** 0.05° gridded hail hazard return-period maps, stochastic event catalog, validation diagnostics, and placeholder vulnerability curves

---

## What This Project Builds

This repository builds a transparent, radar-based hail catastrophe model for the continental United States. It estimates damaging hail hazard at every 0.05° grid cell, approximately 5.5 km, using a homogenized record of radar-derived Maximum Expected Size of Hail (MESH) observations from MYRORSS, GridRad, and operational MRMS.

The model is designed to answer:

1. **How often does hail occur at each location?**
2. **How large can hail plausibly become at each location for return periods from 10 to 50,000 years?**
3. **How do analytical extreme-value estimates compare with a stochastic event catalog?**
4. **Where are tail estimates unstable or sensitive to assumptions?**

v2.1 is not a redesign of v2.0. It is a methodological hardening update that keeps the existing 15-stage pipeline but strengthens bias correction, environmental filtering, event grouping, EVT threshold selection, stochastic simulation, topographic adjustment, and diagnostics.

---

## Why v2.1 Exists

v2.0 already moved the model from SPC-report-driven hail hazard to radar-based MESH hazard. That eliminated most population-density and reporting-time bias. The v2.1 update improves defensibility for underwriting, portfolio analytics, and technical review by addressing the main residual risks:

- GridRad-to-MYRORSS calibration should be conditional on environment, not only global quantile mapping.
- Environmental filtering should be probabilistic, not hard-threshold-only.
- Event grouping should avoid physically implausible merges.
- GPD tail thresholds should be selected and reported using automated stability diagnostics.
- Stochastic simulation should preserve sparse storage and avoid dense event reconstruction.
- Spatial translation and intensity perturbation should be calibrated and sparse-safe.
- Topographic correction should use elevation relative to melting-layer height where ERA5 is available.
- Validation should include tail diagnostics, analytical-vs-stochastic divergence, and model-risk flags.

---

## Core Data Sources

| Dataset | Period | Role |
|---|---:|---|
| MYRORSS MESH | 1998–2011 | Historical radar MESH reanalysis |
| GridRad / GridRad-Severe | 2012–2019 gap-fill target | 3D radar reflectivity used to compute SHI → MESH75 |
| Operational MRMS MESH | 2020–present | Recent operational radar MESH |
| ERA5 | 1991–2020 climatology and optional daily fields | Freezing levels, −20°C height, CAPE/RH features, topographic adjustment support |
| SPC hail reports | 2004–present | Validation and calibration support only, not primary hazard input |
| DEM, optional | static | Elevation-informed hail survival adjustment |

---

## Pipeline Overview

The pipeline has 15 stages:

| Stage | Script | Purpose |
|---:|---|---|
| 01 | `01_download_myrorss.py` | Download MYRORSS MESH and build daily 0.05° rasters |
| 02 | `02_download_mrms_mesh.py` | Download operational MRMS MESH and build daily rasters |
| 03 | `03_download_spc.py` | Download SPC reports for validation/calibration |
| 04a | `04a_download_era5_isotherms.py` | Build ERA5 monthly 0°C and −20°C isotherm height climatology |
| 04b | `04b_fill_gridrad_gap.py` | Compute MESH75 from GridRad reflectivity for the gap period |
| 05 | `05_apply_mesh_bias_correction.py` | Apply MESH75 correction, conditional calibration, and environmental filtering |
| 06 | `06_validate_mesh_vs_spc.py` | Validate corrected MESH against SPC reports |
| 07 | `07_build_hail_climo.py` | Build daily climatology and annual summary rasters |
| 08 | `08_build_event_catalog.py` | Build sparse event catalog and event peak arrays |
| 09 | `09_fit_cdf_regional.py` | Fit per-cell lognormal + regional-GPD CDFs with threshold diagnostics |
| 10 | `10_build_smooth_cdf.py` | Build spatially pooled CDF return-period maps |
| 11 | `11_build_occurrence_probs.py` | Build occurrence probability rasters for standard thresholds |
| 12 | `12_apply_conus_mask.py` | Apply CONUS mask and elevation/freezing-level topographic correction |
| 13 | `13_generate_stochastic_catalog.py` | Generate sparse-safe 50,000-year stochastic event catalog |
| 14 | `14_build_vulnerability.py` | Build placeholder MDR vulnerability curves |
| 15 | `15_render_figures.py` | Render all figures and diagnostics |

---

## v2.1 Methodology Highlights

### Conditional bias correction

Stage 05 should retain the v2.0 quantile-mapping fallback, but the preferred v2.1 method is conditional calibration using features such as raw MESH, CAPE, freezing level, latitude, month, and source. This reduces bias leakage into the tail and makes GridRad correction more stable across regimes.

### Probabilistic environmental filtering

Hard filters are retained as safety floors, but v2.1 adds a probabilistic hail-realness weight:

```text
mesh_final = mesh_corrected × P(hail_real | environment, mesh)
```

This avoids discontinuities caused by strict thresholds while preserving false-positive suppression in warm-season subtropical convection.

### Sparse-safe event and stochastic workflow

Stage 08 stores events as sparse `(rows, cols, vals)` arrays. v2.1 treats this sparse format as the source of truth. Stage 13 stochastic generation should operate directly on sparse arrays and should not reconstruct all events as dense `(n_events, 520, 1180)` arrays.

### Tail stability and model-risk diagnostics

Stage 09 adds automated GPD threshold selection diagnostics and exports `threshold_selection.csv`. Stage 15 adds analytical-vs-stochastic divergence maps and tail-stability flags to identify areas where long return-period estimates should be reviewed.

---

## Data Layout

All data lives under `data/`, which should remain gitignored.

```text
data/historical/    Raw radar, SPC reports, corrected MESH, climatology, events
data/analysis/      Calibration models, CDF parameters, occurrence, topography, vulnerability
data/stochastic/    Stochastic catalog, empirical return-period maps, EP tables
```

Figures are written to:

```text
docs/figures/historical/
docs/figures/stochastic/
docs/figures/analysis/
```

---

## Key Outputs

| Output | Description |
|---|---|
| `data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif` | Homogenized daily corrected MESH75 field |
| `data/historical/events/event_catalog.csv` | Historical event catalog |
| `data/historical/events/event_peaks.npz` | Sparse per-event peak hail arrays |
| `data/analysis/cdf/cdf_parameters.npz` | Per-cell CDF parameters |
| `data/analysis/cdf/threshold_selection.csv` | v2.1 EVT threshold diagnostics |
| `data/analysis/cdf/rp_*yr_hail_smooth.tif` | Analytical spatially pooled return-period maps |
| `data/stochastic/maps/rp_*yr_stochastic.tif` | Empirical stochastic return-period maps |
| `data/stochastic/pet/pet_occurrence.csv` | Occurrence exceedance table |
| `data/stochastic/pet/pet_aggregate.csv` | Aggregate exceedance table |
| `docs/figures/analysis/analytical_vs_stochastic_rp.png` | Cross-check of analytical vs stochastic tails |

---

## Recommended Use

Use v2.1 outputs as a transparent independent hail hazard layer. For underwriting or regulatory use, review the following diagnostics before relying on long-return-period estimates:

1. Stage 06 validation report.
2. Stage 09 threshold diagnostics and GPD stability outputs.
3. Stage 13 stochastic return-period maps.
4. Stage 15 analytical-vs-stochastic divergence maps.
5. Tail-stability flags and cells with extreme ξ or threshold instability.

---

## Limitations

- Hazard only: exposure and claims-calibrated vulnerability are not included.
- Long return periods remain sensitive to extreme-value assumptions.
- Sparse stochastic resampling preserves historical event geometry but only lightly perturbs shapes.
- Public validation data are imperfect; SPC reports are biased and should not be treated as complete truth.
- Topographic correction remains first-order unless event-scale thermodynamic fields are added.

---

## Documentation

| Document | Purpose |
|---|---|
| `executive_summary.md` | One-page technical summary |
| `methodology.md` | Full v2.1 methodology |
| `technical_documentation.md` | Stage-by-stage technical specification |
| `data_dictionary.md` | Output files, formats, schemas, and units |
| `literature_review.md` | Supporting literature and references |
| `migration_plan.md` | v1.0 → v2.0 and v2.0 → v2.1 transition notes |
| `reproduce.md` | Reproduction and validation guide |
| `explainer.md` | Plain-language stakeholder explanation |
