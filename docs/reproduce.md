# Reproduction Guide

**CONUS Hail Catastrophe Model v2.0**

---

## Prerequisites

1. **Python 3.9+** with packages from `requirements.txt`
2. **AWS CLI or boto3** (no account needed — MYRORSS and MRMS are public buckets)
3. **NCAR RDA account** (free): https://rda.ucar.edu — required for GridRad download
4. **Copernicus CDS account** (free): https://cds.climate.copernicus.eu — required for ERA5
5. **~2 TB disk space** for raw radar data + intermediate products
6. **~16 GB RAM** (peak usage during stochastic catalog generation)

## Setup

```bash
git clone https://github.com/YOUR_ACCOUNT/us-hail-cat-model.git
cd us-hail-cat-model
pip install -r requirements.txt
```

Configure ERA5 access:
```bash
cat > ~/.cdsapirc << CDSEOF
url: https://cds.climate.copernicus.eu/api
key: YOUR-PERSONAL-ACCESS-TOKEN
CDSEOF
```

## Full Pipeline Run

```bash
python run_pipeline.py
```

Total runtime: ~20–40 hours (dominated by downloads). Resumable at any stage.

## Stage-by-Stage

### Stages 01–02: Radar Data Download
```bash
python run_pipeline.py --only 01    # MYRORSS (1998–2011), ~2–6 hrs
python run_pipeline.py --only 02    # MRMS (2020–present), ~3–8 hrs
```
Output: `data/historical/mesh_0.05deg/YYYY/mesh_YYYYMMDD.tif`

### Stage 03: SPC Reports
```bash
python run_pipeline.py --only 03
```
Output: `data/historical/spc/YYYY/`

### Stage 04a: ERA5 Isotherms
```bash
python run_pipeline.py --only 04a
```
Requires CDS credentials. Output: `data/historical/era5/era5_monthly_isotherms_conus.nc`

### Stage 04b: GridRad Gap Fill
**Prerequisite:** Download GridRad data from NCAR RDA to `data/historical/gridrad/`. Use their wget scripts for bulk download (~1.5 TB for 2012–2019).

```bash
python scripts/04b_fill_gridrad_gap.py --check-data    # verify files exist
python run_pipeline.py --only 04b                       # compute MESH75
```
Output: Same path as stages 01–02 (files interleave)

### Stage 05: Bias Correction
```bash
python run_pipeline.py --only 05
```
Internally builds cross-calibration from overlap, then applies corrections.
Output: `data/historical/mesh_0.05deg_corrected/YYYY/mesh_YYYYMMDD.tif`

### Stage 06: Validation
```bash
python run_pipeline.py --only 06
```
Output: `data/historical/validation/` (CSVs, summary, figures)

### Stages 07–15
```bash
python run_pipeline.py --from 07
```

Or individually:
```bash
python run_pipeline.py --only 07    # Daily climatology (~10 min)
python run_pipeline.py --only 08    # Event catalog (~15 min)
python run_pipeline.py --only 09    # CDF fitting with regional GPD (~30 min)
python run_pipeline.py --only 10    # Spatially-pooled CDF rebuild (~30 min)
python run_pipeline.py --only 11    # Occurrence probabilities (~10 min)
python run_pipeline.py --only 12    # CONUS mask + topography (~10 min)
python run_pipeline.py --only 13    # 50,000-yr stochastic catalog (~3 hrs)
python run_pipeline.py --only 14    # Vulnerability curves (~5 min)
python run_pipeline.py --only 15    # All figures (~45 min)
```

**Stage 12 note:** For topographic correction, optionally provide a DEM at
`data/analysis/topography/elevation_0.05deg.tif`. Without it, a uniform
correction factor of 1.0 is used.

**Stage 13 note:** Produces empirical RP maps that should be compared against
the analytical RP maps from stages 09–10. Divergence at long return periods
flags cells where the GPD tail may be misspecified.

## Validation

Validate all outputs without re-running:
```bash
python run_pipeline.py --validate
```

## Data Paths

All data under `data/` is gitignored. The three top-level directories are:
- `data/historical/` — radar, SPC, corrected MESH, climatology, events, validation
- `data/analysis/` — CDF parameters, calibration, occurrence, topography, vulnerability
- `data/stochastic/` — catalog, return period maps, EP tables
