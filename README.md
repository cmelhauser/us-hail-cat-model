# CONUS Hail Catastrophe Model — v2.2.2

[![Version](https://img.shields.io/badge/version-v2.2.2-blue)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![CI](https://github.com/melhauserc/us-hail-cat-model/actions/workflows/tests.yml/badge.svg)](https://github.com/melhauserc/us-hail-cat-model/actions/workflows/tests.yml)

A radar-based probabilistic hail hazard model for the Continental United States. The model ingests 25+ years of NOAA multi-radar MESH data, fits regional extreme-value distributions, and generates a 50,000-year stochastic event catalog on a 0.05° CONUS grid.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Pipeline](#pipeline)
- [Data Sources](#data-sources)
- [Quick Start](#quick-start)
- [Running the Pipeline](#running-the-pipeline)
- [AWS Fargate (optional)](#aws-fargate-optional)
- [Outputs](#outputs)
- [Limitations](#limitations)
- [Documentation](#documentation)
- [Credits](#credits)
- [License](#license)

---

## Overview

Version 2.2 defines daily MESH rasters on **12 UTC → 12 UTC convective days**. **v2.2.1** introduced literature-aligned severe-hail thresholds and era-pooled GridRad calibration (see `docs/methodology.md` §2.7); **v2.2.2** adds range debias, GridRad artifact filtering (§5.5), and hazard-only pipeline staging (14 stages).

**Preferred thresholds (v2.2.2):**

| Constant | Value | Use |
|----------|------:|-----|
| `EVENT_ACTIVE_THRESH_MM` | **29.0 mm** | Stage 08 event footprints; Stage 05 subtropical winter filter |
| `DAMAGE_THRESH_MM` | 25.4 mm | Damage onset; occurrence products and Stage 13 severe-cell counts |
| GridRad calibration | era-pooled QM | MYRORSS 2005–2011 vs GridRad 2012–2019 (median ratio ~1.10) |
| Range debias | SPC-collocated | Per-era multiplicative factors vs nearest-radar distance (125 km reference) |
| GridRad artifact filter | 5-pass (speckle + inner-ref radial ring + azimuthal + filament + 21-day persistence) | GridRad days only, Stage 05; see `methodology.md` §5.5 |

The model produces:

- Corrected convective-day MESH75 rasters (1998–present)
- Stage 01 source-coverage manifest distinguishing missing source days from true no-hail days
- Shared hail-value QA guard for non-finite, negative, or `>300.0 mm` artifacts
- A sparse historical event catalog
- Regional extreme-value return-period maps (10–50,000 years)
- A 50,000-year stochastic event catalog
- Exceedance probability tables and tail-stability diagnostics

**Scope.** Hail hazard only — gridded occurrence, intensity, return periods, and stochastic event catalogs. No exposure integration, vulnerability curves, or financial loss output. Claims-calibrated damage functions are documented as **future work** (see `docs/methodology.md` §14).

### Production run (v2.2.1, completed 2026-06-30)

Historical reference only — superseded by **v2.2.2** artifact-filter and debias rebuilds (2026-07).

| Metric | Value |
|--------|------:|
| Convective-day archive | 9,797 days (1998–2026) |
| Corrected MESH75 (Stage 05) | 9,797 days; era-pooled GridRad QM |
| Historical events (29 mm) | 8,798 (~303 yr⁻¹) |
| SPC validation pairs | 173,766 |
| Stochastic simulation | 50,000 yr; 15.17M synthetic events |
| Stochastic 100-yr CONUS peak | 157.8 mm (6.21 in) |
| Stochastic 50,000-yr CONUS peak | 300.0 mm (11.81 in) |

Full pipeline validated with `run_pipeline.py --from 05 --skip-ml` and Stage 13 memmap-backed catalog generation. **v2.2.2** is re-ingesting MYRORSS (Stage 01 coordinate fix) and rebuilding Stages 05–07 with five-pass GridRad filtering (including spatiotemporal range-ring persistence); see `docs/RUN_NOTES.md`.

---

## Architecture

The model is organized into four logical phases:

**Phase 1 — Ingestion and Calibration (Stages 01–05)**
Raw MESH data from three radar sources are ingested, time-aligned, and cross-calibrated to a single consistent record. MYRORSS provides the 1998–2011 historical baseline; GridRad/GridRad-Severe fills **2012-01-01 through 2020-10-13** (Stage **04c**); operational MRMS covers **2020-10-14** onward. Stage **04c** reads sparse **`Reflectivity`** (dBZ), not the **`Nradecho`** echo mask. Stage 05 applies Witt→MESH75 recalibration, **era-pooled GridRad quantile mapping** (when same-day overlap is absent), and environmental filtering (5 mm noise floor; subtropical winter ≥ **29 mm** at lat &lt; 30°N).

**Phase 2 — Event Catalog (Stages 06–08)**
Stage 06 cross-validates the corrected MESH record against SPC storm reports (validation only). Stage 07 computes long-term DOY climatology. Stage 08 groups contiguous hail cells into events at the **29 mm** skill threshold (`EVENT_ACTIVE_THRESH_MM`), with spatial overlap, temporal continuity, centroid displacement (≤ 150 km/day), and intensity jump (≤ 3×) constraints. Sparse `rows/cols/vals` storage only.

**Phase 3 — Extreme Value Fitting (Stages 09–11)**
Stage 09 fits a Generalized Pareto Distribution (GPD) to the tail of each grid cell's MESH distribution using L-moments, with K-means regional pooling (k = 6) and automated threshold diagnostics. Stage 10 applies spatial smoothing (150 km radius, 75 km exponential decay) to stabilize tail estimates. Stage 11 maps exceedance probabilities at eight MESH thresholds.

**Phase 4 — Hazard Output (Stages 12–14)**
Stage 12 applies a CONUS land mask and a freezing-level-aware topographic correction factor (bounded 1.0–1.25). Stage 13 generates a 50,000-year stochastic catalog by resampling the historical event library with calibrated intensity perturbation and ±3-cell spatial translation — all operations remain sparse throughout. Stage 14 renders diagnostic figures on Lambert Conformal CONUS maps (`scripts/_mapping.py`: country and state boundaries) and compares analytical (CDF-derived) against empirical (stochastic) return-period maps; divergence between the two flags GPD misspecification.

---

## Pipeline

| Stage | Script | Description |
|------:|--------|-------------|
| 01 | `01_download_myrorss.py` | MYRORSS MESH ingestion (1998–2011) |
| 02 | `02_download_mrms_mesh.py` | MRMS MESH ingestion (2020–present) |
| 03 | `03_download_spc.py` | SPC storm reports — validation only |
| 04a | `04a_download_era5_isotherms.py` | ERA5 isotherm download |
| 04b | `04b_download_gridrad.py` | Download GridRad / GridRad-Severe inputs (2012–2020-10-13) |
| 04c | `04c_fill_gridrad_gap.py` | Compute MESH75 from GridRad dBZ reflectivity + ERA5; severe-first download when chained with 04b; optional GDAL peak tags |
| 05 | `05_apply_mesh_bias_correction.py` | Cross-source bias correction and filtering |
| 06 | `06_validate_mesh_vs_spc.py` | SPC validation and detection-rate diagnostics |
| 07 | `07_build_hail_climo.py` | Long-term hail frequency climatology |
| 08 | `08_build_event_catalog.py` | Sparse historical event catalog |
| 09 | `09_fit_cdf_regional.py` | Regional GPD EVT fitting via L-moments |
| 10 | `10_build_smooth_cdf.py` | Spatial smoothing of tail parameters |
| 11 | `11_build_occurrence_probs.py` | Exceedance probability rasters |
| 11b | `11b_prepare_topography.py` | NOAA ETOPO 2022 DEM download and 0.05° resampling |
| 12 | `12_apply_conus_mask.py` | CONUS mask and topographic correction |
| 13 | `13_generate_stochastic_catalog.py` | 50,000-year stochastic catalog |
| 14 | `14_render_figures.py` | Return-period maps and diagnostics |

The pipeline is orchestrated by `run_pipeline.py`:

```bash
python run_pipeline.py [--from N] [--only N] [--skip N,N] [--dry-run] [--validate] [--skip-ml] [--skip-calibration] [--clean-from N] [--retrain-models]
```

---

## Data Sources

| Dataset | Period | Role |
|---------|--------|------|
| MYRORSS MESH | Apr 1998 – Dec 2011 | Historical radar baseline |
| GridRad-Severe (d841006) | Jan 2012 – 13 Oct 2020 | Preferred gap-fill source (~100 severe events/year) |
| GridRad hourly V3.1 (d841000) | Jan 2012 – Dec 2017 | Hourly gap-fill fallback (all months) |
| GridRad hourly V4.2 (d841001) | Apr–Aug 2018 – Aug 2021 | Warm-season hourly fallback when Severe absent |
| MRMS MESH | 14 Oct 2020 – present | Operational radar |
| ERA5 (0°C / −20°C isotherms) | 1991–2020 | Thermodynamic filtering |
| SPC storm reports | 2004 – present | Validation only |
| NOAA/NCEI ETOPO 2022 surface elevation | Static | Stage 11b DEM source for topographic correction |

Free accounts are required at [NCAR RDA](https://rda.ucar.edu) (GridRad) and [Copernicus CDS](https://cds.climate.copernicus.eu) (ERA5). Stage 04a uses the CDS API and requires both accepted ERA5 dataset licence terms and a local `~/.cdsapirc` file before the ERA5 download can run:

```yaml
url: https://cds.climate.copernicus.eu/api
key: YOUR_PERSONAL_ACCESS_TOKEN
```

Generate the token from your Copernicus CDS profile, save the file outside the repository, and restrict it with `chmod 600 ~/.cdsapirc`. Never commit API credentials.

Before running Stage 04a, sign in to CDS and accept the licence terms for both ERA5 monthly datasets used by the script:

- [ERA5 monthly pressure-level means](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels-monthly-means?tab=download#manage-licences)
- [ERA5 monthly single-level means](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means?tab=download#manage-licences)

CDS will reject authenticated API calls until those licence terms are accepted for the account tied to the token. The failure looks like `403 Client Error: Forbidden` with `required licences not accepted`; this is a CDS account setup issue, not a bad `.cdsapirc` file.

Stage 04a submits the ERA5 pressure-level request in bounded yearly chunks, with an automatic monthly fallback if CDS rejects a year as too large. The chunks are retained under `data/historical/era5/pressure_chunks/` so interrupted ERA5 runs can resume without repeating completed downloads.

Stage 11b downloads [NOAA/NCEI ETOPO 2022](https://doi.org/10.25921/fd45-gt74) 60 arc-second surface elevation from the public NOAA archive, caches the source GeoTIFF under `data/analysis/topography/source/`, and writes `data/analysis/topography/elevation_0.05deg.tif` on the model grid. Stage 12 uses this DEM for bounded topographic correction; if the DEM is absent, Stage 12 falls back to a neutral `1.0` correction.

---

## Quick Start

**Requirements:** Python 3.10+, and system libraries for `cartopy`, `eccodes`, and `rasterio` (GEOS, PROJ, ecCodes).

```bash
git clone https://github.com/melhauserc/us-hail-cat-model.git
cd us-hail-cat-model
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Alternatively, use the provided Docker image for a fully reproducible environment:

```bash
docker build -t hail-cat-model .
docker run --rm -it hail-cat-model bash
```

**Pre-run validation (required before first execution):**

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

---

## Running the Pipeline

**Recommended first-run sequence:**

```
01 → 02 → 03 → 04a → 04c → 05 (--skip-ml) → 06 → 07 → 08 → 09 → 10 → 11 → 11b → 12
→ Stage 13 smoke (--n-years 1000) → Stage 13 full → 14
```

Run the full pipeline in one command:

```bash
python run_pipeline.py
```

Or run individual stages, ranges, or subsets:

```bash
python run_pipeline.py --only 9          # re-fit EVT
python run_pipeline.py --from 13         # resume from stochastic
python run_pipeline.py --skip 14           # skip figure rendering
```

**Stage 05 without ML artifacts:**

```bash
python run_pipeline.py --only 05 --skip-ml --skip-calibration
```

**Stage 05 rebuild after filter or debias changes** (blocking; cleans Stages 05–14 outputs):

```bash
python scripts/rerun_stage05.py
# equivalent:
python run_pipeline.py --only 05 --clean-from 05 --skip-ml --skip-calibration
```

**Stage 13 smoke test (before committing to the 50,000-year run):**

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

**Post-run validation:**

```bash
python run_pipeline.py --validate
```

---

## AWS Fargate (optional)

For cloud runs without changing stage scripts, use the **`aws/`** adapter: CDK deploys
ECS Fargate + EFS + ECR, and a local CLI submits tasks.

| Mode | Behavior |
|------|----------|
| Parallel downloads | Stages **01**, **02**, and **04c** as separate Fargate tasks |
| Finalize | Stages **03**, **04a**, **05–14** on one task (skips standalone **04b**) |
| Shared storage | EFS mounts at `/app/data`, `/app/logs`, `/app/docs/figures` |

```bash
pip install -e ".[aws]"
python aws/run_pipeline_aws.py --dry-run
# After CDK deploy + image push to ECR:
python aws/run_pipeline_aws.py --mode full
```

Details: [`aws/README.md`](aws/README.md), [`docs/reproduce.md`](docs/reproduce.md) §14,
and the design spec under `docs/superpowers/specs/`.

---

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Raw daily MESH rasters | `data/historical/mesh_0.05deg/` | Stage 01/02/04c convective-day (12Z→12Z) GeoTIFFs before correction |
| Mesh daily peak summaries | `data/analysis/mesh_daily_peaks/` | Optional era QA (CSV, percentiles, ECDF); gitignored |
| Stage 01 source manifest | `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv` | Per-day MYRORSS source counts, QA-repaired daily maxima, and `missing_source` / `no_hail_pixels` / `ok` status |
| Stage 04c gap-fill manifest | `data/historical/mesh_0.05deg/manifest_stage04c_gridrad.csv` | Per-day GridRad gap-fill status for 2012-01-01 – 2020-10-13 |
| Corrected MESH rasters | `data/historical/mesh_0.05deg_corrected/` | Daily MESH75 grids |
| Event catalog | `data/historical/events/` | Sparse `.npz` per event |
| EVT parameters | `data/analysis/cdf/` | GPD ξ, σ, threshold per cell |
| Return-period maps | `data/analysis/cdf/` | Analytical RP rasters |
| Model-grid DEM | `data/analysis/topography/elevation_0.05deg.tif` | NOAA/NCEI ETOPO 2022 surface elevation resampled by Stage 11b |
| Topographic correction | `data/analysis/topography/topo_correction.tif` | Bounded terrain correction applied by Stage 12 |
| Stochastic catalog | `data/stochastic/` | 50,000-yr event library |
| Stochastic RP maps | `data/stochastic/` | Empirical return periods |
| Exceedance tables | `data/stochastic/` | PET tables by threshold |
| Figures | `docs/figures/` | Diagnostic and output maps |

Generated pipeline outputs and diagnostic summaries are excluded from version control via `.gitignore` (`data/`, `docs/figures/`, `logs/`). External archival instructions: [`docs/DATA_AVAILABILITY.md`](docs/DATA_AVAILABILITY.md).

---

## Limitations

The following limitations should be documented before any underwriting, regulatory, or risk-transfer application:

- **Long return periods are extrapolative.** RP > ~500 years exceed the observed record and rely on GPD tail assumptions.
- **Spatial dependence is simplified.** The stochastic catalog does not model inter-event spatial correlation beyond the historical footprint.
- **Climate non-stationarity is not modeled.** The model assumes a stationary hail climate over the radar record.
- **Source-transition uncertainty.** The MYRORSS → GridRad → MRMS calibration introduces residual bias, particularly at the 2011 and 2020 transitions. v2.2.2 adds range-dependent debias and a five-pass GridRad artifact filter (Stage 05), including spatiotemporal range-ring persistence from a 21-day trailing window, but a broad GridRad–MYRORSS climatological offset can remain in era-comparison diagnostics until MYRORSS re-ingest and Stage 05 rebuild complete.
- **Radar-site artifacts.** GridRad-era data can exhibit NEXRAD range rings and speckle in return-period maps if uncorrected; delete `mesh_0.05deg_corrected/`, rerun Stage 05 with the artifact filter, then `radar_artifact_diagnostic.py` and downstream stages after calibration changes.
- **SPC validation is incomplete.** Report density is spatially and temporally uneven; rural areas are systematically underrepresented.
- **Vulnerability and loss modeling are out of scope.** This repository delivers hazard only; MDR curves, exposure, and financial loss are future work (see `docs/methodology.md` §14).

---

## Documentation

Full documentation is in `/docs`. Start with [`docs/README.md`](docs/README.md) for a guided reading path.

| Document | Description |
|----------|-------------|
| `docs/methodology.md` | Scientific assumptions and formulas |
| `docs/technical_documentation.md` | Per-stage implementation notes |
| `docs/data_dictionary.md` | All output file schemas |
| `docs/reproduce.md` | Reproduction guide and environment setup (includes §14 AWS Fargate) |
| `aws/README.md` | Optional ECS Fargate adapter (CDK + `run_pipeline_aws.py`) |
| `docs/DATA_AVAILABILITY.md` | Zenodo/ORCID archival plan for code, figures, and diagnostics |
| `scripts/diagnostics/summarize_mesh_daily_peaks.py` | Optional mesh-era peak CSV/ECDF diagnostic |
| `scripts/diagnostics/hail_day_climatology.py` | Per-cell hail-day climatology and MESH75 threshold sensitivity |
| `scripts/diagnostics/radar_artifact_diagnostic.py` | Speckle scores, range debias fit, GridRad−MYRORSS artifact maps |
| `docs/uncertainty.md` | Six-category uncertainty budget |
| `docs/executive_summary.md` | Non-technical overview |
| `docs/explainer.md` | Plain-language model explanation |
| `docs/REVIEW_PRE_RUN.md` | Pre-execution audit checklist |
| `AGENTS.md` | Canonical AI-agent and developer orientation |
| `docs/ai_instructions.md` | Extended AI operating rules and project constraints |
| `CONTRIBUTING.md` | Development workflow and methodology-change policy |

---

## Credits

| Role | Credit |
|------|--------|
| Author / scientific lead | Christopher Melhauser |
| AI collaborator | **theonlymuffinbot** |

**theonlymuffinbot** is the project pseudonym for all AI collaboration on this
repository (implementation, tests, documentation, diagnostics, run monitoring,
and manuscript drafting under human direction). It is an attribution name, not a
separate GitHub repository. The sole code remote is
[`cmelhauser/us-hail-cat-model`](https://github.com/cmelhauser/us-hail-cat-model).

See `docs/ai_instructions.md` and the AI disclosure sections in
`docs/pnas_article_ai_hail_model.md` for workflow detail.

---

## License

MIT License. See [`LICENSE`](LICENSE) for details (copyright: Christopher
Melhauser and theonlymuffinbot).

Data sourced from NOAA (MYRORSS, MRMS), NCAR RDA (GridRad), Copernicus CDS (ERA5), and NOAA SPC are subject to their respective terms of use.
