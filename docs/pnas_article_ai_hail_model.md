# Scientific Infrastructure at Agent Speed: An Open Source US Hail Hazard Model

**Draft manuscript for PNAS-style submission**

**Working title:** Scientific Infrastructure at Agent Speed: An Open Source US Hail Hazard Model  
**Article type:** Perspective-informed research article / computational science case study  
**Status:** Draft ready for final figures/discussion — Stage 01 MYRORSS coordinate-fix re-ingest **complete** (2026-07-08); Stages **05–14** rebuilding (`hail_from05`). Prior v2.2.1 hazard numbers below are **provisional placeholders** until the rebuild finishes.  
**Figures:** Regenerate with `scripts/diagnostics/render_pnas_article_figures.py` and Stage 14 after pipeline completion → `docs/figures/pnas/`  
**Target journal:** Proceedings of the National Academy of Sciences (PNAS)  

---

## Author Line

**Christopher Melhauser, Ph.D.**

**Affiliations:** Independent Researcher. Google Scholar: https://scholar.google.com/citations?user=uIXGJ9AAAAAJ&hl=en

**Corresponding author:** Christopher Melhauser (christopher.melhauser@gmail.com)

---

## Classification

Physical Sciences; Sustainability Science; Computer Sciences; Applied Physical Sciences

---

## Keywords

Artificial intelligence; catastrophe modeling; hail; severe convective storms; radar climatology; extreme value theory; reproducible science

---

## Significance Statement

Catastrophe models are usually built by specialized teams over long development cycles. This study describes a reproducible, radar-first US hail catastrophe hazard model built from public data through a human-directed AI workflow. The pipeline combines MYRORSS, GridRad, MRMS, ERA5, and SPC data to estimate hail occurrence, return periods, and stochastic event behavior, while preserving source provenance that distinguishes missing-source days from source-present no-hail days. Beyond the hail results, the study documents a mode of scientific software development in which frontier AI agents support literature synthesis, implementation, testing, data QA, documentation, and long-run monitoring under human scientific responsibility.

---

## Abstract

Artificial intelligence is beginning to alter not only how scientific results are analyzed, but how scientific infrastructure is built. We present a case study in AI-assisted catastrophe model development: a US hail hazard model constructed as a fully automated, reproducible pipeline using frontier language-model agents under human direction. The model ingests public radar and environmental datasets, including MYRORSS, GridRad or GridRad-Severe, operational MRMS, ERA5 isotherm fields, and SPC hail reports for validation. It builds a 0.05 degree CONUS hail archive of **9,797** convective days (1998–2026), calibrates radar-derived MESH to MESH75, constructs sparse historical hail events at a **29 mm** skill threshold, fits regional extreme-value models with automated threshold diagnostics, and produces analytical and **50,000-year stochastic** return-period maps. [*Final event counts, SPC validation pairs, POD, and stochastic catalog size are frozen after the 2026-07 Stages 05–14 rebuild on the corrected MYRORSS archive; provisional prior-run figures remain in Results.*] Literature-aligned diagnostics—including per-cell hail-day climatology, source-transition peak distributions, and era-pooled calibration ECDFs—support threshold and splice-date choices. We describe both the scientific model and the development process: literature review, code generation, debugging, testing, documentation, run monitoring, and methodological hardening performed with `claude-sonnet-4-6` and `claude-opus-4-6` (Anthropic, accessed May 2026) and `gpt-5.5-medium` (OpenAI, accessed May 2026). This study frames AI-assisted model building as a reproducible scientific workflow rather than a code-generation novelty.

---

## Introduction

Severe convective storms are among the most frequent and costly natural hazards in the United States, and hail is a major contributor to insured loss. Yet hail hazard remains difficult to model because direct observations are incomplete, storm reports are biased by human presence and reporting practices, radar products require calibration, and long-return-period estimation must extrapolate from a short homogeneous record.

At the same time, scientific software development is entering a new phase. Frontier language models can read code, generate tests, inspect documentation, design workflows, reason over literature, and operate long-running computational processes. The relevant scientific question is no longer whether AI can write isolated functions. It is whether AI can help build, document, validate, and maintain a nontrivial end-to-end scientific model under human supervision.

This paper presents a concrete case study: the construction of a US hail catastrophe hazard model using AI-assisted development. The work has two linked contributions. First, it describes a radar-first hail model that converts public atmospheric data into gridded hazard, return-period maps, and stochastic event catalogs. Second, it documents the process by which AI agents were used to accelerate literature review, pipeline implementation, debugging, testing, documentation, data-quality review, and run monitoring.

The title *Scientific Infrastructure at Agent Speed* foregrounds a practical question: can frontier AI agents compress the calendar time required to build auditable hazard-model infrastructure, when a human scientist retains direction and accountability? The open-source US hail model is the demonstration artifact—not a black-box output, but a runnable repository with explicit assumptions, tests, validation commands, source-provenance records, and documentation.

### Relationship to prior work

The hail-science contribution builds on four mature literatures. The first is the literature on human hail-report bias, which shows that severe-hail reports are shaped by population, roads, observer practices, report-size rounding, and reporting thresholds (Allen and Tippett 2015; Blair et al. 2011, 2017). The second is radar-based hail estimation, including the original Severe Hail Index and MESH algorithm (Witt et al. 1998), corrected MESH75 relationships (Murillo and Homeyer 2019), MYRORSS (Williams et al. 2022), GridRad (Bowman and Homeyer 2017; Murillo et al. 2021), and operational MRMS climatologies (Smith et al. 2016; Wendt and Jirak 2021). The third is extreme-value analysis for rare environmental hazards, including peaks-over-threshold models and generalized Pareto tails (Pickands 1975; Balkema and de Haan 1974; Coles 2001), regional pooling and L-moments (Hosking and Wallis 1997), threshold diagnostics (Scarrott and MacDonald 2012), and spatial-extremes warnings (Davison et al. 2012; Cooley et al. 2007). The fourth is catastrophe-model practice: sparse event footprints, stochastic catalogs, vulnerability, and uncertainty communication (Grossi and Kunreuther 2005; Brown et al. 2015; Miralles et al. 2023).

The AI-process contribution builds on a rapidly emerging literature on large language models as scientific assistants and agents. Recent systems have demonstrated tool-using agents for chemistry (Boiko et al. 2023), multi-agent scientific collaboration (Swanson et al. 2025), and autonomous open-ended discovery frameworks (Lu et al. 2024). These studies show that AI systems can contribute to parts of scientific work, but most are either benchmark-oriented, laboratory-specific, or focused on autonomous discovery within a narrow scaffold. This manuscript instead studies an applied scientific-infrastructure build: a human-directed, multi-month repository that combines literature review, scientific modeling, data engineering, CI, documentation, long-running execution, and manuscript preparation, with disclosure and human accountability consistent with current journal policy (Proceedings of the National Academy of Sciences 2026).

The contribution is therefore integrative rather than algorithmically singular. Radar hail estimators, extreme-value models, stochastic event catalogs, and AI research agents each have separate precedents. The novelty of this study is their combination in a transparent public-data hazard-model pipeline that exposes the scientific assumptions, source-coverage status, validation checks, code changes, and reproducibility controls required to evaluate the work.

---

## Conceptual Framework

### AI-assisted scientific model construction

The workflow was organized around human-directed AI agents. The human operator provided scientific intent, methodological preferences, repository goals, and acceptance criteria. AI agents performed codebase review, implementation, documentation expansion, literature synthesis, pipeline monitoring, and debugging. This creates a hybrid development loop:

