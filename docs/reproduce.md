# Reproduction Guide

**CONUS Hail Catastrophe Model v2.1**

---

## 1. Environment

Recommended:

- Python 3.10+.
- At least 16 GB RAM; more is recommended for Stage 10 and Stage 13.
- Disk space sufficient for radar data and outputs.
- Copernicus CDS credentials for ERA5.
- NCAR RDA access for GridRad files.

Install:

```bash
git clone https://github.com/YOUR_ACCOUNT/us-hail-cat-model.git
cd us-hail-cat-model

python3.10 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

ERA5 credentials:

```bash
cat > ~/.cdsapirc << CDSEOF
url: https://cds.climate.copernicus.eu/api
key: YOUR-PERSONAL-ACCESS-TOKEN
CDSEOF
```

---

## 2. Pre-Run Checks

Run these before the full model:

```bash
python -m py_compile run_pipeline.py scripts/*.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

These check syntax, tests, and pipeline stage selection.

---

## 3. Full Run

The pipeline is stage-based and should be resumable. For first production runs,
prefer the staged execution order below instead of a single unattended command.

---

## 4. Stage-by-Stage Execution

```bash
python run_pipeline.py --only 01
python run_pipeline.py --only 02
python run_pipeline.py --only 03
python run_pipeline.py --only 04a
python run_pipeline.py --only 04b
python run_pipeline.py --only 05 --skip-ml
python run_pipeline.py --only 06
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

After Stage 01, inspect the MYRORSS source manifest before continuing:

```bash
python - <<'PY'
import csv
from collections import Counter

with open("data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv", newline="") as f:
    counts = Counter(row["status"] for row in csv.DictReader(f))
print(counts)
PY
```

The manifest distinguishes `missing_source` days from `no_hail_pixels` days.
Both can produce all-zero daily GeoTIFFs, so do not infer source availability
from raster file size or raster values alone.

Run from a stage:

```bash
python run_pipeline.py --from 07
```

Skip stages:

```bash
python run_pipeline.py --skip 14,15
```

---

## 5. Stage 04b GridRad Setup

GridRad files should be placed in:

```text
data/historical/gridrad/
data/historical/gridrad_severe/
```

Check availability:

```bash
python scripts/04b_fill_gridrad_gap.py --check-data
```

Run:

```bash
python run_pipeline.py --only 04b
```

---

## 6. Stage 05 Modes

Default:

```bash
python run_pipeline.py --only 05
```

Force deterministic fallback:

```bash
python run_pipeline.py --only 05 --skip-ml
```

Use `--skip-ml` for the first full production pass unless the optional
calibration artifacts have already been reviewed.

External model retraining workflow:

```bash
python run_pipeline.py --only 05 --retrain-models
```

Optional artifacts:

```text
data/analysis/calibration/gridrad_cqm_model.pkl
data/analysis/calibration/hail_filter_model.pkl
```

If artifacts are absent, the deterministic workflow should still run.

---

## 7. Stage 13 Development and Final Runs

Smoke test:

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 1000
```

Final run:

```bash
python scripts/13_generate_stochastic_catalog.py --n-years 50000
```

Stage 13 must remain sparse-safe.

---

## 8. Validation After Outputs Exist

```bash
python run_pipeline.py --validate
```

Individual validation examples:

```bash
python scripts/08_build_event_catalog.py --validate
python scripts/09_fit_cdf_regional.py --validate
python scripts/13_generate_stochastic_catalog.py --validate
```

---

## 9. Quality-Control Checklist

### Calibration

- `gridrad_quantile_map.npz` exists.
- Optional ML artifact use is logged.
- Correction ratios are plausible.
- Source distributions after correction are comparable.

### Filtering

- Pixel counts do not collapse unexpectedly.
- Subtropical warm-season noise is reduced.
- Optional probabilistic filter diagnostics are reviewed if present.

### Event catalog

- Event CSV exists.
- Sparse NPZ exists.
- No duration cap violations.
- Sparse arrays have matching lengths.
- Event counts by year are plausible.

### CDF fitting

- `cdf_parameters.npz` exists.
- `threshold_selection.csv` exists.
- ξ values are plausible.
- RP maps are broadly monotonic.

### Stochastic

- Smoke test succeeds.
- 50,000-year run completes.
- PET outputs exist.
- RP maps exist.
- Stage 13 did not create persistent dense event cubes.

### Diagnostics

- Validation figures exist.
- Analytical vs stochastic plots exist.
- Large divergence regions are reviewed.

---

## 10. Suggested Run Manifest

Recommended path:

```text
data/analysis/run_manifest.json
```

Example:

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

---

## 11. Expected Runtime

| Stage group | Runtime driver |
|---|---|
| 01–03 | download bandwidth |
| 04a | CDS queue |
| 04b | GridRad availability and SHI computation |
| 05–06 | raster I/O and validation |
| 07–12 | raster processing and CDF fitting |
| 13 | stochastic years |
| 15 | figure rendering |

---

## 12. Recommended First Full Run Order

1. Run syntax and tests.
2. Run `--dry-run`.
3. Run Stage 01 and inspect `manifest_stage01_myrorss.csv`.
4. Run stages 02, 03, 04a, and 04b.
5. Run Stage 05 with `--skip-ml` first.
6. Run Stage 06 validation.
7. Run stages 07–12.
8. Run Stage 13 with 1,000 years.
9. Run Stage 13 with 50,000 years.
10. Run Stage 14 and Stage 15.
11. Archive logs and manifest.
