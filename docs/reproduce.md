# Reproduction Guide

**CONUS Hail Catastrophe Model v2.2**

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

ERA5 access is required for Stage 04a. Register for a free Copernicus CDS
account, accept the licence terms for the ERA5 monthly pressure-level and
single-level datasets from their download pages, generate a personal access
token from the CDS profile page, and store it in `~/.cdsapirc` outside the
repository:

```bash
cat > ~/.cdsapirc << CDSEOF
url: https://cds.climate.copernicus.eu/api
key: YOUR_PERSONAL_ACCESS_TOKEN
CDSEOF
chmod 600 ~/.cdsapirc
```

Do not commit this file or paste the token into logs. CDS can authenticate with
a valid token and still reject Stage 04a if the dataset licence terms have not
been accepted for that account.

Accept both dataset licences while signed in to the same CDS account used to
generate the token:

- https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels-monthly-means?tab=download#manage-licences
- https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means?tab=download#manage-licences

The telltale failure is `403 Client Error: Forbidden` with `required licences
not accepted`. That means the credential file is being read but the CDS account
still needs dataset licence acceptance.

Stage 04a submits ERA5 pressure-level requests in bounded yearly chunks, with a
monthly fallback if CDS rejects a year as too large. Completed chunks are kept in
`data/historical/era5/pressure_chunks/`, so interrupted ERA5 runs can resume
without repeating successful downloads.

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
# GridRad: run_pipeline skips 04b and streams downloads inside 04c (see paragraph below).
python run_pipeline.py --only 04c
python run_pipeline.py --only 05 --skip-ml
python run_pipeline.py --only 06
python run_pipeline.py --only 07
python run_pipeline.py --only 08
python run_pipeline.py --only 09
python run_pipeline.py --only 10
python run_pipeline.py --only 11
python run_pipeline.py --only 11b
python run_pipeline.py --only 12
python run_pipeline.py --only 13
python run_pipeline.py --only 14
python run_pipeline.py --only 15
```

**`run_pipeline.py` and GridRad:** on a default full run (and on resumes that start
before stage **04b**), the runner **auto-skips stage 04b** whenever **04c** is in the
plan and calls **04c** with **`--with-04b-download --workers 4`** (per-day download,
four convective days in parallel; GridRad staging removed after each day by default).
Use **`python run_pipeline.py --only 04b`** or **`--from 04b`** for the legacy standalone
NCAR downloader. If you already populated **`gridrad/`** with **04b**, gap-fill from
disk without redundant downloads via **`python scripts/04c_fill_gridrad_gap.py --workers N`**
without **`--with-04b-download`** — **`run_pipeline.py --only 04c`** always passes
**`--with-04b-download`**.

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

## 5. Stage 04b/04c GridRad Setup

By default, **04b** plans and downloads **one convective day at a time** (12 UTC → 12 UTC; lower peak RAM
and a smaller in-flight download plan than the legacy global planner). Use
`--plan-all-days-first` only if you need the old “catalog everything, then download”
schedule. Per-day download threads default to **`--workers 1`**; raise cautiously (NCAR
asks for ≤10 concurrent streams total).

**04c** processes days **sequentially by default** (`--workers 1`). After each day’s
run finishes (output written, skipped, no-data, or error), local GridRad NetCDF trees
for that convective day are **removed** unless you pass **`--keep-gridrad-inputs`**.

**Single-pass (tight disk):** chain 04b’s per-day download inside 04c. With default
**`--workers 1`**, days are strictly sequential. You may set **`--workers N`** with
**`N > 1`** for parallel convective days (each worker has its own session); keep
**`N × --04b-download-workers`** within NCAR throttling guidance.

**Mental model (04b vs 04c workers):** `--workers` on **04c** is the number of **parallel
convective days** (separate processes when `N > 1`). **`--04b-download-workers`** applies
only with **`--with-04b-download`**: it is **within-day** parallel HTTP GETs for that
day’s NetCDF pulls. Rough peak in-flight downloads scale as **`04c_workers × 04b_download_workers`**
(before skips). Stage **04b** alone uses its own `--workers` for within-day GETs only.

| What you want | Command pattern |
|---|---|
| Gap-fill only; GridRad files already on disk | `python scripts/04c_fill_gridrad_gap.py --workers N` (no `--with-04b-download`) |
| Download + gap-fill; one day at a time, max within-day download speed | `--workers 1 --with-04b-download --04b-download-workers M` |
| Download + gap-fill; many days at once | `--workers N --with-04b-download` (keep `N × M` within NCAR limits; often ≤10 concurrent streams) |
| Two-stage pipeline (full 04b archive, then 04c) | `run_pipeline.py --only 04b` then **`python scripts/04c_fill_gridrad_gap.py --workers N`** without `--with-04b-download` (``run_pipeline.py --only 04c`` always streams downloads) |

```bash
python scripts/04c_fill_gridrad_gap.py --with-04b-download
```

GridRad files are staged under (and deleted from, unless `--keep-gridrad-inputs`):

```text
data/historical/gridrad/
data/historical/gridrad_severe/
```

Check availability (after download):

```bash
python scripts/04c_fill_gridrad_gap.py --check-data
```

Download (Stage 04b):

```bash
python run_pipeline.py --only 04b
```

Gap-fill compute (Stage 04c via **`run_pipeline.py`**):

```bash
python run_pipeline.py --only 04c
```

This invokes **`04c_fill_gridrad_gap.py`** with **`--with-04b-download --workers 4`**
by default (see §4). On constrained disks, call the script directly with fewer parallel
days instead — for example **`python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2`**
(~2 concurrent day trees under `gridrad_severe/`, typically ~8–12 GB each before per-day cleanup).
To gap-fill from an existing **`gridrad/`** tree without embedded download, omit
**`--with-04b-download`** (for example **`python scripts/04c_fill_gridrad_gap.py --workers 2`**).

**Monitor gap-fill progress (optional):**

```bash
tail -f logs/04c_fill_gridrad_gap.log
# or logs/04c_fill_gridrad_gap.run.log when started via nohup
```

Gap-fill GeoTIFFs include GDAL tags (`MAX_MESH75_MM`, `ACTIVE_CELLS`) for daily QA.
After any 04c reflectivity-reader fix, delete affected gap-era `mesh_*.tif` files and
re-run 04c for those dates (see `docs/technical_documentation.md` §8.3).

**Daily peak summaries (optional diagnostic):**

```bash
.venv/bin/python scripts/diagnostics/summarize_mesh_daily_peaks.py
```

Writes `data/analysis/mesh_daily_peaks/` (`mesh_daily_peaks.csv`, percentiles, ECDF plot).
Re-run while Stages 02 or 04c are in progress to compare hail distributions by radar era.

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
  "model_version": "2.2",
  "run_date": "YYYY-MM-DD",
  "random_seed": 42,
  "stages_run": ["01", "02", "03", "04a", "04b", "05", "06", "07", "08", "09", "10", "11", "11b", "12", "13", "14", "15"],
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
| 07–12 | raster processing, DEM preparation, and CDF fitting |
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
7. Run stages 07–12. Stage 11b downloads NOAA/NCEI ETOPO 2022 surface elevation and writes `data/analysis/topography/elevation_0.05deg.tif` before Stage 12.
8. Run Stage 13 with 1,000 years.
9. Run Stage 13 with 50,000 years.
10. Run Stage 14 and Stage 15.
11. Archive logs and manifest.