```text
scientific intent -> AI-assisted implementation -> automated validation
-> human review -> model hardening -> documented pipeline
```

This loop differs from ordinary code completion in three ways. First, the AI system maintained repository-level context across many files and stages. Second, it participated in operational execution, including long-running pipeline monitoring. Third, it produced not only code, but also scientific documentation, methodology review, test scaffolding, and reproducibility notes.

### Model-building objective

The modeling objective was to build a public-data hail hazard model rather than a proprietary loss model. The target outputs were:

- corrected daily MESH75 rasters;
- a source-coverage manifest distinguishing missing-source days from no-hail days;
- validation summaries against SPC hail reports;
- day-of-year and annual climatology;
- sparse historical event catalogs;
- analytical return-period maps;
- empirical stochastic return-period maps;
- diagnostic figures;
- hazard-only scope (no exposure or loss module in the repository).

---

## Data

The model uses radar-derived hail information as the primary hazard field. Human hail reports are used for validation, not as the gridded hazard truth.

### MYRORSS

MYRORSS (Williams et al. 2022) provides the early historical radar reanalysis period from April 1998 through December 2011. The pipeline reads both plain `.netcdf` and `.netcdf.gz` archive objects, decodes sparse source files, and accumulates the cell-wise maximum MESH over **convective days** defined as **12 UTC → 12 UTC** (label = date at window start), then aggregates to a 0.05 degree grid and writes GeoTIFF outputs. A daily manifest records source availability, source file counts, read errors, active cells, maximum MESH, and processing status.

### GridRad and GridRad-Severe

GridRad or GridRad-Severe fills the gap from January 2012 through 13 October 2020 (inclusive). Stage **04b** downloads timesteps that fall in each 12 UTC → 12 UTC convective window from three NCAR THREDDS datasets: **GridRad-Severe** (**d841006**, 5-min, ~100 severe events per year), **GridRad V3.1 hourly** (**d841000**, through 2017, all months), and **GridRad V4.2 warm-season hourly** (**d841001**, Apr–Aug 2008–2021). Stage **04c** computes daily MESH75 on the canonical 0.05° grid. When **04c** chains downloads (`--with-04b-download`), it uses a **severe-first** policy: severe files are fetched when the catalog lists them; hourly GridRad is downloaded only when severe is unavailable or does not cover the full convective window, trying **d841000** then **d841001** (V4.2 only for Apr–Aug convective days after 2017). GridRad-Severe is preferred when available because higher temporal sampling better resolves short-lived hail cores.

Severe Hail Index (Witt et al. 1998) is derived from three-dimensional **reflectivity in dBZ** and ERA5 isotherm fields, then converted to MESH75 using the Murillo and Homeyer (2019) revised coefficients on the Bowman and Homeyer (2017) GridRad archive. NCAR GridRad v3/v4 files typically store reflectivity as sparse `Reflectivity(Index)` with an `index` vector; the pipeline reconstructs a dense vertical profile per grid column. The 3-D field `Nradecho` is an echo mask, not dBZ, and is excluded from SHI. Longitudes given in 0–360° form are normalized before CONUS masking. Gap-fill GeoTIFFs carry GDAL metadata tags (`MAX_MESH75_MM`, `ACTIVE_CELLS`, `SOURCE`, `DATE`) for operational QA.

### MRMS

Operational MRMS (Smith et al. 2016) supplies the recent radar era from **14 October 2020** onward. The pipeline handles native orientation and longitude conventions before writing convective-day model-grid MESH rasters (same 12 UTC → 12 UTC definition as MYRORSS and GridRad).

### ERA5

ERA5 monthly 0 C and -20 C isotherm heights support GridRad SHI computation and environmental filtering.

### SPC hail reports

SPC reports support validation and calibration review (Allen and Tippett 2015; Wendt and Jirak 2021). Because reports are affected by population, road networks, report practices, and reporting threshold changes, they are not used as the primary hazard field.

---

## Hail Hazard Model

### Grid

All hazard products use a fixed 0.05 degree CONUS grid:

```text
520 rows x 1180 columns
EPSG:4326
north-to-south row orientation
west-to-east column orientation
```

Hail size is an extremal variable, so native data are aggregated by block maximum rather than mean or sum.

### Bias correction and filtering

MYRORSS and MRMS MESH products are converted to corrected MESH75. GridRad-derived MESH75 is calibrated by **era-pooled quantile mapping**: active pixels from MYRORSS (2005–2011) are aligned to GridRad (2012–2020) when same-day overlap is unavailable (median ratio ~**1.10** above 10 mm on the production archive). Deterministic environmental filtering applies a 5 mm noise floor and requires **≥ 29 mm** for subtropical winter cells (Nov–Feb, lat &lt; 30°N), matching the Cintineo/Wendt severe-hail skill threshold.

**GridRad artifact filter (2026-07 / v2.3.0).** Stochastic return-period maps initially showed NEXRAD range rings and spokes, traced to GridRad-era isolated speckle and range-dependent over-estimation relative to SPC collocated pairs. We added `scripts/diagnostics/radar_artifact_diagnostic.py`, which bins validation pairs by distance to the nearest CONUS WSR-88D site (~140 radars) and fits per-era multiplicative debias factors (normalized at **125 km**, clipped **[0.45, 1.15]**) for diagnostic review. Stage 05 keeps SPC validation-only: range-debias tables and the optional hail-likelihood classifier are never applied to hazard rasters. GridRad days always pass **five core artifact-filter passes** plus default-on site remediation: isolated speckle (&gt; **2.5×** local 3×3 median), **radial range ring** (per-site 10 km bins vs inner-range ≤75 km baseline and neighbors; **1.12×** / **1.18×** thresholds), azimuthal annulus, quiet-background filament, and **spatiotemporal range-ring persistence**—a **21-day** trailing window of pre-filter daily rasters (resume-safe via sidecar) that zeros cells on chronically active (radar site, range) annuli while retaining burst cells above **1.75×** their historical median and coordinated storm-day annulus uplift (**1.5×**). This is the daily-grid analogue of multi-scan ring discrimination (Chilson et al. 2019). **Stage 01 (v2.2.2):** corrected WDSS-II `pixel_x`/`pixel_y` axes in MYRORSS sparse NetCDF (prior ingest truncated hail east of ~−96°W); full MYRORSS re-ingest restores eastern CONUS coverage for era-comparison diagnostics.

Optional ML calibration and probabilistic filtering remain available (Gneiting et al. 2005; Ortega 2018); `--skip-ml` forces deterministic fallbacks.

### Event identification

Daily corrected rasters are thresholded at **`EVENT_ACTIVE_THRESH_MM = 29.0 mm`** for event active cells (Cintineo et al. 2012; Wendt & Jirak 2021). The **25.4 mm** damage threshold (`DAMAGE_THRESH_MM`) is retained for occurrence products and Stage 13 severe-cell counts. Spatially and temporally coherent footprints are merged into events under five constraints: temporal gap between active days (≤ 2 days), buffered spatial overlap (~83 km), event duration (≤ 5 days), centroid displacement (≤ 150 km per day), and peak intensity jump (≤ 3× between consecutive days). Events are stored as sparse arrays:

```text
rows_event_id
cols_event_id
vals_event_id
```

This sparse representation is central to memory safety in the stochastic catalog. Storing the complete historical catalog as dense grids would require on the order of tens of gigabytes of RAM; sparse templates reduce that by two to three orders of magnitude.

### Per-cell hail-day climatology diagnostic and v2.2.1 threshold choice

