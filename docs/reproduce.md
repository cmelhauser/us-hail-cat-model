# Reproduction Guide

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Prerequisites

Recommended environment:

- Python 3.9+.
- `requirements.txt` installed.
- AWS access libraries for public S3 reads.
- NCAR RDA account for GridRad downloads.
- Copernicus CDS account for ERA5.
- Approximately 2 TB disk space if storing raw radar inputs.
- At least 16 GB RAM; more is recommended for Stage 10 and Stage 13.

Recommended packages include:

```text
numpy
pandas
scipy
rasterio
xarray
netCDF4
cfgrib
eccodes
boto3
s3fs
scikit-learn
matplotlib
cartopy
regionmask
pyarrow
pytest
```

---

## 2. Setup

```bash
git clone https://github.com/YOUR_ACCOUNT/us-hail-cat-model.git
cd us-hail-cat-model
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure ERA5 CDS credentials:

```bash
cat > ~/.cdsapirc << CDSEOF
url: https://cds.climate.copernicus.eu/api
key: YOUR-PERSONAL-ACCESS-TOKEN
CDSEOF
```

---

## 3. Full Pipeline

```bash
python run_pipeline.py
```

The full pipeline is resumable stage-by-stage. Runtime depends heavily on download bandwidth and whether GridRad files are already local.

---

## 4. Stage-by-Stage Execution

### Stage 01 — MYRORSS

```bash
python run_pipeline.py --only 01
```

Output:

```text
data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif
```

### Stage 02 — MRMS

```bash
python run_pipeline.py --only 02
```

Output uses the same path as Stage 01.

### Stage 03 — SPC reports

```bash
python run_pipeline.py --only 03
```

Output:

```text
data/historical/spc/YYYY/
```

### Stage 04a — ERA5 isotherms

```bash
python run_pipeline.py --only 04a
```

Output:

```text
data/historical/era5/era5_monthly_isotherms_conus.nc
```

### Stage 04b — GridRad gap fill

GridRad files must be downloaded separately from NCAR RDA into:

```text
data/historical/gridrad/
data/historical/gridrad_severe/
```

Check data availability:

```bash
python scripts/04b_fill_gridrad_gap.py --check-data
```

Run gap fill:

```bash
python run_pipeline.py --only 04b
```

### Stage 05 — Bias correction and filtering

```bash
python run_pipeline.py --only 05
```

v2.1 preferred behavior:

- Use conditional calibration model if present.
- Use probabilistic environmental filter if present.
- Fall back to quantile mapping and hard filters if models are absent.

Recommended optional flags:

```bash
python run_pipeline.py --only 05 --retrain-models
python run_pipeline.py --only 05 --skip-ml
```

### Stage 06 — Validation

```bash
python run_pipeline.py --only 06
```

Outputs:

```text
data/historical/validation/
docs/figures/analysis/
```

### Stages 07–15

```bash
python run_pipeline.py --from 07
```

Or individually:

```bash
python run_pipeline.py --only 07
python run_pipeline.py --only 08
python run_pipeline.py --only 09
python run_pipeline.py --only 10
python run_pipeline.py --only 11
python run_pipeline.py --only 12
python run_pipeline.py --only 13
python run_pipeline.py --only 14
python run_pipeline.py --only 15
```

---

## 5. Fast Development Runs

Use shorter or narrower runs for development.

Examples:

```bash
python scripts/01_download_myrorss.py --year 2005 --month 5
python scripts/02_download_mrms_mesh.py --year 2023 --month 5
python scripts/05_apply_mesh_bias_correction.py --year 2005 --skip-calibration
python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

---

## 6. Validation Without Re-running

```bash
python run_pipeline.py --validate
```

Each stage should also support direct validation:

```bash
python scripts/08_build_event_catalog.py --validate
python scripts/09_fit_cdf_regional.py --validate
python scripts/13_generate_stochastic_catalog.py --validate
```

---

## 7. v2.1 Quality-Control Checklist

Before treating outputs as final, verify:

### Calibration

- `gridrad_quantile_map.npz` exists.
- If ML calibration is used, `gridrad_cqm_model.pkl` exists.
- Source distributions before/after correction are plausible.
- Calibration diagnostics do not show extreme correction ratios in the tail.

### Environmental filtering

- `hail_filter_model.pkl` exists if probabilistic filtering is enabled.
- Filtered pixel count does not collapse unrealistically.
- Warm-season subtropical false positives are reduced.

### Event catalog

- `event_catalog.csv` exists.
- `event_peaks.npz` exists.
- No event duration exceeds 5 days.
- Event centroids and footprints are plausible.
- Sparse arrays have matching row/col/value lengths.

### CDF fitting

- `cdf_parameters.npz` exists.
- `threshold_selection.csv` exists.
- GPD thresholds and ξ values are plausible.
- Long-return-period maps are monotonic with return period.

### Stochastic simulation

- `stochastic_event_summary.parquet` exists.
- Empirical RP maps exist for all requested return periods.
- PET tables exist.
- Stage 13 did not create dense event cubes as persistent outputs.

### Diagnostics

- Analytical-vs-stochastic plots were rendered.
- Large divergence areas are reviewed.
- Tail-stability flags are reviewed before using long return periods.

---

## 8. Recommended Test Commands

After implementation of tests:

```bash
pytest -q
pytest tests/test_stage05_bias_correction.py -q
pytest tests/test_stage08_event_catalog.py -q
pytest tests/test_stage09_cdf.py -q
pytest tests/test_stage13_stochastic.py -q
```

Suggested categories:

- Unit tests for pure functions.
- Small synthetic raster integration tests.
- Schema tests for outputs.
- Monotonicity tests for return-period maps.
- Sparse safety tests for Stage 13.

---

## 9. Expected Runtime

Approximate final-run runtime:

| Stage group | Runtime driver |
|---|---|
| 01–03 | download bandwidth |
| 04a | CDS queue |
| 04b | GridRad file availability and SHI computation |
| 05–06 | raster I/O and validation |
| 07–12 | raster processing and CDF fitting |
| 13 | stochastic simulation length |
| 15 | map rendering |

Stage 13 should be tested with `--n-years 1000` before running 50,000 years.

---

## 10. Reproducibility Manifest

Each full run should save a manifest similar to:

```json
{
  "model_version": "2.1",
  "run_date": "YYYY-MM-DD",
  "random_seed": 42,
  "stages_run": ["01", "02", "03", "04a", "04b", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15"],
  "calibration_mode": "conditional_with_quantile_fallback",
  "environment_filter": "probabilistic_with_safety_floor",
  "stochastic_years": 50000
}
```

Recommended path:

```text
data/analysis/run_manifest.json
```
