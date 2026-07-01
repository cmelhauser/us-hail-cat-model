# FAQ — CONUS Hail Catastrophe Model v2.2

**Related:** `docs/methodology.md`, `docs/technical_documentation.md`, `docs/uncertainty.md`, `docs/REVIEW_2026-05-01.md §B.7`

---

## General Model Questions

**Q: What does this model produce?**

Gridded hail hazard return-period maps and a 50,000-year stochastic event catalog for the continental United States. It does not produce financial loss estimates, claims predictions, or exposure-weighted outputs. It is a hazard model, not a catastrophe loss model.

**Q: What is the spatial resolution?**

0.05 degrees (~5.5 km) in EPSG:4326. The grid is 520 rows × 1180 columns. This resolution is fixed; changing it requires a version bump and full rerun.

**Q: What time period does the model cover?**

The observational record runs from April 1998 (MYRORSS start) through the present MRMS operational era. Three radar sources are spliced: MYRORSS (Apr 1998–Dec 2011), GridRad/GridRad-Severe (Jan 2012–13 Oct 2020), and operational MRMS (14 Oct 2020–present). Stage **04c** processes **convective days** (12 UTC → 12 UTC) through label **2020-10-13**; there is no radar gap-fill after that date. See `docs/methodology.md` §2.6.

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
| 04c | Compute SHI/MESH75 from GridRad reflectivity + ERA5; severe-first download when `--with-04b-download`; default sequential days; optional per-day input cleanup unless `--keep-gridrad-inputs` |
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

On **`04c_fill_gridrad_gap.py`**, **`--workers`** is how many **convective days** run in parallel (separate processes when `N > 1`). **`--04b-download-workers`** only applies with **`--with-04b-download`**: it parallelizes **HTTP GETs within one convective day’s** download call (`download_for_day_adaptive` → `download_for_day`). For throttling, think **`04c_workers × 04b_download_workers`** (see `docs/reproduce.md` §5 table). Stage **04b**’s own **`--workers`** flag is unrelated—it only affects within-day GETs when you run **04b** as a standalone script.

**Q: Does Stage 04c download both GridRad and GridRad-Severe for every day?**

No. With **`--with-04b-download`**, Stage **04c** uses a **severe-first** policy (`download_for_day_adaptive` in **04b**). If GridRad-Severe exists in the THREDDS catalog for the convective window, only severe files are downloaded. Hourly GridRad is fetched only when severe is unavailable or staged severe files do not cover the full 12 UTC → 12 UTC window. Hourly fallback order is **d841000** (V3.1, through 2017) then **d841001** (V4.2 warm-season hourly, Apr–Aug 2018–2021). Processing mirrors this: complete severe coverage uses severe only; partial severe merges hourly timesteps for gaps (`SOURCE=gridrad-severe-5min+hourly-fill`). Standalone **`04b`** still supports explicit **`--hourly-only`** / **`--severe-only`** flags.

**Q: Why do many gap-era days still show `missing_source` in the manifest?**

Three NCAR products cover the gap era with different calendars: **GridRad-Severe** (~100 severe events per year), **GridRad V3.1 hourly** (through 2017, all months), and **GridRad V4.2 warm-season hourly** (Apr–Aug only, 2008–2021). Off-season days and non-severe warm-season days may legitimately have no GridRad on NCAR. After the **d841001** fallback (v2.2.1+), re-run **`--missing-only`** backfill to pick up additional Apr–Aug 2018–2020 days that previously logged `no_data`.

**Q: Why did many GridRad gap-fill days show zero hail (`active_cells=0`) even when NetCDFs downloaded successfully?**

Stage **04c** must use **reflectivity in dBZ** for SHI. NCAR GridRad v3/v4 files usually store that as sparse **`Reflectivity(Index)`** plus an **`index`** vector. The 3-D field **`Nradecho`** is an echo mask (values typically well below 40 dBZ), not reflectivity. An older reader that treated **`Nradecho`** as dBZ failed the **`Z_THRESHOLD`** (40 dBZ) test on most hourly-only days. The fix reconstructs 3-D reflectivity from sparse **`Reflectivity`**, normalizes longitudes from 0–360°, and writes diagnostic GDAL tags (`MAX_MESH75_MM`, `ACTIVE_CELLS`). **Re-run:** delete affected `mesh_YYYYMMDD.tif` gap files and re-run **04c** for those dates (see `docs/technical_documentation.md` §8.3).

**Q: Stage 04c failed with "No space left on device" — what should I do?**

Stop the run, delete stale staging under `data/historical/gridrad/by_convective_day/` and `data/historical/gridrad_severe/by_convective_day/` for the labels in progress (gap-fill GeoTIFFs under `mesh_0.05deg/` are kept). Restart with fewer parallel days: **`python scripts/04c_fill_gridrad_gap.py --with-04b-download --workers 2`** (or `1`). `run_pipeline.py --only 04c` always passes **`--workers 4`**, which can hold up to four full convective-day trees (~8–12 GB each) before per-day cleanup. See `docs/RUN_NOTES.md` and `docs/technical_documentation.md` §8.4.

**Q: Why must Stage 13 be "sparse-safe"?**

The historical event catalog contains thousands of events. Each event covers at most a fraction of the 520×1180 grid. If every event were stored as a full dense grid, the stochastic simulation would require hundreds of gigabytes of RAM (`n_events × 520 × 1180 × 4 bytes ≈ 10,000 × 614,000 × 4 = ~24 GB` for a modest catalog). Sparse storage (rows/cols/vals per event) reduces this by two to three orders of magnitude. See `docs/methodology.md §2.3`.

**Q: What is `event_peaks.npz`?**

The Stage 08 output that stores each historical event as sparse arrays: `rows`, `cols`, and `vals` for every cell in the event footprint, keyed by `event_id`. This is the authoritative event store consumed by Stage 13. Never reconstruct these events into dense grids.

**Q: Stage 08 reports ~300 events per year. Is that reasonable?**

Stage 08 counts **CONUS-wide** days/clusters with at least one cell ≥ **`EVENT_ACTIVE_THRESH_MM` (29.0 mm)** in v2.2.1. The prior 25.4 mm threshold yielded ~306 events/yr and ~344 national any-cell MESH days/yr with weak seasonality vs SPC. At **29 mm**, per-cell Great Plains maxima are **~3.7 hail days/yr** (vs **~5.5** at 25.4 mm), closer to Cintineo et al. (2012) and Wendt & Jirak (2021). Run `scripts/diagnostics/hail_day_climatology.py` for full threshold sensitivity; see `docs/methodology.md` §2.7 and §8.4.

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

The 0.05° grid remains fixed. **v2.2** changed the **temporal** definition of a daily raster to a **12 UTC → 12 UTC convective day** (see `docs/methodology.md` §2.6). That requires re-running Stages 01, 02, 04c, and downstream stages; archived v2.1 calendar-UTC GeoTIFFs are not interchangeable. Further grid or day-definition changes need a version bump and full rerun.

**Q: Where is the documentation index?**

`docs/README.md` provides a complete reading path with links to all documentation files.