Before finalizing v2.2.1, we ran `scripts/diagnostics/hail_day_climatology.py` on the full corrected archive (9,797 convective days, 1998–2026) to compare per-cell hail-day frequencies against Cintineo et al. (2012), Murillo et al. (2021), and Wendt & Jirak (2021). The diagnostic computes mean **hail days per year** at each 0.05° cell for six MESH75 thresholds and reports CONUS **any-cell** totals (comparable to Stage 08 λ).

**Key findings:**

1. **Conventional 25.4 mm over-diagnoses relative to literature skill thresholds.** At 25.4 mm, 93.8% of CONUS cells had ≥1 active day over the record; Great Plains maxima reached **5.5 hail days/yr** at 0.05° vs Cintineo’s **~11–12 days/yr** at coarser 0.88° and 29 mm (directionally consistent when resolution and threshold differ).

2. **National any-cell counts are weakly seasonal at 25.4 mm** (~344 days/yr, nearly flat across months) whereas SPC report-day climatology peaks sharply in late spring (~216 report days/yr on the validation pairs). This pattern is consistent with radar false alarms in cool-season and Gulf Coast convection noted by Murillo et al. (2021).

3. **29 mm (Cintineo/MRMS skill) is the preferred event threshold.** Great Plains per-cell maxima fall to **3.7 days/yr**; national any-cell counts average **331 yr⁻¹** (1998–2026).

4. **Higher Murillo skill thresholds (41.9–63.3 mm)** further reduce per-cell frequencies (GP max **1.6–0.2 days/yr**) and are useful for tail-focused sensitivity, not for damage-onset event catalogs.

| Threshold | GP max days/yr | GP mean days/yr | National any-cell days/yr |
|-----------|---------------:|----------------:|--------------------------:|
| 25.4 mm conventional | 5.5 | 2.2 | 344 |
| **29.0 mm skill (adopted)** | **3.7** | **1.4** | **331** |
| 35.6 mm MESHWitt skill | 2.3 | 0.6 | 321 |
| 41.9 mm MESH75 skill | 1.6 | 0.2 | 287 |
| 50.8 mm significant severe | 0.6 | 0.1 | 229 |
| 63.3 mm MESH95 skill | 0.2 | 0.04 | 126 |

**v2.2.1 adoption:** Stage 08 active cells and Stage 05 subtropical winter filtering use **`EVENT_ACTIVE_THRESH_MM = 29.0 mm`**. `DAMAGE_THRESH_MM = 25.4 mm` is unchanged for occurrence stages and Stage 13 severe-cell counts.

### Extreme value modeling

At each grid cell, annual maximum hail is represented by a zero-inflated frequency-severity model. Positive values are modeled with a lognormal body and a generalized Pareto tail (Pickands 1975; Balkema and de Haan 1974; Coles 2001). Tail shape parameters are pooled regionally via K-means clustering (default: 6 regions) and L-moment estimation (Hosking and Wallis 1997) to reduce instability from sparse exceedance samples; L-moments are preferred over maximum likelihood for the small regional samples available in a 25-year radar record.

For each region, automated threshold diagnostics are computed and written to `threshold_selection.csv` (Scarrott and MacDonald 2012). The six diagnostic columns are: exceedance count, GPD shape (ξ), GPD scale (σ), mean residual life linearity score, shape stability across candidate thresholds, and a KS goodness-of-fit statistic. The automated diagnostic is preferred over a fixed threshold where data support it, with 50.8 mm (2 inches) as the conservative fallback.

### Topographic correction

Stage 12 applies a freezing-level-aware multiplicative correction to analytical return-period maps:

```text
factor = 1.0 + α × (elevation_km / freezing_level_km)
```

with α = 0.25, bounded to [1.0, 1.25] when ERA5 monthly freezing levels are available, and [1.0, 1.20] otherwise. The coefficient is empirically motivated by Front Range hail climatology and is treated as a sensitivity parameter in post-run analysis, acknowledging that melting and terrain effects are only first-order approximations (Rasmussen and Heymsfield 1987; Li et al. 2021; Andrews et al. 2024). Elevation data are taken from a 0.05° aggregated topography product.

### Stochastic catalog

The stochastic catalog resamples historical sparse event templates in the spirit of hail insurance and catastrophe event-set practice (Miralles et al. 2023). Annual event counts are drawn from a Poisson distribution, event dates are sampled from a smoothed seasonal distribution, templates are selected by seasonal similarity, and footprints receive sparse spatial translation (±3 grid cells, ≈ ±16.5 km), lognormal intensity perturbation (calibrated σ), and optional shape perturbation. All perturbation operations act directly on sparse row/column/value vectors; no intermediate dense reconstruction is performed. Analytical and stochastic return-period maps are compared as a structural diagnostic (Davison et al. 2012): divergence above defined thresholds at return periods ≤ 500 years is treated as a priority model-risk flag requiring manual review.

---

## AI-Assisted Development Process

### Agent roles

AI collaboration on this project is credited under the collective pseudonym
**theonlymuffinbot**. That name is an attribution label for all AI work on the
repository; it is **not** a separate GitHub repository. The sole code remote is
`cmelhauser/us-hail-cat-model`.

Work attributed to **theonlymuffinbot** was performed through frontier language-model
agents under human direction, including `claude-sonnet-4-6` and `claude-opus-4-6`
(Anthropic, accessed May 2026) and `gpt-5.5-medium` (OpenAI, accessed May 2026).
Those agents acted as research assistants, software engineers, documentation
editors, code reviewers, and operational monitors.

The human operator (Christopher Melhauser) remained responsible for scientific
direction, acceptance criteria, prioritization, and interpretation. Scientific
accountability for claims, code, and the manuscript remains with the human author;
**theonlymuffinbot** documents AI collaboration rather than independent authorship
of scientific claims.

### Development activities

AI assistance (**theonlymuffinbot**) was used for:

- reviewing the existing repository and identifying methodological risks;
- implementing Stage 05 optional ML calibration paths with deterministic fallbacks;
- adding Stage 08 merge-quality diagnostics (centroid displacement, intensity jump, `merge_quality_flag`);
- implementing automated GPD threshold diagnostics in Stage 09;
- implementing freezing-level-aware topographic correction in Stage 12;
- enforcing sparse-safe constraints throughout Stage 13 stochastic simulation;
- fixing Stage 13 out-of-memory failure via memmap-backed annual maxima and streamed Parquet event summaries (2026-06-30);
- adding a Stage 01 source-coverage manifest;
- diagnosing archive-format issues (plain `.netcdf` vs. gzipped `.netcdf.gz` in MYRORSS);
- diagnosing GridRad gap-fill defects (incorrect use of `Nradecho` instead of sparse `Reflectivity` for SHI, producing all-zero gap days on hourly-only archives);
- writing pre-run review documentation and audit checklists;
- writing and running targeted unit, integration, and smoke tests;
- expanding methodology, benchmark, sensitivity, and FAQ documentation;
- monitoring a long-running full pipeline run;
- distinguishing missing-source days from source-present no-hail days;
- drafting manuscript text and documentation.

All git operations (commit, push, merge) were performed by the human operator; AI systems provided commit message drafts and change summaries but did not write directly to git history.

### Development-process evidence

The AI-assisted development process is reported through quantitative repository and workflow metrics (GitHub repository `cmelhauser/us-hail-cat-model`, snapshot through **2026-06-30**; full v2.2.1 production hazard run complete).

