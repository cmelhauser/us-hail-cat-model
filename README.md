# CONUS Hail Catastrophe Model

**A public-data, radar-based probabilistic hail hazard model for the Continental United States, built from NOAA radar-derived MESH hail size estimates, ERA5 reanalysis, and stochastic event simulation.**

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Model Version](https://img.shields.io/badge/model-v2.1-purple)

---

## Overview

This repository builds a CONUS hail catastrophe-model hazard layer on a 0.05° grid, approximately 5.5 km per cell. The model uses radar-derived Maximum Expected Size of Hail (MESH) rather than SPC storm reports as the primary hazard input. SPC reports are retained for validation and calibration only.

Version **v2.1** is a production-hardening update to the v2.0 methodology. It preserves the 15-stage pipeline and output structure while improving the most important statistical and operational weaknesses:

- more robust GridRad cross-calibration with optional conditional model artifacts;
- optional probabilistic environmental filtering with deterministic fallback;
- physically constrained event grouping;
- automated EVT threshold diagnostics;
- physically informed topographic correction;
- sparse-safe stochastic simulation that avoids dense event-grid reconstruction in the hot loop;
- expanded validation and unit-test coverage for all stages.

The model produces **hazard only**. Vulnerability curves are included as literature-based placeholders, but production loss modeling requires calibrated vulnerability and exposure layers.

---

## What This Produces

- **Analytical return period maps** — hail size at 10, 25, 50, 100, 200, 250, 500, 1,000, 5,000, 10,000, and 50,000-year return periods.
- **Smoothed return period maps** — spatially pooled CDF outputs for more stable regional hazard gradients.
- **Annual occurrence probability rasters** — probability of exceeding 0.25", 0.50", 1.00", 1.50", 2.00", 3.00", 4.00", and 5.00" per year.
- **Historical event catalog** — sparse, active-cell event footprints grouped by synoptic system.
- **Daily climatology** — 366 daily climatology rasters capturing seasonal hail activity.
- **50,000-year stochastic catalog** — sparse event-resampling simulation with calibrated intensity perturbation and Gaussian spatial translation.
- **Probable Exceedance Tables** — occurrence and aggregate exceedance summaries from the stochastic catalog.
- **Validation outputs** — corrected MESH75 vs. SPC report diagnostics.
- **Vulnerability lookup tables** — placeholder lognormal MDR curves by construction class.

Uses **no commercial hazard data**. Required data sources are public, except optional claims/exposure data for downstream loss modeling.

---

## Data Sources

| Source | Role | Period | Access |
|---|---:|---:|---|
| NOAA MYRORSS MESH | Primary historical radar hazard | 1998–2011 | AWS S3: `noaa-oar-myrorss-pds` |
| GridRad / GridRad-Severe | Gap-fill radar hazard | 2012–2019 | NCAR RDA: `d841000` / `d841006` |
| NOAA Operational MRMS MESH | Operational radar hazard | 2020–present | AWS S3: `noaa-mrms-pds` |
| ERA5 Reanalysis | Freezing-level / isotherm inputs | 1991–2020 climatology | Copernicus CDS |
| NOAA SPC Hail Reports | Validation and calibration | 2004–present | `spc.noaa.gov` |
| DEM, optional | Topographic correction | static | GMTED2010, SRTM, or equivalent |

---

## v2.1 Methodology Highlights

### 1. Bias correction and environmental filtering

Stage 05 remains backward-compatible with the original deterministic v2.0 workflow:

- MYRORSS/MRMS: Witt MESH → MESH75 recalibration.
- GridRad: quantile mapping to MYRORSS/MRMS overlap distribution.
- Environmental filtering: noise floor and subtropical winter suppression.

v2.1 adds optional model-artifact hooks:

- `data/analysis/calibration/gridrad_cqm_model.pkl`
- `data/analysis/calibration/hail_filter_model.pkl`

If these files exist, Stage 05 uses them. If they do not exist, Stage 05 automatically falls back to deterministic quantile mapping and deterministic environmental filtering.

### 2. Event grouping refinement

Stage 08 still uses synoptic grouping, but v2.1 adds meteorological coherence checks before merging adjacent hail days:

- maximum centroid displacement constraint;
- maximum peak-intensity jump constraint;
- existing maximum duration cap preserved.

This reduces false merges without redesigning event storage.

### 3. EVT threshold hardening

Stage 09 keeps the zero-inflated lognormal + GPD framework with regional GPD shape-parameter pooling. v2.1 adds automated threshold scoring around the MRL diagnostic concept so GPD threshold choice is less subjective and easier to audit.

### 4. Topographic correction

Stage 12 replaces the purely fixed 5% per km assumption with a physically bounded correction that can use freezing-level context when available. If no DEM is available, the correction remains neutral at 1.0.

### 5. Sparse-safe stochastic catalog

Stage 13 no longer reconstructs all event templates as dense `(n_events, 520, 1180)` arrays. It operates directly on sparse event arrays:

```text
rows, cols, vals
```

This is the most important implementation hardening change in v2.1 because it keeps memory bounded and preserves the sparse design introduced in Stage 08.

---

## Quick Start

```bash
git clone https://github.com/YOUR_ACCOUNT/us-hail-cat-model.git
cd us-hail-cat-model
pip install -r requirements.txt
python run_pipeline.py
```

Common pipeline commands:

```bash
python run_pipeline.py --dry-run
python run_pipeline.py --validate
python run_pipeline.py --only 05
python run_pipeline.py --from 07
python run_pipeline.py --skip 14,15
python run_pipeline.py --skip-ml
python run_pipeline.py --retrain-models --only 05
```

`--skip-ml` forces deterministic v2.1 fallbacks even if optional model artifacts are present. `--retrain-models` is passed through to Stage 05 for external model-training workflows; the current Stage 05 implementation expects trained artifacts to be supplied separately.

---

## Pipeline

| Stage | Script | What it does | Runtime |
|---|---|---|---:|
| 01 | `01_download_myrorss.py` | Download MYRORSS MESH, aggregate to 0.05° daily rasters | ~2–6 hrs |
| 02 | `02_download_mrms_mesh.py` | Download operational MRMS MESH, aggregate to 0.05° daily rasters | ~3–8 hrs |
| 03 | `03_download_spc.py` | Download SPC reports for validation/calibration | ~5 min |
| 04a | `04a_download_era5_isotherms.py` | Build ERA5 0°C and −20°C isotherm climatology | ~30 min |
| 04b | `04b_fill_gridrad_gap.py` | Compute MESH75 from GridRad / GridRad-Severe reflectivity | ~8–24 hrs |
| 05 | `05_apply_mesh_bias_correction.py` | v2.1 MESH75 correction, GridRad calibration, optional probabilistic filter | ~1 hr |
| 06 | `06_validate_mesh_vs_spc.py` | Validate corrected MESH75 against SPC ground reports | ~15 min |
| 07 | `07_build_hail_climo.py` | Build 366-day climatology | ~10 min |
| 08 | `08_build_event_catalog.py` | Build sparse event catalog with physical merge constraints | ~15 min |
| 09 | `09_fit_cdf_regional.py` | Fit lognormal + GPD CDF with regional ξ pooling and threshold diagnostics | ~30 min |
| 10 | `10_build_smooth_cdf.py` | Build spatially pooled CDF return period maps | ~30 min |
| 11 | `11_build_occurrence_probs.py` | Build annual exceedance probability rasters | ~10 min |
| 12 | `12_apply_conus_mask.py` | Apply CONUS mask and bounded topographic correction | ~10 min |
| 13 | `13_generate_stochastic_catalog.py` | Generate sparse-safe 50,000-year stochastic catalog | ~3 hrs |
| 14 | `14_build_vulnerability.py` | Build placeholder MDR vulnerability curves | ~5 min |
| 15 | `15_render_figures.py` | Render figures and comparison diagnostics | ~45 min |

---

## Repository Layout

```text
us-hail-cat-model/
├── scripts/
│   ├── 01_download_myrorss.py
│   ├── 02_download_mrms_mesh.py
│   ├── 03_download_spc.py
│   ├── 04a_download_era5_isotherms.py
│   ├── 04b_fill_gridrad_gap.py
│   ├── 05_apply_mesh_bias_correction.py
│   ├── 06_validate_mesh_vs_spc.py
│   ├── 07_build_hail_climo.py
│   ├── 08_build_event_catalog.py
│   ├── 09_fit_cdf_regional.py
│   ├── 10_build_smooth_cdf.py
│   ├── 11_build_occurrence_probs.py
│   ├── 12_apply_conus_mask.py
│   ├── 13_generate_stochastic_catalog.py
│   ├── 14_build_vulnerability.py
│   └── 15_render_figures.py
├── tests/
├── docs/
├── data/                  # gitignored
├── logs/                  # gitignored
├── run_pipeline.py
├── requirements.txt
└── README.md
```

---

## Data Layout

```text
data/
├── historical/
│   ├── mesh_0.05deg/              # Raw daily MESH rasters
│   ├── mesh_0.05deg_corrected/    # Corrected daily MESH75 rasters
│   ├── mesh_0.05deg_climo/        # Daily climatology
│   ├── events/                    # Sparse event catalog
│   ├── era5/                      # ERA5 isotherms
│   ├── gridrad/                   # GridRad inputs
│   ├── gridrad_severe/            # GridRad-Severe inputs
│   ├── spc/                       # SPC reports
│   └── validation/                # Validation outputs
├── analysis/
│   ├── calibration/               # Quantile maps and optional ML artifacts
│   ├── cdf/                       # CDF parameters, RP maps, threshold diagnostics
│   ├── occurrence/                # Occurrence probability rasters
│   ├── topography/                # DEM and correction rasters
│   ├── conus_mask/                # CONUS land mask
│   └── vulnerability/             # MDR curves
└── stochastic/
    ├── catalog/                   # Stochastic event summary
    ├── maps/                      # Stochastic RP maps
    └── pet/                       # PET tables
```

---

## Testing

The v2.1 implementation package includes pytest coverage for all 15 stages plus the pipeline runner.

```bash
pip install pytest
pytest tests -q
```

The tests are designed to validate pure functions, storage assumptions, CLI wiring, and output-schema expectations without downloading full NOAA datasets.

---

## Production / Underwriting Use Notes

Before using outputs for underwriting or regulatory communication:

1. Run the full pipeline from clean inputs.
2. Run `python run_pipeline.py --validate`.
3. Run `pytest tests -q`.
4. Review Stage 06 validation output for SPC-vs-MESH bias and detection metrics.
5. Compare analytical and stochastic return period maps at 100-, 500-, 1,000-, and 10,000-year return periods.
6. Document any regions where stochastic and analytical tails diverge materially.
7. Do not use placeholder vulnerability curves for production loss estimates without claims calibration.

---

## Known Limitations

1. MESH75 reduces but does not eliminate radar hail-size bias.
2. GridRad hourly files may miss short-lived hail peaks where GridRad-Severe is unavailable.
3. Tail estimates beyond the observed record remain extrapolative, especially above 500-year return periods.
4. Stochastic resampling preserves historical footprint families and perturbs them, but it is not a fully generative storm-physics model.
5. Vulnerability curves are literature placeholders, not claims-calibrated production curves.
6. No exposure layer is included.
7. Optional ML artifacts are not trained by default; deterministic fallbacks remain the baseline.

---

## Documentation

See `docs/` for detailed methodology, technical documentation, data dictionary, reproduction guide, literature review, and plain-language explainer.

---

## License

MIT License. See `LICENSE`.
