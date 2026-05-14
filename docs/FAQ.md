# FAQ — CONUS Hail Catastrophe Model v2.1

**Related:** `docs/methodology.md`, `docs/technical_documentation.md`, `docs/uncertainty.md`, `docs/REVIEW_2026-05-01.md §B.7`

---

## General Model Questions

**Q: What does this model produce?**

Gridded hail hazard return-period maps and a 50,000-year stochastic event catalog for the continental United States. It does not produce financial loss estimates, claims predictions, or exposure-weighted outputs. It is a hazard model, not a catastrophe loss model.

**Q: What is the spatial resolution?**

0.05 degrees (~5.5 km) in EPSG:4326. The grid is 520 rows × 1180 columns. This resolution is fixed in v2.1; changing it requires a version bump and full rerun.

**Q: What time period does the model cover?**

The observational record runs from April 1998 (MYRORSS start) through the present MRMS operational era. Three radar sources are spliced: MYRORSS (Apr 1998–Dec 2011), GridRad/GridRad-Severe (Jan 2012–Oct 2019), and operational MRMS (Oct 2020–present). The 2019–2020 gap is not covered by any current source.

**Q: What is the primary hazard variable?**

MESH75 in millimeters. MESH75 is derived from the Severe Hail Index using the corrected relationship from Murillo and Homeyer (2021): `MESH75 = 15.096 × SHI^0.206`. It is interpreted as a radar-based estimate of hail size at the 75th-percentile severity for the storm.

**Q: How should I interpret return periods?**

A 100-year return period at a grid cell means the model estimates a 1% annual probability of MESH75 exceeding that level at that cell. Return periods above ~500 years are extrapolative — they exceed the observational record and depend heavily on the fitted tail behavior.

---

## Data and Sources

**Q: Why not use SPC hail reports as the primary hazard input?**

SPC reports are spatially and temporally biased. They depend on where people are present (population density), road networks, spotter motivation, operational reporting criteria, and how those criteria changed over time (notably the 2010 threshold change from 0.75 to 1.0 inch). Radar MESH is imperfect but provides spatially continuous, unbiased coverage across rural and urban areas. See `docs/methodology.md §2.1` and the literature review for citations.

**Q: Can I use SPC reports for anything in this model?**

Yes — validation. SPC reports are used in Stage 06 to check that corrected MESH75 fields are directionally consistent with surface reports, and in Stage 07 to diagnose regional biases. They are never used as the hazard surface.

**Q: Why are three different radar sources used?**

No single radar product covers the full 1998–present period. MYRORSS is the best available reanalysis of the early archive; GridRad fills the middle period; MRMS is the operational product. Each source has different retrieval methods, so Stage 05 calibrates them toward a common distribution before pooling.

**Q: What does "MESH75" mean compared to plain "MESH"?**

The original MESH (Witt et al. 1998) was designed for warning support, not climatological estimation. It tends to overestimate hail size at the high end. MESH75 is a recalibrated version that better represents the 75th percentile of observed hail. v2.1 uses MESH75 throughout after Stage 05 calibration.

**Q: What is ERA5 used for?**

Monthly ERA5 0°C and −20°C isotherm heights are used in Stage 04c to compute Severe Hail Index (SHI) from GridRad reflectivity profiles. They may also support optional environmental filtering in Stage 05. ERA5 is not used as a hazard input — it provides thermodynamic context.

---

## Pipeline and Architecture

**Q: What does each stage do?**

See `docs/technical_documentation.md` for per-stage implementation notes. In brief:

| Stage | Role |
|---|---|
| 01 | Download MYRORSS, write daily GeoTIFFs + manifest |
| 02 | Download MRMS MESH GRIB2, write daily GeoTIFFs |
| 03 | Download SPC hail reports |
| 04a | Download ERA5 isotherms |
| 04b | Download GridRad / GridRad-Severe inputs (NCAR RDA/GDEX); default is one day at a time with `--workers 1` per day |
| 04c | Compute SHI/MESH75 from GridRad reflectivity + ERA5; default sequential days; optional per-day input cleanup unless `--keep-gridrad-inputs` |
| 05 | Calibrate all sources, apply environmental filter |
| 06 | Validate corrected MESH vs SPC reports |
| 07 | Build hail climatology (annual exceedance frequency) |
| 08 | Build sparse historical event catalog |
| 09 | Fit regional GPD extreme-value distributions |
| 10 | Spatially smooth CDFs for stable return-period maps |
| 11 | Build annual exceedance probability maps |
| 11b | Download NOAA/NCEI ETOPO 2022 DEM and resample to the model grid |
| 12 | Apply CONUS mask and topographic correction |
| 13 | Generate 50,000-year stochastic event catalog |
| 14 | Apply vulnerability curves (placeholder) |
| 15 | Render diagnostic figures |

**Q: How do I run the pipeline?**