```text
Repository start date:                    2026-03-17
Repository freeze date for submission:    Not frozen (draft; v2.2.1 hazard run complete 2026-06-30)
Total commits (all branches):             90
Commits on main since 2026-05-01:         50 (v2.1 hardening and run-prep pass)
Pull requests opened / merged to main:    9 / 6
Tracked files at HEAD (by category):      37 stage/helper Python modules; 36 test files;
                                          24 documentation markdown files; 10 CI/config files
Current Python + docs line count (wc):    ~8,500 lines in scripts/; ~7,600 lines in docs/
Cumulative git diffstat (all history):    +146,092 / −120,636 lines
Automated tests (v2.1 merge → HEAD):      26 → 37 test modules; 198 test functions collected
Recent CI workflow runs (tests.yml):      18 sampled runs, 18 success, 0 failure
Pipeline stages in scope:                 14 executable (01–13, 14; plus 11b)
AI-audit defects fixed pre-production:    ≥7 (see table below)
Human-retained decisions (examples):      fixed 0.05° grid; SPC validation-only; Stage 13
                                          sparse-safe; deterministic Stage 05 fallback (--skip-ml);
                                          three-source splice dates; human-only git push/merge
Approximate wall-clock repository life:     ~15 weeks (2026-03-17 to 2026-06-30)
Intensive AI-assisted hardening window:     ~3 weeks (2026-05-01 to 2026-05-20);
                                            production ingest + hazard run May–June 2026
Approximate model/API cost:               Not logged in repository (not reported here)
```

Representative AI-assisted interventions are summarized in Table 1.

| # | Issue discovered (AI-assisted audit) | Evidence | Patch / artifact | Validation | Residual risk |
|---|--------------------------------------|----------|----------------|------------|---------------|
| 1 | Early MYRORSS days read as empty | Zero GeoTIFFs despite S3 objects; plain `.netcdf` not `.gz` | Stage 01 dual-suffix reader; `manifest_stage01_myrorss.csv` | Rebuilt 1998 canary days; manifest status codes | Remaining MYRORSS `missing_source` days documented |
| 2 | Missing-source vs no-hail conflated | Raster zeros alone ambiguous | Manifest distinguishes `missing_source` / `no_hail_pixels` / `ok` | Stage 01 QA + `--qa-only` repair pass | Users must consult manifest, not raster alone |
| 3 | Event-merge constant drift | `MAX_CENTROID_KM_DAY` 100 km in Stage 08 vs 150 km in config/docs | Corrected to 150 km; test guard in `test_no_duplicated_constants.py` | pytest; methodology §8.2 aligned | Other constants still require drift tests |
| 4 | Duplicated grid constants across stages | Review grep across 15 scripts | `scripts/_config.py`, `_logging.py`, `_io.py` | `test_no_duplicated_constants.py`; ruff/mypy CI | New stages must import shared helpers |
| 5 | GridRad gap-fill silent zeros | Hourly days with NetCDFs but `active_cells=0` | Stage 04c sparse `Reflectivity` reader; lon fix; GDAL QA tags | Reprocessed 2012 canary day; log peak hail | GridRad–MRMS calibration still required at Stage 05 |
| 6 | Parallel 04c worker import failure | `ProcessPoolExecutor` dataclass error loading 04b | Register 04b in `sys.modules` before `exec_module` | Multi-worker 04c restart | NCAR download throttling at high worker count |
| 7 | Physical hail QA ceiling | 250 mm cap vs later 300 mm policy | Shared `sanitize_hail_values`; Stage 01–05 wired | 300 mm rescan: 0 cells after prior 250 mm repair | Values >300 mm still truncated to zero |
| 8 | GridRad hourly calendar gap (2018–2020) | 708 gap-era days `no_data` after primary ingest; V3.1 ends 2017 | **d841001** V4.2 warm-season hourly fallback in 04b/04c; `--missing-only` backfill | Apr 2018 canary days write `src=gridrad-hourly-v42`; pytest fallback suite | Off-season and non-severe warm-season days may remain `missing_source` |
| 9 | Stochastic RP radar rings/spokes | GridRad speckle 9.7%; SPC/MESH ~0.81 at 112 km; visible NEXRAD geometry in RP maps | `radar_artifact_diagnostic.py`; `range_debias.npz`; five-pass GridRad filter in Stage 05 (persistence pass 5) | Speckle 9.7%→6.1%→**1.8%** (pre–eastern-fix archive) | Refresh diagnostics after 2026-07-08 Stage 05 rebuild |

### Example: source manifest discovery

During a pre-run review, many apparently empty daily GeoTIFFs were found. AI-assisted investigation showed that some early MYRORSS archive files were plain `.netcdf` rather than `.netcdf.gz`, and the previous reader ignored them. The Stage 01 script was updated to read both formats, and a manifest was added to distinguish missing source from no-hail days. This illustrates the model-building value of AI agents as persistent auditors: the issue was not a novel algorithmic insight, but a data-engineering defect that would have materially affected the historical record.

### Example: GridRad reflectivity ingestion

During full-pipeline execution, most GridRad hourly gap-fill days produced zero active cells despite successful NetCDF downloads. AI-assisted inspection of NCAR file structure showed that physical reflectivity is stored as sparse `Reflectivity(Index)`, while `Nradecho` is a separate 3-D echo mask with values well below the 40 dBZ column threshold used for SHI. The Stage **04c** reader was corrected to reconstruct dBZ from sparse reflectivity, normalize longitudes, and write diagnostic GDAL tags. Affected gap-era GeoTIFFs were deleted and reprocessed. This case shows how AI-assisted monitoring plus file-format literacy can catch scientifically silent failures that unit tests on synthetic data may miss.

### Example: GridRad V4.2 hourly fallback (d841001)

After primary Stage **04c** ingest (2026-06-08 → 2026-06-27), **712** of **3,209** gap-era manifest rows remained `missing_source`, including many Apr–Aug 2018–2020 convective days where V3.1 hourly (**d841000**) is empty but NCAR publishes warm-season V4.2 hourly (**d841001**). AI-assisted review of THREDDS catalogs and the Murillo et al. (2021) GridRad documentation identified the separate dataset ID. Stage **04b** was extended to query **d841001** after **d841000** when severe coverage is absent; Stage **04c** tags outputs `gridrad-hourly-v42`. A **`--missing-only`** backfill recovers additional warm-season days without re-downloading the full archive. This illustrates how AI agents can close data-availability gaps that are invisible to algorithm-only reviews.

### Example: Radar artifact debias in stochastic maps

After the first full v2.2.1 hazard run, **100-year** and **10,000-year** stochastic return-period maps showed concentric NEXRAD rings and radial spokes over the central and eastern CONUS—patterns inconsistent with physical hail climatology. AI-assisted review linked the artifacts to GridRad-era speckle (**9.7%** of active cells vs **3.9%** for MYRORSS) and range-dependent SPC/MESH bias (median report/MESH ratio **~0.81** at 112 km from radar). The team implemented a diagnostic that bins validation pairs by nearest-radar distance, fits per-era debias factors, and applies a **five-pass** GridRad artifact filter in Stage 05 (speckle, radial ring with inner-range baseline, azimuthal annulus, filament, and **spatiotemporal range-ring persistence** from a 21-day trailing window). Post-correction diagnostics reduced GridRad speckle to **1.8%** mean (**9.1%** P95) from **6.1%** after the initial three-pass filter. A Stage 01 sparse-grid coordinate fix (WDSS-II `pixel_x`/`pixel_y` axes) restored eastern CONUS MYRORSS hail that had been truncated west of ~−96°W; full MYRORSS re-ingest completed **2026-07-08** (5,023/5,023 days; geotransform and eastern-coverage QA passed), and Stages **05–14** were restarted on that archive for final hazard products.

