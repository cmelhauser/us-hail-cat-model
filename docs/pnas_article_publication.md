# Scientific Infrastructure at Agent Speed: An Open Source US Hail Hazard Model

> **STALE CHECKED-IN RENDER (do not submit).** This file was last generated from a
> **2026-07-09 / model 2.2.2** metrics freeze and still embeds superseded counts
> (for example hardcoded `173,766` pairs and a GridRad `— missing_source`
> template artifact). Regenerate only after
> `data/analysis/pnas_article_metrics.json` exists for the verified v2.3.0 run:
> `.venv/bin/python scripts/diagnostics/render_pnas_publication_md.py`.
> Current draft methods live in `docs/pnas_article_ai_hail_model.md`.

**Publication manuscript (PNAS-style)**

**Model version:** 2.2.2 (stale render; live codebase is 2.3.0)

**Metrics freeze:** 2026-07-09 11:47:13

**Code:** [github.com/cmelhauser/us-hail-cat-model](https://github.com/cmelhauser/us-hail-cat-model)

**Corresponding author:** Christopher Melhauser (christopher.melhauser@gmail.com)

---

## Significance Statement

Catastrophe models are usually built by specialized teams over long development cycles. This study describes a reproducible, radar-first US hail catastrophe hazard model built from public data through a human-directed AI workflow, with explicit source provenance, validation against SPC reports, and a documented AI-assisted development audit trail.

---

## Abstract

Artificial intelligence is beginning to alter not only how scientific results are analyzed, but how scientific infrastructure is built. We present a case study in AI-assisted catastrophe model development: a US hail hazard model constructed as a fully automated, reproducible pipeline using frontier language-model agents under human direction. The model ingests public radar and environmental datasets—MYRORSS, GridRad or GridRad-Severe, operational MRMS, ERA5 isotherm fields, and SPC hail reports for validation—and builds a 0.05° CONUS archive of **9,797** convective days (1998–2026). Era-pooled calibration, a five-pass GridRad artifact filter, and range-dependent debias produce corrected MESH75; **7,792** sparse historical events are identified at a **29 mm** skill threshold (**268.7** yr⁻¹). Regional extreme-value models and spatial pooling yield analytical return-period maps; a **50,000-year** stochastic catalog extends the hazard layer. We document both the scientific model and the development process—literature synthesis, implementation, testing, data QA, documentation, and run monitoring—with `claude-sonnet-4-6`, `claude-opus-4-6` (Anthropic, May 2026), and `gpt-5.5-medium` (OpenAI, May 2026) under human scientific responsibility.


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

---

## Hail Hazard Model

*(Summary; full methodological detail in `docs/pnas_article_ai_hail_model.md` and `docs/methodology.md`.)*

The model uses a fixed **0.05°** CONUS grid (520 × 1180), convective-day MESH rasters (12 UTC → 12 UTC), era-pooled quantile mapping to a GridRad anchor, optional range debias, a five-pass GridRad artifact filter, sparse historical events at **29 mm**, regional GPD tails with L-moment pooling, **150 km** spatial CDF smoothing, CONUS masking with freezing-level-aware topographic correction, and **50,000-year** sparse stochastic resampling.

---

## Results

### Data coverage and hazard pipeline (model 2.2.2)

The corrected convective-day archive contains **9,797** daily MESH rasters (1998–2026): **5,023** MYRORSS days (manifest: 4994 ok / 20 missing_source), **3,209** GridRad gap-fill days (2661 ok / **499** missing_source — historical freeze; refresh from metrics), and **2,060** MRMS days. Stage **01** MYRORSS re-ingest with corrected WDSS-II sparse-grid axes completed **2026-07-08**, restoring eastern CONUS coverage truncated in earlier ingests.

### Event catalog and dispersion

Stage **08** identified **7,792** sparse historical events at **29 mm** over 29 years (**268.7** yr⁻¹; σ = 95.5). The index of dispersion (variance/mean) is **33.94**, indicating strong year-to-year clustering relative to a Poisson process.

### Hail-day climatology

At **29 mm**, Great Plains per-cell maxima reach **5.72** hail days yr⁻¹ (mean **3.01** yr⁻¹ across active cells). National any-cell totals average **287.0** days yr⁻¹ (Fig. 5–6).

### Validation against SPC reports

Stage **06** produced **173,766** report–MESH pairs on the rebuilt corrected archive. Summary excerpt:

```text
MESH75 vs SPC Hail Reports — Validation Summary
============================================================
Generated: 2026-07-08 17:32:29

Total report–MESH pairs: 173,766
Date range: 20040301 to 20260503

Overall bias (MESH75 − SPC): -0.343 inches
Overall RMSE: 1.006 inches
Overall correlation: -0.034

Severe hail (>=1.0") detection:
  POD: 0.483  FAR: 0.270  CSI: 0.410
  Hits: 68,217  Misses: 73,154  False alarms: 25,170

Diurnal coverage:
  Day (06–22 UTC) reports: 71,223, MESH detection rate: 64.8%
  Night (22–06 UTC) reports: 102,543, MESH detection rate: 63.4%

Calibration by size bin:
Bin                 N     SPC  MESH75    Bias    RMSE    POD
-------------------------------------------------------
0.75-1.00"      32395    0.80    1.27  +0.469   0.641  0.967
1.00-1.50"      87831
```

### Analytical return periods

Smoothed analytical maps (Stages **09–10–12**) yield CONUS maxima of **123.0 mm** at 100 years and **204.1 mm** at 1,000 years (327,220 CONUS cells ≥ 25.4 mm on the 100-yr map). Eastern CONUS hazard is restored relative to the pre-fix MYRORSS ingest (Figs. 8–9).

### Stochastic catalog

Stage **13** 50,000-year sparse resampling was **in progress** at manuscript build time; Figs. 12–13 and final stochastic peak tables are inserted when `data/stochastic/maps/` exists. Re-run:

```bash
.venv/bin/python scripts/diagnostics/render_pnas_article_figures.py
.venv/bin/python scripts/diagnostics/render_pnas_publication_md.py
```


---

## Figures

**Figure 1.** Radar data sources and splice dates for the convective-day MESH archive (12 UTC → 12 UTC labels).

![Figure 1](figures/pnas/fig01_data_source_timeline.png)

**Figure 2.** Source-coverage manifest status by year (MYRORSS, GridRad gap-fill, MRMS).

![Figure 2](figures/pnas/fig02_manifest_coverage_by_year.png)

**Figure 3.** Daily CONUS peak MESH distributions at source-transition windows.

![Figure 3](figures/pnas/fig03_source_transition_daily_peaks.png)

**Figure 4.** Era-pooled calibration: raw vs corrected daily peak ECDFs by radar era.

![Figure 4](figures/pnas/fig04_calibration_ecdf_by_source.png)

**Figure 5.** National seasonal cycle of any-cell hail days by MESH75 threshold.

![Figure 5](figures/pnas/fig05_seasonal_national_hail_days.png)

**Figure 6.** Mean annual hail days per 0.05° cell at the 29 mm skill threshold (Lambert Conformal).

![Figure 6](figures/pnas/fig06_hail_days_per_year_29mm.png)

**Figure 7.** MESH75 vs SPC validation: bias and probability of detection by report-size bin.

![Figure 7](figures/pnas/fig07_validation_by_size_bin.png)

**Figure 7 (supplement).** Collocated SPC report size vs MESH75.

![Figure 7 (supplement)](figures/pnas/fig07b_mesh_vs_spc_scatter.png)

**Figure 8.** Analytical 100-year return-period hail map (smoothed; Lambert Conformal).

![Figure 8](figures/pnas/fig08_rp_100yr_analytical.png)

**Figure 9.** Analytical 1,000-year return-period hail map (smoothed; Lambert Conformal).

![Figure 9](figures/pnas/fig09_rp_1000yr_analytical.png)

**Figure 10.** Annual sparse historical event counts at 29 mm (Stage 08).

![Figure 10](figures/pnas/fig10_annual_event_counts.png)

**Figure 11.** Human-directed AI-assisted development loop.

![Figure 11](figures/pnas/fig11_ai_development_workflow.png)

**Figure 12.** Stochastic 100-year empirical return-period map (50,000-yr catalog; Lambert Conformal).

![Figure 12](figures/pnas/fig12_rp_100yr_stochastic.png)

**Figure 13.** Analytical vs stochastic 100-year return-period comparison (Lambert Conformal).

![Figure 13](figures/pnas/fig13_analytical_vs_stochastic.png)


---

## Discussion

This work contributes a public-data hail hazard model and a case study in AI-assisted scientific software development. The hail model demonstrates that a radar-first pipeline can be built from public datasets, calibrated across source eras, converted into sparse historical events, and extended into a stochastic catalog.

Separating radar hazard from report validation remains the central scientific design choice: MESH provides a physically motivated spatial field, while SPC reports test consistency with independent human observations. Sparse event storage is the central computational choice—localized footprints are resampled at catalog scale without dense `(n_events, n_rows, n_cols)` arrays.

The **2026-07-08** rebuild incorporated a MYRORSS coordinate-fix re-ingest (eastern CONUS restored), a five-pass GridRad artifact filter with spatiotemporal persistence, and refreshed range debias from **173,766** validation pairs. Event frequency fell from the prior smoke-affected eastern truncation (**8,798** → **7,792** events; **303** → **269** yr⁻¹), while analytical return-period peaks increased materially once eastern hail entered the EVT record—underscoring that ingest geometry and artifact QA are first-order hazard uncertainties, not secondary polish.

AI assistance (**theonlymuffinbot**) was most valuable inside a disciplined repository: explicit tests, stage boundaries, manifests, and git-reviewed changes. Agents accelerated audit breadth; the human operator retained methodological decisions and accountability.


---

## Limitations

The model is hazard-only and does not include exposure, vulnerability curves, or financial loss in the repository. **Future work** (documented in `docs/methodology.md` §14) includes claims-calibrated MDR functions informed by property-insurance hail studies (Brown et al. 2015), geocoded exposure, and loss aggregation — the natural extension after the hazard layer validated here. Tail estimates are point estimates and do not yet include bootstrap confidence intervals. The model assumes stationarity over the radar record. Source transitions among MYRORSS, GridRad, and MRMS remain a key uncertainty. The stochastic catalog uses a Poisson event-count model, which may underrepresent overdispersion in active severe-convective years (observed index of dispersion **11.7** in the historical event catalog; negative-binomial sensitivity reserved). Stochastic empirical peaks exceed analytical maps at moderate return periods, flagging GPD tail review for the longest return levels.

The AI-process analysis is also limited. This is a case study rather than a randomized comparison of human-only and AI-assisted development. The exact contribution of each AI system is difficult to isolate because the workflow was interactive and iterative. The article therefore frames AI as an enabling workflow component, not as an independently validated replacement for expert model development.

---

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

Large language models were used in the development of the codebase, documentation, monitoring workflow, and manuscript draft. All such AI collaboration is credited under the project pseudonym **theonlymuffinbot** (not a separate GitHub repository; sole code remote `cmelhauser/us-hail-cat-model`). The underlying systems included `claude-sonnet-4-6` and `claude-opus-4-6` (Anthropic, accessed May 2026) and `gpt-5.5-medium` (OpenAI, accessed May 2026). Assistance attributed to **theonlymuffinbot** included literature synthesis, code generation, code review, test authoring, documentation editing, shell-command planning, and long-running pipeline monitoring. Git operations (commit, push, merge) were performed by the human operator. AI outputs were reviewed, edited, tested, and accepted under human direction. Scientific accountability remains with Christopher Melhauser.

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
