# CONUS Hail Catastrophe Model

**A ground-up probabilistic hail hazard model for the Continental United States, built from ~28 years of NOAA radar-derived MESH hail size estimates.**

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

## What This Produces

- **Return period maps** — Hail size (inches) at 10–500-year return periods for every 0.05° grid cell (~5.5 km) across CONUS.
- **Annual occurrence probability rasters** — Probability of exceeding 0.25", 0.50", 1.00", 1.50", 2.00", 3.00", 4.00", or 5.00" at each cell per year.
- **Event catalog** — Discrete historical storm events (1998–present) grouped by synoptic system.
- **Daily climatology** — 366 daily rasters capturing seasonal variation.
- **50,000-year stochastic catalog** — Event-resampled with calibrated intensity perturbation and spatial translation.
- **Vulnerability curves** — Lognormal MDR by construction class (placeholder — requires claims calibration).
- **MESH validation report** — Cross-validation of corrected MESH against SPC ground reports.

Uses **no commercial hazard data** — only publicly available NOAA radar, SPC reports (validation), and ERA5 reanalysis.

---

## Data Sources

| Source | Role | Period | Access |
|---|---|---|---|
| NOAA MYRORSS MESH | Primary hazard (historical) | 1998–2011 | AWS S3: `noaa-oar-myrorss-pds` |
| GridRad 3D NEXRAD | Primary hazard (gap fill) | 2012–2019 | NCAR RDA: `d841000` / `d841006` |
| NOAA Operational MRMS MESH | Primary hazard (operational) | 2020–present | AWS S3: `noaa-mrms-pds` |
| ERA5 Reanalysis | Isotherm heights for SHI | Climatology | Copernicus CDS |
| NOAA SPC Hail Reports | Validation / calibration | 2004–present | spc.noaa.gov |
| Murillo & Homeyer (2019/2021) | MESH75 correction coefficients | — | doi:10.1175/JAMC-D-18-0247.1 |

---

## Quick Start

```bash
git clone https://github.com/YOUR_ACCOUNT/us-hail-cat-model.git
cd us-hail-cat-model
pip install -r requirements.txt
python run_pipeline.py
```

Pipeline flags: `--from 05`, `--only 04b`, `--skip 14,15`, `--dry-run`, `--validate`

---

## Pipeline

| Stage | Script | What it does | Runtime |
|---|---|---|---|
| 01 | `01_download_myrorss.py` | Download MYRORSS MESH (1998–2011), aggregate to 0.05° | ~2–6 hrs |
| 02 | `02_download_mrms_mesh.py` | Download operational MRMS MESH (2020–present), aggregate to 0.05° | ~3–8 hrs |
| 03 | `03_download_spc.py` | Download SPC hail reports (validation only) | ~5 min |
| 04a | `04a_download_era5_isotherms.py` | Download ERA5 monthly 0°C/−20°C isotherm heights | ~30 min |
| 04b | `04b_fill_gridrad_gap.py` | Compute MESH75 from GridRad 3D reflectivity (2012–2019) | ~8–24 hrs |
| 05 | `05_apply_mesh_bias_correction.py` | Unified: MESH75 recalibration + GridRad cross-calibration + env filter | ~1 hr |
| 06 | `06_validate_mesh_vs_spc.py` | Cross-validate corrected MESH against SPC ground reports | ~15 min |
| 07 | `07_build_hail_climo.py` | Build 366-file daily climatology at 0.05° | ~10 min |
| 08 | `08_build_event_catalog.py` | Event identification (synoptic grouping) + catalog | ~15 min |
| 09 | `09_fit_cdf_regional.py` | Lognormal + GPD CDF fitting with regional ξ pooling | ~30 min |
| 10 | `10_build_smooth_cdf.py` | Spatially-pooled CDF rebuild (150 km kernel) | ~30 min |
| 11 | `11_build_occurrence_probs.py` | Annual occurrence probability rasters (8 thresholds) | ~10 min |
| 12 | `12_apply_conus_mask.py` | CONUS mask + topographic correction | ~10 min |
| 13 | `13_generate_stochastic_catalog.py` | 50,000-yr event-resampling catalog | ~3 hrs |
| 14 | `14_build_vulnerability.py` | MDR vulnerability curves by construction class | ~5 min |
| 15 | `15_render_figures.py` | All figures: historical, stochastic, analysis, validation | ~45 min |