### Reproducibility controls

The repository includes documentation, pre-run review notes, validation commands, gitignored generated data products, stage logs, and a staged execution plan. AI-generated changes were reviewed through diffs, tests, py_compile checks, smoke runs, and branch synchronization.

### Governance and disclosure

AI use is disclosed in the Materials and Methods section. Collaboration is
credited under the project pseudonym **theonlymuffinbot**, with the underlying
systems and categories of work named, and with human-review controls applied to
AI-generated outputs. Scientific accountability for accuracy, integrity, and
publication remains with Christopher Melhauser. All AI outputs used in the code,
documentation, analysis, and manuscript were reviewed and accepted under human
responsibility. **theonlymuffinbot** is not a separate GitHub repository.

---

## Results

> **Publication freeze note (2026-07-08).** Stage **01** MYRORSS re-ingest is complete and
> eastern CONUS / geotransform QA passed. Stages **05–14** are rebuilding on that archive
> (`run_pipeline.py --from 05 --skip-ml`). Numerical values in this Results section are from
> the prior **v2.2.1 / pre–eastern-fix** production run (**2026-06-30**) and intermediate
> diagnostics; treat them as **scaffolding** until replaced from
> `data/analysis/pnas_article_metrics.json` and regenerated `docs/figures/pnas/` after the
> rebuild. Insert final discussion paragraphs once Figs. 2–13 and Tables 3–4 are refreshed.

**Prior production snapshot (provisional):** convective-day **v2.2.1** hazard pipeline
(Stages 05–14) completed **2026-06-30** on the pre–Stage 01 coordinate-fix archive.

### Stage completion and data coverage

Values as of **2026-07-08** ingest + **2026-06-30** hazard snapshot (update after rebuild):

```text
Model version:                            2.2.2
Total daily MESH rasters (raw archive):   9,797
  MYRORSS (1998–2011):                    5,023  (re-ingest complete 2026-07-08;
                                                  manifest ~4,994 ok / 20 missing_source)
  GridRad gap-fill (2012–2020-10-13):     2,714  (manifest: 2,661 ok, 499 missing_source)
  MRMS (2020-10-14–present):              2,060  (manifest: 2,059 ok, 1 ok_with_read_errors)
Stage 05–14:                              rebuilding (five-pass filter + era-pooled QM)
Event active threshold:                   29.0 mm (EVENT_ACTIVE_THRESH_MM)
Historical sparse events / stochastic:    TBD after Stages 08 / 13
Prior event catalog (superseded):         8,798 events; 303.4 yr⁻¹ (2026-06-30)
```

**Manifest provenance (Fig. 2).** Stage 01 MYRORSS coverage is effectively complete after
the coordinate-fix re-ingest (**5,023** GeoTIFFs; geotransform OK; eastern CONUS restored).
GridRad gap-fill retains **499** `missing_source` rows (mostly off-season or pre-V4.2 hourly
gaps); **2018–2019** are the sparsest years (~48% ok rate) before warm-season **d841001**
backfill. MRMS coverage is effectively complete.

### Literature-aligned diagnostics

Three diagnostics, motivated by Cintineo et al. (2012), Murillo et al. (2021), Wendt & Jirak (2021), and the source-transition discussion in `docs/literature_review.md`, were run on the **pre–eastern-fix** corrected archive (**provisional**; regenerate after Stage 05+`hail_day_climatology.py`):

**Per-cell hail-day climatology (Fig. 5–6).** At the adopted **29 mm** skill threshold, Great Plains maxima are **3.7 days yr⁻¹** per 0.05° cell (vs Cintineo ~11–12 days yr⁻¹ at coarser 0.88° resolution). National any-cell totals average **331 days yr⁻¹** (1998–2026). The **25.4 mm** conventional threshold yields a nearly flat seasonal cycle (~344 days yr⁻¹ year-round), whereas **29 mm** and higher Murillo skill thresholds reproduce the late-spring peak expected from SPC report climatology (Fig. 5).

**Source-transition peak distributions (Fig. 3).** At the MYRORSS→GridRad splice (2010–2013), median daily CONUS peak MESH is **54.5 mm** (MYRORSS) vs **54.7 mm** (GridRad); p95 is higher for GridRad (**143 mm** vs **118 mm**), consistent with GridRad-Severe 5-min sampling. At the GridRad→MRMS splice (2019–2022), MRMS peaks are higher (median **79 mm**, p95 **245 mm**) than GridRad (**62 mm**, **106 mm**), flagging the MRMS handoff for Stage 05 calibration review rather than assuming homogeneity.

**Era-pooled calibration ECDF (Fig. 4).** Quantile mapping compresses MYRORSS and MRMS upper tails toward the GridRad anchor: MYRORSS p95 falls from **215 mm** (raw) to **94 mm** (calibrated); MRMS p95 from **209 mm** to **93 mm**. GridRad is unchanged (anchor era).

**Radar artifact diagnostic (2026-07-06, pre-persistence / pre–eastern fix).** `scripts/diagnostics/radar_artifact_diagnostic.py` on the four-pass corrected archive (9,797 days) quantified NEXRAD geometry artifacts. GridRad mean speckle fraction (isolated spikes &gt;2.5× local 3×3 median) was **1.8%** of active cells (**9.1%** at P95) vs **3.9%** for MYRORSS—down from **9.7%** / **50%** pre-debias and **6.1%** / **33%** after the three-pass filter. Range-binned mean annual maxima show GridRad **~1.7×** MYRORSS at 50–125 km from radar. A fifth **spatiotemporal persistence** pass (21-day trailing window) was added **2026-07-07**; Stage 01 MYRORSS coordinate-fix re-ingest completed **2026-07-08**. **TODO after rebuild:** regenerate artifact maps and replace this paragraph with post–Stage 05/06 numbers.

### Validation against SPC reports

Stage 06 validation on corrected MESH75 (Fig. 7; **provisional** — regenerate after Stage 06 rebuild):

```text
Report–MESH pairs:                        173,766  (2004-03-01 → 2026-05-03)  ← replace
Overall bias (MESH75 − SPC):              −0.774 inches
Overall RMSE:                             1.146 inches
Overall correlation:                      0.164
Severe hail (≥ 1.0") POD / FAR / CSI:     0.333 / 0.001 / 0.332
  Hits / misses / false alarms:           47,015 / 94,356 / 28
Diurnal detection (06–22 vs 22–06 UTC):   30.3% vs 33.7%
```

**Calibration by report-size bin (Fig. 7).** — provisional table; freeze after Stage 06.

| Bin | N | Bias (in) | RMSE (in) | POD |
|-----|--:|----------:|----------:|----:|
| 0.75–1.00″ | 32,395 | −0.80 | 0.80 | 0.003 |
| 1.00–1.50″ | 87,831 | −0.47 | 0.90 | 0.395 |
| 1.50–2.00″ | 38,781 | −1.06 | 1.35 | 0.390 |
| 2.00–3.00″ | 12,464 | −1.62 | 1.87 | 0.426 |
| 3.00–4.00″ | 1,374 | −2.37 | 2.55 | 0.411 |
| ≥ 4.00″ | 921 | −3.69 | 3.80 | 0.326 |

