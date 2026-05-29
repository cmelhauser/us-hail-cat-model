# CONUS Hail Catastrophe Model — v2.2

[![Version](https://img.shields.io/badge/version-v2.2-blue)]()
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
- [Outputs](#outputs)
- [Limitations](#limitations)
- [Documentation](#documentation)
- [License](#license)

---

## Overview

Version 2.2 defines daily MESH rasters on **12 UTC → 12 UTC convective days** (label = date at window start). The 15-stage pipeline and 0.05° grid are unchanged from v2.1 aside from this temporal definition; v2.1 calendar-UTC production GeoTIFFs require full re-ingest. See `docs/methodology.md` §2.6.

The model produces:

- Corrected convective-day MESH75 rasters (1998–present)
- Stage 01 source-coverage manifest distinguishing missing source days from true no-hail days
- Shared hail-value QA guard for non-finite, negative, or `>300.0 mm` artifacts
- A sparse historical event catalog
- Regional extreme-value return-period maps (10–50,000 years)
- A 50,000-year stochastic event catalog
- Exceedance probability tables and tail-stability diagnostics

**Scope.** Hail hazard only. The vulnerability module is a placeholder and is not claims-calibrated. No exposure integration or financial loss output is included in this release.

---

## Architecture

The model is organized into four logical phases:

**Phase 1 — Ingestion and Calibration (Stages 01–05)**
Raw MESH data from three radar sources are ingested, time-aligned, and cross-calibrated to a single consistent record. MYRORSS provides the 1998–2011 historical baseline; GridRad/GridRad-Severe fills **2012-01-01 through 2020-10-13** (Stage **04c**); operational MRMS covers **2020-10-14** onward. Stage **04c** reads sparse **`Reflectivity`** (dBZ), not the **`Nradecho`** echo mask. Stage 05 applies quantile-mapping bias correction between sources, optionally enhanced by a conditional ML model, and filters cells using ERA5 thermodynamic thresholds (0°C / −20°C isotherms).

**Phase 2 — Event Catalog (Stages 06–08)**
Stage 06 cross-validates the corrected MESH record against SPC storm reports (validation use only — SPC is never a hazard input). Stage 07 computes a long-term spatial climatology. Stage 08 groups contiguous hail cells into discrete events using spatial overlap, temporal continuity, centroid displacement (≤ 150 km/day), and intensity jump (≤ 3×) constraints. All events are stored as sparse arrays (`rows`, `cols`, `vals`) — no dense grids are constructed.

**Phase 3 — Extreme Value Fitting (Stages 09–11)**
Stage 09 fits a Generalized Pareto Distribution (GPD) to the tail of each grid cell's MESH distribution using L-moments, with K-means regional pooling (k = 6) and automated threshold diagnostics. Stage 10 applies spatial smoothing (150 km radius, 75 km exponential decay) to stabilize tail estimates. Stage 11 maps exceedance probabilities at eight MESH thresholds.

**Phase 4 — Hazard Output (Stages 12–15)**
Stage 12 applies a CONUS land mask and a freezing-level-aware topographic correction factor (bounded 1.0–1.25). Stage 13 generates a 50,000-year stochastic catalog by resampling the historical event library with calibrated intensity perturbation and ±3-cell spatial translation — all operations remain sparse throughout. Stage 14 applies the placeholder vulnerability curves. Stage 15 renders diagnostic figures and compares analytical (CDF-derived) against empirical (stochastic) return-period maps; divergence between the two flags GPD misspecification.

---

## Pipeline

| Stage | Script | Description |
|------:|--------|-------------|
| 01 | `01_download_myrorss.py` | MYRORSS MESH ingestion (1998–2011) |
| 02 | `02_download_mrms_mesh.py` | MRMS MESH ingestion (2020–present) |
| 03 | `03_download_spc.py` | SPC storm reports — validation only |
| 04a | `04a_download_era5_isotherms.py` | ERA5 isotherm download |
| 04b | `04b_download_gridrad.py` | Download GridRad / GridRad-Severe inputs (2012–2020-10-13) |
| 04c | `04c_fill_gridrad_gap.py` | Compute MESH75 from GridRad dBZ reflectivity + ERA5; optional GDAL peak tags |
| 05 | `05_apply_mesh_bias_correction.py` | Cross-source bias correction and filtering |
| 06 | `06_validate_mesh_vs_spc.py` | SPC validation and detection-rate diagnostics |
| 07 | `07_build_hail_climo.py` | Long-term hail frequency climatology |
| 08 | `08_build_event_catalog.py` | Sparse historical event catalog |
| 09 | `09_fit_cdf_regional.py` | Regional GPD EVT fitting via L-moments |
| 10 | `10_build_smooth_cdf.py` | Spatial smoothing of tail parameters |
| 11 | `11_build_occurrence_probs.py` | Exceedance probability rasters |
| 11b | `11b_prepare_topography.py` | NOAA ETOPO 2022 DEM download and 0.05° resampling |
| 12 | `12_apply_conus_mask.py` | CONUS mask and topographic correction |
| 13 | `13_generate_stochastic_catalog.py` | 50,000-year stochastic simulation |
| 14 | `14_build_vulnerability.py` | Placeholder vulnerability curves |
| 15 | `15_render_figures.py` | Return-period maps and diagnostics |

The pipeline is orchestrated by `run_pipeline.py`:

```bash
python run_pipeline.py [--from N] [--only N] [--skip N,N] [--dry-run] [--validate] [--skip-ml] [--retrain-models]
```

---

## Data Sources

| Dataset | Period | Role |
|---------|--------|------|
| MYRORSS MESH | Apr 1998 – Dec 2011 | Historical radar baseline |
| GridRad / GridRad-Severe | Jan 2012 – 13 Oct 2020 | Transition-period gap fill (Stage 04c) |
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
→ Stage 13 smoke (--n-years 1000) → Stage 13 full → 14 → 15
```

Run the full pipeline in one command:

```bash
python run_pipeline.py
```

Or run individual stages, ranges, or subsets:

```bash
python run_pipeline.py --only 9          # re-fit EVT
python run_pipeline.py --from 13         # resume from stochastic
python run_pipeline.py --skip 14,15      # skip vulnerability and figures
```

**Stage 05 without ML artifacts:**

```bash
python run_pipeline.py --only 5 --skip-ml
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

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Raw daily MESH rasters | `data/historical/mesh_0.05deg/` | Stage 01/02/04c convective-day (12Z→12Z) GeoTIFFs before correction |
| Mesh daily peak summaries | `data/analysis/mesh_daily_peaks/` | Optional era QA (CSV, percentiles, ECDF); tracked in git |
| Stage 01 source manifest | `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv` | Per-day MYRORSS source counts, QA-repaired daily maxima, and `missing_source` / `no_hail_pixels` / `ok` status |
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

Generated pipeline outputs are excluded from version control via `.gitignore`, except the small tracked diagnostic bundle under `data/analysis/mesh_daily_peaks/`.

---

## Limitations

The following limitations should be documented before any underwriting, regulatory, or risk-transfer application:

- **Long return periods are extrapolative.** RP > ~500 years exceed the observed record and rely on GPD tail assumptions.
- **Spatial dependence is simplified.** The stochastic catalog does not model inter-event spatial correlation beyond the historical footprint.
- **Climate non-stationarity is not modeled.** The model assumes a stationary hail climate over the radar record.
- **Source-transition uncertainty.** The MYRORSS → GridRad → MRMS calibration introduces residual bias, particularly at the 2011 and 2020 transitions.
- **SPC validation is incomplete.** Report density is spatially and temporally uneven; rural areas are systematically underrepresented.
- **Vulnerability is a placeholder.** The five-class lognormal curves are literature-based and not calibrated to claims data.

---

## Documentation

Full documentation is in `/docs`. Start with [`docs/README.md`](docs/README.md) for a guided reading path.

| Document | Description |
|----------|-------------|
| `docs/methodology.md` | Scientific assumptions and formulas |
| `docs/technical_documentation.md` | Per-stage implementation notes |
| `docs/data_dictionary.md` | All output file schemas |
| `docs/reproduce.md` | Reproduction guide and environment setup |
| `scripts/diagnostics/summarize_mesh_daily_peaks.py` | Optional mesh-era peak CSV/ECDF diagnostic |
| `docs/uncertainty.md` | Six-category uncertainty budget |
| `docs/executive_summary.md` | Non-technical overview |
| `docs/explainer.md` | Plain-language model explanation |
| `docs/REVIEW_PRE_RUN.md` | Pre-execution audit checklist |
| `AGENTS.md` | Canonical AI-agent and developer orientation |
| `docs/ai_instructions.md` | Extended AI operating rules and project constraints |
| `CONTRIBUTING.md` | Development workflow and methodology-change policy |

---

## License

MIT License. See [`LICENSE`](LICENSE) for details.

Data sourced from NOAA (MYRORSS, MRMS), NCAR RDA (GridRad), Copernicus CDS (ERA5), and NOAA SPC are subject to their respective terms of use.