---

## Directory Structure

```
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
│   ├── 15_render_figures.py
│   └── archive/v1/                   # Archived v1.0 scripts
├── data/                             # Gitignored — see below
├── docs/
│   ├── data_dictionary.md
│   ├── executive_summary.md
│   ├── explainer.md
│   ├── literature_review.md
│   ├── methodology.md
│   ├── migration_plan.md
│   ├── reproduce.md
│   ├── technical_documentation.md
│   └── figures/
│       ├── historical/
│       ├── stochastic/
│       └── analysis/
├── run_pipeline.py
├── requirements.txt
└── .gitignore
```

**Data directory (gitignored):**

```
data/
├── historical/
│   ├── myrorss/                ← MYRORSS MESH downloads (1998–2011)
│   ├── mrms/                   ← Operational MRMS MESH (2020–present)
│   ├── gridrad/                ← GridRad V3.1/V4.2 (2012–2019)
│   ├── gridrad_severe/         ← GridRad-Severe 5-min data
│   ├── era5/                   ← ERA5 monthly isotherm heights
│   ├── spc/                    ← SPC hail reports
│   ├── mesh_0.05deg/           ← Raw 0.05° daily MESH rasters (all sources)
│   ├── mesh_0.05deg_corrected/ ← Bias-corrected MESH75 rasters
│   ├── mesh_0.05deg_climo/     ← 366 daily climatology files
│   ├── events/                 ← Historical event catalog
│   └── validation/             ← MESH vs SPC cross-validation + figures
├── analysis/
│   ├── calibration/            ← GridRad→MYRORSS quantile mapping
│   ├── cdf/                    ← CDF parameters, GPD fits, MRL diagnostics
│   ├── occurrence/             ← Occurrence probability rasters
│   ├── topography/             ← DEM and hail survival correction grids
│   ├── vulnerability/          ← MDR curves by construction class
│   └── conus_mask/             ← CONUS land mask
└── stochastic/
    ├── catalog/                ← 50,000-yr event catalog (Parquet)
    ├── maps/                   ← Return period + p_occ GeoTIFFs
    └── pet/                    ← Probable Exceedance Tables
```

---

## Key Results

*Populated after pipeline run.*

| Metric | Value |
|---|---|
| Period of record | 1998–present (~28 years) |
| Grid resolution | 0.05° (~5.5 km) |
| Data sources | MYRORSS + GridRad + MRMS (radar) |
| MESH calibration | MESH75 (corrected Murillo & Homeyer 2021) |
| Total events | *pending* |
| GPD fallback cells | Target: <10 |
| Stochastic catalog | 50,000 years |

---

## Known Limitations

1. **MESH overestimation bias** — MESH75 reduces but does not eliminate radar overforecast tendency.
2. **GridRad temporal resolution** — Hourly composites miss short-lived peaks; cross-calibration corrects for this statistically but not event-by-event.
3. **28-year record** — Return periods beyond ~100 years carry significant extrapolation uncertainty.
4. **Event-resampling** — Cannot generate novel footprint geometries absent from the historical record.
5. **Vulnerability placeholder** — MDR parameters from literature, not calibrated to claims data.
6. **No exposure layer** — Hazard only; EP curve and AAL require TIV database.

---

## Documentation

See [`docs/`](docs/) for methodology, technical reference, data dictionary, and reproduction guide.

## License

MIT License. See [LICENSE](LICENSE).