Radar MESH75 under-estimates reported hail size (negative bias), especially above 2 inches, consistent with report rounding, beam height, and Wendt & Jirak (2021) radar–report sampling differences. Near-zero FAR at the 1-inch threshold indicates few radar false alarms relative to collocated reports. Spatial bias maps (`spatial_bias_1deg.csv`) show MESH/report ratios near unity (0.8–1.3) across the central Great Plains.

### Return-period maps

Analytical smoothed return-period maps (Stages 09–10–12; Figs. 8–9) — **provisional** CONUS peaks from 2026-06-30:

```text
10-year CONUS maximum:                    60.3 mm (2.37 in)   ← replace after Stages 09–12
100-year CONUS maximum:                   96.9 mm (3.81 in)
500-year CONUS maximum:                   132.9 mm (5.23 in)
1,000-year CONUS maximum:                 150.6 mm (5.93 in)
50,000-year CONUS maximum:                255.4 mm (10.1 in)
Cells with RP ≥ 25.4 mm (100-yr map):     327,231 (~53% of grid)
Peak hazard regions:                      Central Great Plains; secondary maxima in High Plains / Front Range
Analytical vs stochastic (CONUS peak):
  100-year:   analytical 96.9 mm  vs  stochastic 157.8 mm
  1,000-year: analytical 150.6 mm vs  stochastic 196.9 mm
  50,000-year: analytical 255.4 mm vs  stochastic 300.0 mm (QA cap)
```

Stochastic empirical peaks exceed analytical smoothed maps at return periods ≤ 1,000 years, consistent with resampling sparse event templates with calibrated intensity perturbation (σ = 0.225) rather than extrapolating a regional GPD tail alone. At 50,000 years both products hit the physical QA cap (300 mm) at the CONUS maximum cell. Stage 14 renders side-by-side analytical vs stochastic maps (`docs/figures/analysis/analytical_vs_stochastic_rp.png`). **TODO:** rewrite after eastern-CONUS fix propagates into RP geography.

### Historical event catalog and count dispersion

Stage 08 sparse events at **29 mm** (Fig. 10) — **provisional (pre–eastern-fix run)**:

```text
Total events:                             8,798          ← replace after Stage 08
Mean annual event count:                  303.4 yr⁻¹  (σ = 59.5)
Index of dispersion (var/mean):           11.66
Per-cell GP max hail days/yr (@ 29 mm):   3.7
National any-cell days/yr (@ 29 mm):      331
```

The index of dispersion **≫ 1** indicates substantial year-to-year clustering of severe convection, supporting the limitation noted in `docs/literature_review.md` that the Stage 13 Poisson count model may underrepresent overdispersion; a negative-binomial alternative is reserved for sensitivity analysis. Recompute after the Stage 08 rebuild.

### Stochastic catalog

Stage 13 sparse resampling (Fig. 12; `data/stochastic/`) — **provisional numbers from 2026-06-30**; rebuild required:

```text
Simulated years:                          50,000
Calibrated σ_perturb:                     0.225          ← re-calibrate after Stage 08
Poisson λ (events yr⁻¹):                  303.4 (historical); 303.3 (simulated mean)
Synthetic events:                         15,166,852     ← replace after Stage 13
Simulation wall time:                     321.5 min (~5.4 h)
Annual-max storage:                       memmap 112.5 GB on disk (deleted after RP write)
100-yr occurrence exceedance peak (OEP):  225.6 mm
```

**Empirical stochastic CONUS peak hail (mm)** — provisional:

| Return period | Stochastic peak | Analytical peak |
|--------------:|----------------:|----------------:|
| 10 yr | 117.5 | 60.3 |
| 100 yr | 157.8 | 96.9 |
| 1,000 yr | 196.9 | 150.6 |
| 50,000 yr | 300.0 (cap) | 255.4 |

**TODO after Stage 13/14:** replace table from `pnas_article_metrics.json` / Stage 14 report; confirm analytical–stochastic agreement and absence of residual NEXRAD rings on Figs. 12–13.

### AI-assisted development results

Process metrics for the AI-assisted infrastructure build (snapshot **2026-06-30**):

```text
Development duration (repository):          ~15 weeks (2026-03-17 to 2026-06-30)
Intensive AI-assisted hardening window:     ~9 weeks (2026-05-01 to 2026-06-30)
Total git commits:                          106
AI-audit defects remediated pre-production: 8 documented (Table 1)
Documentation markdown files in docs/:      25+
Automated test modules:                     37
Automated test functions (pytest collect):  198
Integration tests:                          test_smoke_synthetic.py; test_gridrad_hourly_fallback.py
CI (GitHub Actions tests.yml):              Python 3.10/3.11/3.12 matrix; green on v2.2.2 branch
Long-run monitoring (operations):           Stage 01 MYRORSS fix complete 2026-07-08 (5,023 days);
                                            Stages 05–14 rebuild in progress (hail_from05);
                                            prior v2.2.1 hazard catalog superseded pending rerun
```

Examples of AI audit findings beyond Table 1: (i) comprehensive v2.1 review document identifying missing LICENSE, CI, and `pyproject.toml` (resolved same week); (ii) detection that Stages 05–14 had been executed on a 31-event May-2011 smoke slice before Stage 01 finished, invalidating those outputs for production; (iii) documentation drift across Python version strings and `MAX_HAIL_MM` caps reconciled to `_config.py`; (iv) GridRad pipeline ergonomics (streaming 04b inside 04c, worker pools, per-day staging deletion) implemented after operational review; (v) PNAS manuscript and literature-review expansion tying AI-process claims to reproducibility artifacts rather than anecdotal chat use; (vi) **d841001** V4.2 warm-season hourly fallback closing Apr–Aug 2018–2020 NCAR catalog gaps; (vii) **`render_pnas_article_figures.py`** linking literature benchmarks to manifest, calibration, validation, and return-period outputs for manuscript QA; (viii) MYRORSS WDSS-II sparse-grid axis swap catching eastern CONUS truncation before final publication.

### Figures

Main figures regenerate to `docs/figures/pnas/` after Stages 06–14 complete:

```bash
.venv/bin/python scripts/14_render_figures.py
.venv/bin/python scripts/diagnostics/render_pnas_article_figures.py
```

| Fig. | File | Caption | Ready? |
|------|------|---------|--------|
| 1 | `fig01_data_source_timeline.png` | Radar-era timeline: MYRORSS, GridRad gap-fill (12 UTC convective days), MRMS splice dates | Scaffold OK |
| 2 | `fig02_manifest_coverage_by_year.png` | Source-coverage manifest status by year | Refresh after Stage 01 manifest final |
| 3 | `fig03_source_transition_daily_peaks.png` | Source-transition QA: daily CONUS peak MESH at era splices | After Stage 05 |
| 4 | `fig04_calibration_ecdf_by_source.png` | Era-pooled calibration ECDFs by source | After Stage 05 |
| 5 | `fig05_seasonal_national_hail_days.png` | Seasonal cycle by MESH75 threshold | After hail-day diagnostic |
| 6 | `fig06_hail_days_per_year_29mm.png` | Per-cell mean annual hail days @ 29 mm | After hail-day diagnostic |
| 7 | `fig07_validation_by_size_bin.png` | SPC validation bias and POD by size bin | After Stage 06 |
| 7b | `fig07b_mesh_vs_spc_scatter.png` | Report size vs collocated MESH75 | After Stage 06 |
| 8 | `fig08_rp_100yr_analytical.png` | Analytical 100-year RP map | After Stages 09–12 |
| 9 | `fig09_rp_1000yr_analytical.png` | Analytical 1,000-year RP map | After Stages 09–12 |
| 10 | `fig10_annual_event_counts.png` | Annual sparse event counts (Stage 08) | After Stage 08 |
| 11 | `fig11_ai_development_workflow.png` | Human-directed AI development loop | Scaffold OK |
| 12 | `fig12_rp_100yr_stochastic.png` | Stochastic 100-year empirical RP map | After Stage 13 |
| 13 | `fig13_analytical_vs_stochastic.png` | Analytical vs stochastic RP comparison | After Stage 14 |