From the repo root:
```bash
python run_pipeline.py --only 01       # single stage
python run_pipeline.py --from 06       # stages 06 through 15
python run_pipeline.py --skip 14,15    # skip stages
python run_pipeline.py --dry-run       # validate without executing
python run_pipeline.py --validate      # re-validate all outputs
```

Always run the pre-run checks before a full execution:
```bash
python -m py_compile run_pipeline.py scripts/*.py
ruff check .
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
python run_pipeline.py --dry-run
```

**Q: What is `--skip-ml` for?**

Stage 05 has optional machine-learning components for conditional GridRad calibration (`gridrad_cqm_model.pkl`) and probabilistic environmental filtering (`hail_filter_model.pkl`). These artifacts may not exist on a fresh installation. `--skip-ml` forces Stage 05 to use deterministic quantile mapping and hard-threshold filtering. This is the recommended mode for first runs and for reproducible baselines.

**Q: Stage 04c: what is the difference between `--workers` and `--04b-download-workers`?**

On **`04c_fill_gridrad_gap.py`**, **`--workers`** is how many **calendar days** run in parallel (separate processes when `N > 1`). **`--04b-download-workers`** only applies with **`--with-04b-download`**: it parallelizes **HTTP GETs within one day’s** `download_for_day` call. For throttling, think **`04c_workers × 04b_download_workers`** (see `docs/reproduce.md` §5 table). Stage **04b**’s own **`--workers`** flag is unrelated—it only affects within-day GETs when you run **04b** as a standalone script.

**Q: Why must Stage 13 be "sparse-safe"?**

The historical event catalog contains thousands of events. Each event covers at most a fraction of the 520×1180 grid. If every event were stored as a full dense grid, the stochastic simulation would require hundreds of gigabytes of RAM (`n_events × 520 × 1180 × 4 bytes ≈ 10,000 × 614,000 × 4 = ~24 GB` for a modest catalog). Sparse storage (rows/cols/vals per event) reduces this by two to three orders of magnitude. See `docs/methodology.md §2.3`.

**Q: What is `event_peaks.npz`?**

The Stage 08 output that stores each historical event as sparse arrays: `rows`, `cols`, and `vals` for every cell in the event footprint, keyed by `event_id`. This is the authoritative event store consumed by Stage 13. Never reconstruct these events into dense grids.

---

## Statistics and Methodology

**Q: What extreme-value distribution is used?**

The Generalized Pareto Distribution (GPD) is fit to exceedances above a per-region threshold using L-moments (Hosking and Wallis 1997). L-moments are preferred over maximum likelihood for the small regional samples available after regional pooling.

**Q: What is regional pooling, and why is it needed?**

Many CONUS grid cells have only a few decades of observations. Fitting a GPD separately to each cell would produce unstable shape parameters (ξ). Regional pooling (Stage 09) groups cells into K-means clusters, estimates a pooled ξ per region from the combined exceedances, and uses cell-specific scale parameters (σ). The default is 6 regions, following Allen et al. (2015) with one extra for the Front Range.

**Q: What is the GPD threshold?**

The damage threshold below which tail fitting begins. The default is 50.8 mm (2.0 inches). Stage 09 runs automated Mean Residual Life (MRL) diagnostics and produces `threshold_selection.csv` with per-region KS, MRL-linearity, stability, and count-penalty scores. The automated threshold is preferred over the fixed default where data support it.

**Q: What are the two RP products?**

1. **Analytical RP maps** (Stage 10–12): derived from the fitted GPD CDF at each grid cell. Stable and smooth but depends on the parametric tail assumption.
2. **Stochastic RP maps** (Stage 13): derived empirically from ranked peak MESH75 values across 50,000 simulated years. Model-free but subject to Monte Carlo variability at long return periods.

Agreement between the two is an internal consistency check. Large divergence at RP ≤ 500 yr is a P0 flag.

**Q: How is the stochastic catalog generated?**

Stage 13 resamples historical events with replacement, scales intensities using a calibrated sigma perturbation, and applies small spatial translations (±3 grid cells, ≈ ±16.5 km). Each simulated year draws events from a Poisson annual count. The 50,000-year catalog represents 50,000 independent simulated hail seasons.

**Q: What is the topographic correction?**

Stage 12 applies:
```
factor = 1.0 + α × (elevation_km / freezing_level_km)
```
with α = 0.25, clipped to [1.0, 1.25] when ERA5 freezing level is available, [1.0, 1.20] otherwise. The coefficient 0.25 is empirically motivated by Front Range hail climatology but does not have a direct literature citation in v2.1 — see `docs/REVIEW_2026-05-01.md §E.8`. Sensitivity sweeps are defined in `docs/sensitivity.md §4`.

Stage 11b prepares the elevation input from NOAA/NCEI ETOPO 2022 60 arc-second
surface elevation and writes `data/analysis/topography/elevation_0.05deg.tif`.
If that file is absent, Stage 12 falls back to a neutral topographic correction.