### Tables

| Table | Content | Status |
|-------|---------|--------|
| 1 | AI-assisted development interventions (main text) | Complete |
| 2 | Data sources, temporal coverage, and model role | Draft in Methods |
| 3 | Manifest status counts by era (MYRORSS / GridRad / MRMS) | Values in Results; Fig. 2 |
| 4 | SPC validation by size bin | Values in Results; Fig. 7 |
| 5 | Model limitations and mitigation controls | Discussion + Limitations |

---

## Discussion

> **Finalization checklist (fill after `hail_from05` completes and figures regenerate).**  
> 1. Replace provisional Results numbers from `data/analysis/pnas_article_metrics.json`.  
> 2. Confirm eastern CONUS MYRORSS is present in climatology / RP maps (no ~97°W cutoff).  
> 3. Discuss artifact remediation: five-pass GridRad filter + range debias; post-rebuild speckle % and visual QA of Figs. 12–13.  
> 4. Interpret analytical vs stochastic RP peaks (Fig. 13); note any remaining GPD or overdispersion caveats.  
> 5. Summarize SPC validation (Fig. 7) with frozen POD / bias by size bin.  
> 6. Freeze Significance Statement and Abstract to final counts; set repository SHA + DOI placeholders.

This work contributes a public-data hail hazard model and a case study in AI-assisted scientific software development. The hail model demonstrates that a radar-first pipeline can be built from public datasets, calibrated across source eras, converted into sparse historical events, and extended into a stochastic catalog. The AI process demonstrates that language-model agents can support not only code generation, but also literature synthesis, data QA, documentation, version control, and operational monitoring.

The most important scientific design choice is the separation of radar hazard from report validation. Hail reports remain essential, but their observational bias makes them unsuitable as the primary gridded hazard field. Radar-derived MESH provides a physically motivated spatial field, while validation against reports tests consistency with independent human-observed outcomes.

The most important computational design choice is sparse event storage. Hail footprints are localized, and dense event cubes would waste memory and constrain stochastic simulation. Sparse templates allow event perturbation and resampling at catalog scale.

A late-stage discovery illustrates the AI-assisted QA loop: after a full hazard run, maps exposed NEXRAD rings/spokes and truncations inconsistent with known hail climatology. Agents and human review attributed these to GridRad-era geometric artifacts and a MYRORSS sparse-grid axis error; remediation (five-pass filter, range debias, Stage 01 re-ingest, Stages 05–14 rebuild) is part of the reproducible audit trail rather than an undocumented post hoc patch. **[Expand with post-rebuild diagnostic numbers and figure callouts.]**

The most important AI-process lesson is that AI assistance is most powerful when embedded in a disciplined workflow. The agents were useful because the repository had explicit tests, logs, stage boundaries, documentation, and git controls. AI did not remove the need for scientific judgment; it increased the speed and breadth with which assumptions, code paths, data provenance, and documentation could be inspected.

A component of the repository that warrants separate emphasis is the post-run validation framework. Beyond software tests, the model defines a benchmark suite that compares annual exceedance frequency and return-period maps against published independent climatologies (Cintineo et al. 2012; Murillo et al. 2021; Wendt and Jirak 2021) and checks source-transition consistency at the MYRORSS/GridRad and GridRad/MRMS boundaries. These pre-specified targets, and an accompanying sensitivity sweep plan, convert the model from a one-time computation into a revisable scientific object. AI agents participated in specifying these targets alongside the code.

This matters beyond hail. Many societally important hazards have public data, known scientific ingredients, and fragmented code examples, but lack transparent, maintained, end-to-end models. Human-directed AI agents can lower the fixed cost of assembling such models while making assumptions more visible. In this sense, AI may change not only scientific discovery but also the production of reusable scientific infrastructure.

**[Optional closing paragraph once Figs. 8–13 are final:** implications for underwriting / academic use of open radar-based hail RP maps; why hazard-only release precedes loss modeling; what a full bootstrap CI and non-stationary climate extension would add.]

---

## Limitations

The model is hazard-only and does not include exposure, vulnerability curves, or financial loss in the repository. **Future work** (documented in `docs/methodology.md` §14) includes claims-calibrated MDR functions informed by property-insurance hail studies (Brown et al. 2015), geocoded exposure, and loss aggregation — the natural extension after the hazard layer validated here. Tail estimates are point estimates and do not yet include bootstrap confidence intervals. The model assumes stationarity over the radar record. Source transitions among MYRORSS, GridRad, and MRMS remain a key uncertainty. The stochastic catalog uses a Poisson event-count model, which may underrepresent overdispersion in active severe-convective years (observed index of dispersion **11.7** in the historical event catalog; negative-binomial sensitivity reserved). Stochastic empirical peaks exceed analytical maps at moderate return periods, flagging GPD tail review for the longest return levels.

The AI-process analysis is also limited. This is a case study rather than a randomized comparison of human-only and AI-assisted development. The exact contribution of each AI system is difficult to isolate because the workflow was interactive and iterative. The article therefore frames AI as an enabling workflow component, not as an independently validated replacement for expert model development.

---

## Materials and Methods

### Computational environment

The model is implemented as a staged Python repository. Each stage writes durable outputs to `data/`, diagnostics to `logs/` or `docs/figures/`, and documentation to `docs/`. Generated model outputs are excluded from git tracking. Manuscript figures are regenerated with:

```bash
.venv/bin/python scripts/diagnostics/render_pnas_article_figures.py
.venv/bin/python scripts/14_render_figures.py
```

### Pipeline stages

The full pipeline contains 14 pipeline stages (01–13 hazard + 14 figures; loss modeling is future work in methodology §14):

```text
01  MYRORSS ingestion — daily MESH rasters + source-coverage manifest
02  MRMS ingestion — daily MESH rasters from operational radar
03  SPC report download — validation dataset only, not hazard input
04a ERA5 isotherms — monthly 0°C / −20°C freezing levels for GridRad SHI
04b GridRad download — NCAR d841006 (Severe), d841000 (V3.1 hourly), d841001 (V4.2 warm-season hourly)
04c GridRad gap fill — severe-first SHI from sparse Reflectivity (dBZ) → MESH75 daily rasters + manifest
05  Bias correction and filtering — MESH75 calibration, ML optional, deterministic fallback required
06  SPC validation — corrected MESH75 vs surface reports; source-transition diagnostics
07  Hail climatology — annual exceedance frequency and occurrence rasters
08  Event catalog — sparse historical events with merge-quality flags
09  Regional EVT fitting — GPD tail via L-moments, automated threshold diagnostics
10  Spatial CDF pooling — 150 km smoothing for stable return-period maps
11  Occurrence probability maps — 8 MESH75 thresholds
11b Public DEM preparation — NOAA/NCEI ETOPO 2022 resampled to 0.05°
12  CONUS mask + topographic correction — freezing-level-aware elevation factor
13  Stochastic catalog — 50,000-yr sparse event resampling (Poisson counts, seasonal templates)
14  Figures — analytical vs stochastic RP comparison, benchmark diagnostics
```