---

## Uncertainty and Limitations

**Q: How confident are the 500-year and 1,000-year return levels?**

Low confidence. The observational record is ~25 years. Anything above ~500-year RP depends entirely on the assumed tail shape (ξ) from the GPD. ξ is pooled regionally to reduce variance, but it remains uncertain. Treat RP > 500 yr as a sensitivity scenario rather than a calibrated estimate.

**Q: Is climate non-stationarity modeled?**

No. v2.1 assumes stationarity: the fitted tail and simulated catalog represent historical average conditions. There is scientific evidence that hail environments are changing (Allen, Tippett, Sobel 2015). Non-stationarity could be addressed in a future version using time-varying EVT parameters or scenario-based perturbations.

**Q: Why are vulnerability curves labeled "placeholder"?**

Stage 14 implements a generic mean-damage-ratio (MDR) curve for five construction classes, derived from published literature rather than claims data. These curves have not been validated against insurance claims. They exist to allow end-to-end pipeline testing and scenario loss approximation. They should not be used for underwriting or rate-setting without calibration.

**Q: What is the biggest source of uncertainty?**

See `docs/uncertainty.md` for the six-category uncertainty budget. In short: source homogeneity (the three radar sources may not be fully comparable after calibration) and extreme-tail extrapolation are the two largest contributors at long return periods. For RP ≤ 100 yr, sampling variance in the GPD shape parameter is the dominant uncertainty.

**Q: Are spatial correlations between cells modeled?**

Only implicitly through the stochastic event footprints. Stage 13 resamples real event footprints and applies small perturbations, which preserves the spatial structure of each individual event. However, there is no formal max-stable or copula model for the joint tail across cells. This means the model may underestimate aggregate exceedance probabilities for simultaneous large-area events. See `docs/uncertainty.md §4` and the literature review.

---

## Common Errors

**Q: Stage 13 crashes with a MemoryError.**

This is almost certainly a sparse-safety violation. Check that no intermediate step reconstructs events as a dense `(n_events, 520, 1180)` array. Translation, scaling, and perturbation must operate on `rows, cols, vals` directly. See `docs/ai_instructions.md §3.1`.

**Q: Stage 05 says it cannot find the ML model file.**

Run with `--skip-ml`. The ML artifacts (`gridrad_cqm_model.pkl`, `hail_filter_model.pkl`) are optional. Use `--retrain-models` if you want to fit them from existing Stage 05 intermediate outputs.

**Q: Stage 01 produces all-zero GeoTIFFs for some days.**

This is expected for days with no hail pixels or missing source files. Do not diagnose source availability from the GeoTIFF values alone. Check `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`. Status `missing_source` means no MYRORSS NetCDF objects existed for that day; `no_hail_pixels` means files existed but no active cells were found.

**Q: Why are some Stage 01 daily maxima exactly below 300 mm?**

Stage 01 applies a physical QA bound of 300.0 mm. Non-finite, negative, or
larger raw MYRORSS values are treated as source artifacts and reset to `0.0`.
The repair pass can be rerun with `python scripts/01_download_myrorss.py --qa-only`.
The same cap is enforced for MRMS, GridRad-derived gap-fill, and Stage 05
corrected MESH75 outputs during processing and validation.

**Q: `git commit` hangs or fails with a lock error.**

Check whether a git process is still running before removing any lock. If no
git process is active, remove `.git/index.lock` and retry the command. Do not
remove a lock while another git operation is in progress.

**Q: Tests fail with import errors for stage scripts.**

The test suite uses `importlib.util.spec_from_file_location` in `tests/conftest.py` to load stage scripts. If a stage script defines module-level code that runs immediately on import (e.g., large data loads), the test will fail. Stage-level code should be guarded under `if __name__ == "__main__"` or deferred to function calls.

---

## Development and Contribution

**Q: How do I add a new sensitivity parameter?**

1. Add an entry to `docs/sensitivity.md` with the stage, default, justification, sweep range, and expected output.
2. Add a CLI argument to the relevant stage script if not already present.
3. Write a sweep driver script or notebook in `scripts/` or `notebooks/`.
4. Update `docs/technical_documentation.md` if the parameter changes documented behavior.

**Q: How do I add a new output file?**

1. Write the output in the stage script with a consistent path from `scripts/_config.py`.
2. Add the schema to `docs/data_dictionary.md` (column names, units, format, stage that writes it).
3. Add a validation check in the stage's test file.
4. Update `run_pipeline.py --validate` logic if relevant.

**Q: Can I change the grid resolution?**

Not in v2.1. The 0.05° grid is a versioned model assumption. Any change requires regenerating all downstream outputs and bumping the model version to v2.2 or v3.0 depending on scope. See `docs/methodology.md §4`.

**Q: Where is the documentation index?**

`docs/README.md` provides a complete reading path with links to all documentation files.