**Future work (loss side):** exposure geocoding, claims-calibrated vulnerability (MDR) by construction and roof type, deductibles/limits, and portfolio loss aggregation — building on the hazard outputs above.

```text
(planned, not in repository)
L1  Exposure module — building attributes and values
L2  Vulnerability — claims-fitted MDR curves
L3  Financial loss — policy terms and roll-ups
```

### AI disclosure

Large language models were used in the development of the codebase, documentation, monitoring workflow, and manuscript draft. The systems used were `claude-sonnet-4-6` and `claude-opus-4-6` (Anthropic, accessed May 2026) and `gpt-5.5-medium` (OpenAI, accessed May 2026). AI assistance included literature synthesis, code generation, code review, test authoring, documentation editing, shell-command planning, and long-running pipeline monitoring. Git operations (commit, push, merge) were performed by the human operator. AI outputs were reviewed, edited, tested, and accepted under human direction. AI systems are not listed as authors and are not treated as accountable scientific contributors.

### Data and code availability

The code is publicly available at:

```text
https://github.com/cmelhauser/us-hail-cat-model
```

**Maintainer ORCID:** [0009-0000-4234-5419](https://orcid.org/0009-0000-4234-5419)

Input datasets are public or publicly documented. Generated data products are reproducible from the pipeline but are not committed to the source repository because of size (`data/`, `docs/figures/`, `logs/` are gitignored).

| Artifact | Location |
|----------|----------|
| Source code | [github.com/cmelhauser/us-hail-cat-model](https://github.com/cmelhauser/us-hail-cat-model) (commit SHA: *TBD at submission*) |
| Code archive DOI | *TBD — Zenodo deposit minted on GitHub Release `v2.X.X`* |
| Generated outputs DOI | *TBD — Zenodo dataset tarball; see `docs/DATA_AVAILABILITY.md`* |

Full upload instructions, tarball layout, and pre-submission checklist: **`docs/DATA_AVAILABILITY.md`**.

---

## Acknowledgments

[To be added: funding, institutional support, computational resources, and human contributors.]

---

## Competing Interests

[To be added.]

---

## References

Allen, J.T. and M.L. Tippett, 2015: The characteristics of United States hail reports: 1955–2014. *Electronic Journal of Severe Storms Meteorology*, 10(3), 1–31.

Allen, J.T., M.L. Tippett, and A.H. Sobel, 2015: An empirical model relating U.S. monthly hail occurrence to large-scale meteorological environment. *Journal of Advances in Modeling Earth Systems*, 7(1), 226–243.

Andrews, M.S., et al., 2024: Climatology of the elevated mixed layer over the contiguous United States and Northern Mexico using ERA5: 1979–2021. *Journal of Climate*, 37, 1833–1851.

Balkema, A.A. and L. de Haan, 1974: Residual life time at great age. *Annals of Probability*, 2(5), 792–804.

Blair, S.F., et al., 2011: A radar-based assessment of the detectability of giant hail. *Electronic Journal of Severe Storms Meteorology*, 6(7), 1–30.

Blair, S.F., et al., 2017: High-resolution hail observations: implications for NWS warning operations. *Weather and Forecasting*, 32, 1101–1119.

Boiko, D.A., R. MacKnight, B. Kline, and G. Gomes, 2023: Autonomous chemical research with large language models. *Nature*, 624, 570–578.

Bowman, K.P., and C.R. Homeyer, 2017: GridRad: Three-dimensional gridded NEXRAD WSR-88D radar data and derived hail metrics. University of Oklahoma GridRad Project. http://gridrad.org

Brown, T.M., et al., 2015: Evaluating hail damage using property insurance claims data. *Weather, Climate, and Society*, 7(3), 197–210.

Chilson, C., K. Avery, A. McGovern, E. Bridge, D. Sheldon, and J. Kelly, 2019: Automated detection of bird roosts using NEXRAD radar data and convolutional neural networks. *Remote Sensing in Ecology and Conservation*, 5(1), 20–32.

Cintineo, J.L., K.M. Kuhl, J.A. Smith, M.L. Thomas, K.L. Ortega, T.M. Smith, and J. Gao, 2012: An objective high-resolution hail climatology of the contiguous United States. *Weather and Forecasting*, 27, 1235–1248.

Coles, S., 2001: *An Introduction to Statistical Modeling of Extreme Values.* Springer.

Cooley, D., D. Nychka, and P. Naveau, 2007: Bayesian spatial modeling of extreme precipitation return levels. *Journal of the American Statistical Association*, 102(479), 824–840.

Davison, A.C., S.A. Padoan, and M. Ribatet, 2012: Statistical modeling of spatial extremes. *Statistical Science*, 27(2), 161–186.

Gneiting, T., A.E. Raftery, A.H. Westveld III, and T. Goldman, 2005: Calibrated probabilistic forecasting using ensemble model output statistics and minimum CRPS estimation. *Monthly Weather Review*, 133(5), 1098–1118.

Grossi, P. and H. Kunreuther, 2005: *Catastrophe Modeling: A New Approach to Managing Risk.* Springer.

Hosking, J.R.M. and J.R. Wallis, 1997: *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press.

Li, F., D.R. Chavas, K.A. Reed, N. Rosenbloom, and D.T. Dawson, 2021: The role of elevated terrain and the Gulf of Mexico in the production of severe local storm environments over North America. *Journal of Climate*, 34, 7799–7819.

Lu, C., C. Lu, R.T. Lange, J. Foerster, J. Clune, and D. Ha, 2024: The AI Scientist: Towards fully automated open-ended scientific discovery. *arXiv:2408.06292*.

Miralles, O., A.C. Davison, and T. Schmid, 2023: Bayesian modeling of insurance claims for hail damage. *arXiv:2308.04926*.

Murillo, E.M. and C.R. Homeyer, 2019: Revised estimates of the maximum expected size of hail. *Journal of Applied Meteorology and Climatology*, 58, 2037–2056.

Murillo, E.M., C.R. Homeyer, and J.T. Allen, 2021: A 23-year severe hail climatology using GridRad MESH observations. *Monthly Weather Review*, 149, 945–958.

Ortega, K.L., 2018: Evaluating multi-radar, multi-sensor products for surface hailfall estimation. *Electronic Journal of Severe Storms Meteorology*, 13(1), 1–36.

Pickands, J., 1975: Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119–131.

Proceedings of the National Academy of Sciences, 2026: Information for authors. National Academy of Sciences.

Rasmussen, R.M. and A.J. Heymsfield, 1987: Melting and shedding of graupel and hail. *Journal of the Atmospheric Sciences*, 44, 2754–2763.

Scarrott, C. and A. MacDonald, 2012: A review of extreme value threshold estimation and uncertainty quantification. *REVSTAT*, 10(1), 33–60.

Smith, T.M., et al., 2016: Multi-Radar Multi-Sensor severe weather and aviation products: initial operating capabilities. *Bulletin of the American Meteorological Society*, 97, 1617–1630.

Swanson, K., W. Wu, N.L. Bulaong, J.E. Pak, and coauthors, 2025: The Virtual Lab of AI agents designs new SARS-CoV-2 nanobodies. *Nature*, 646, 716–723.

Wendt, N.A. and I.L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Weather and Forecasting*, 36, 645–659.

Williams, S.S., K.L. Ortega, T.M. Smith, A.E. Reinhart, and coauthors, 2022: Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms. *Bulletin of the American Meteorological Society*, 103, E838–E854.

Witt, A., et al., 1998: An enhanced hail detection algorithm for the WSR-88D. *Weather and Forecasting*, 13, 286–303.
