# Literature Review

**CONUS Hail Catastrophe Model v2.2**

---

## 1. Purpose

This literature review documents the scientific basis for the v2.2 hail catastrophe model methodology. It covers report bias, radar-based hail climatology, MESH correction, environmental filtering, extreme-value theory, spatial extremes, stochastic event simulation, topography, vulnerability, and non-stationarity.

The review is intentionally applied rather than exhaustive. Each citation is tied to a model decision: whether a data source is used as hazard input or validation, why a calibration step exists, why a statistical model is defensible, and which assumptions require disclosure.

---

## 2. SPC Report Bias

### Allen and Tippett (2015)

Allen and Tippett documented major biases in U.S. hail reports, including population-density effects, road-network effects, time-of-day reporting bias, and report-size rounding.

**Model implication:** SPC reports should not be the primary hazard field. They are useful for validation but incomplete.

### Allen, Tippett, and Sobel (2015)

This work connected hail occurrence to large-scale environmental predictors such as CAPE, shear, and freezing level.

**Model implication:** Environmental predictors are appropriate covariates for v2.1 conditional calibration and probabilistic filtering.

### Blair et al. (2011, 2017)

These studies documented difficulties in measuring large hail and differences between radar-inferred hail and ground reports.

**Model implication:** MESH validation against SPC should be interpreted cautiously.

### Reporting-threshold changes and observational non-stationarity

The 2010 U.S. severe-hail threshold change from 0.75 inch to 1.00 inch is visible in report climatologies and complicates trend interpretation. Long report records are therefore not automatically homogeneous, even before accounting for population, communication, and spotter-network changes.

**Model implication:** Long SPC time series can support context, but they should not be used directly to impose non-stationary hail-size trends in v2.1.

---

## 3. Radar-Based Hail Products

### Witt et al. (1998)

Witt et al. introduced the original MESH algorithm based on Severe Hail Index.

**Model implication:** MESH is physically motivated but warning-oriented, so calibration is required for climatological and actuarial use.

### Smith et al. (2016)

Smith et al. describe the operational MRMS system.

**Model implication:** MRMS provides recent public, spatially continuous radar hail products.

### Williams, Ortega, Smith, and coauthors (2022)

MYRORSS provides historical radar reanalysis for the contiguous United States.

**Model implication:** MYRORSS is the backbone of the early historical radar record.

### Wendt and Jirak (2021)

This work compares operational MRMS MESH hail climatology with Storm Data. MRMS severe MESH hail hours/days can exceed report-based estimates by **2–4×** locally, especially in low-population regions.

**Model implication:** Radar captures hail in underreported regions and times. Use this range when interpreting Stage 08 CONUS-wide event totals vs SPC validation.

### Murillo, Homeyer, and Allen (2021)

This GridRad-based hail climatology quantifies **severe hail days** on an 80 km grid using MESH at conventional (25.4 mm), skill-optimized (Table 1: MESHWitt 35.56 mm, MESH75 41.91 mm, MESH95 63.25 mm), and environmentally filtered thresholds. Unfiltered MESH75 at 25.4 mm over-diagnoses warm-season Gulf Coast convection relative to reports.

**Model implication:** GridRad can fill temporal gaps but requires calibration. Gap-fill runs through **2020-10-13**. Benchmark Stage 08 and per-cell hail-day diagnostics against Murillo et al. skill thresholds, not only 25.4 mm.

### Cintineo, Smith, Lakshmanan, and coauthors (2012)

Objective MESH climatology on a ~0.88° grid: with ≥ five pixels at 29 mm, the Great Plains shows maximum **severe hail days per year of roughly 11–12**; winter months are nearly devoid of severe hail CONUS-wide.

**Model implication:** Compare per-cell hail-day rates at **≥ 29 mm** (or Murillo MESH75 skill thresholds), not 25.4 mm alone. Implemented in `scripts/diagnostics/hail_day_climatology.py`.

### Per-cell hail-day climatology diagnostic (v2.2.1)

Stage 08 groups **CONUS-wide** active days into sparse events at the 25.4 mm damage threshold. That metric is not directly comparable to per-cell hail-day maps in Cintineo et al. (2012) or Murillo et al. (2021). The optional diagnostic `scripts/diagnostics/hail_day_climatology.py` therefore computes, for each 0.05° cell, mean annual **hail days per year** at six literature thresholds on the Stage 05 corrected archive, plus national any-cell totals and seasonal curves.

**Production run (2026-06, 9,797 convective days, 1998–2026):**

| Threshold | Great Plains max days/yr | GP mean days/yr | National any-cell days/yr (mean) |
|-----------|-------------------------:|----------------:|---------------------------------:|
| 25.4 mm conventional | 5.5 | 2.2 | 344 |
| 29.0 mm Cintineo/MRMS skill | 3.7 | 1.4 | 341 |
| 35.6 mm MESHWitt skill | 2.3 | 0.6 | 321 |
| 41.9 mm MESH75 skill | 1.6 | 0.2 | 287 |
| 50.8 mm significant severe | 0.6 | 0.1 | 229 |
| 63.3 mm MESH95 skill | 0.2 | 0.04 | 126 |

At 29 mm the Great Plains maximum (~3.7 days/yr at 0.05°) is below Cintineo's ~11–12 days/yr at coarser resolution but directionally consistent; the conventional 25.4 mm threshold inflates winter any-cell counts relative to SPC report-day seasonality. Stage 08's ~306 events/year aligns with national any-cell hail days, not with per-cell hail-alley maxima.

**Model implication:** Interpret Stage 08 λ (Poisson rate) as a national any-severe-MESH-day count. For literature benchmarking and threshold sensitivity, use `data/analysis/hail_day_climatology/`.

### GridRad reflectivity and SHI (implementation note)

NCAR GridRad NetCDF products (hourly v3, severe v4) expose physical reflectivity primarily as sparse `Reflectivity(Index)` with an `index` vector, not always as a dense `(Altitude, Latitude, Longitude)` array. The 3-D field `Nradecho` is an echo-related mask and must not be substituted for dBZ in Witt et al. (1998) SHI integration.

**Model implication:** Stage **04c** reconstructs dBZ from sparse reflectivity, normalizes longitudes, and documents daily peaks via GDAL tags. Mis-specified reflectivity fields produce scientifically silent all-zero gap days.

### Source-transition literature synthesis

MYRORSS, GridRad, and MRMS are all radar-derived, but they are not a single observing system. They differ in retrieval algorithm, temporal sampling, vertical representation, processing version, and operational quality control. The model therefore treats source transitions as an explicit algorithmic uncertainty rather than a minor engineering detail.

**Model implication:** Stage 05 calibration and Stage 06 source diagnostics are required before pooled tail fitting.

### 3.6 Convective-day daily aggregation (v2.2)

Radar archives store timesteps on **UTC calendar paths** (e.g. S3 prefixes by `YYYY/MM/DD`), but severe convection is organized into coherent **events** that often span local afternoon and evening and can cross **UTC midnight**. A daily maximum taken over calendar UTC `[00:00, 24:00)` can therefore split one storm system across two daily rasters or mix unrelated systems near the boundary.

**v2.2** defines each daily MESH raster as the cell-wise maximum over a **convective day**: the half-open interval **[D 12:00 UTC, D+1 12:00 UTC)**, with label `D` at the window start. Timesteps are assigned with `convective_day = (t − 12 h).date()`. This matches common practice in climate and hazard archives where a fixed synoptic hour (often **12 UTC**) delimits 24-hour accumulation periods, and it reduces artificial splitting of afternoon hail across UTC calendar dates.

| Reference | Relevance |
|-----------|-----------|
| Ortega et al. (2022) | MYRORSS provides 5-minute MESH; daily maxima are sensitive to which timesteps are included in the accumulation window. |
| Murillo et al. (2021) | GridRad MESH climatology aggregates high-frequency radar volumes; temporal sampling affects severe-hail tails. |
| Wendt and Jirak (2021) | MRMS MESH is available at sub-hourly cadence; daily hail statistics depend on the chosen 24-hour window. |
| Smith et al. (2016) | MRMS operational continuity motivates a consistent, documented daily definition across eras. |
| Allen and Tippett (2015) | SPC hail **report dates** reflect reporting practice; radar-first hazard should use an explicit, reproducible temporal rule rather than implicit UTC midnight. |
| Witt et al. (1998) | MESH is an instantaneous/severe-hail index integrated over short radar volumes; block-max aggregation to daily grids is a documented design choice in `methodology.md` §2.6. |

**Model implication:** Stages **01**, **02**, **04b**, and **04c** filter timesteps into 12 UTC → 12 UTC windows, write `CONVECTIVE_WINDOW_UTC` on GeoTIFFs, and stage GridRad under `by_convective_day/YYYYMMDD/`. v2.1 calendar-UTC production rasters are **not comparable** without full re-ingest. Downstream stages (05–15) consume the convective-day label from `mesh_YYYYMMDD.tif` filenames; Stage **07** DOY climatology still groups by day-of-year across years (not a change to convective-day definition).

---

## 4. MESH Correction and Filtering

### Murillo and Homeyer (2019; corrected 2021)

Murillo and Homeyer developed revised MESH relationships including MESH75.

**Model implication:** v2.1 retains the corrected MESH75 relationship.

### Ortega (2018)

Ortega evaluated radar products for surface hail estimation.

**Model implication:** Environmental filtering should use meteorological context.

### Gneiting et al. (2005)

This paper provides a probabilistic forecasting calibration framework.

**Model implication:** Conditional calibration and probabilistic filtering should be evaluated with reliability and Brier-style metrics.

### Calibration design implication

Radar hail calibration should be judged by both marginal distribution alignment and conditional behavior. A globally calibrated source can still be biased by season, region, terrain, or freezing-level regime. v2.1 therefore supports conditional calibration while retaining deterministic quantile mapping as a transparent fallback.

---

## 5. Extreme Value Theory

### Coles (2001)

Coles provides a practical foundation for GPD tail modeling, threshold diagnostics, and return levels.

**Model implication:** Tail outputs require explicit threshold diagnostics and uncertainty review.

### Hosking and Wallis (1997)

Hosking and Wallis establish regional frequency analysis using L-moments.

**Model implication:** Regional pooling of GPD shape parameter ξ is appropriate where local samples are sparse.

### Scarrott and MacDonald (2012)

This paper reviews threshold selection and uncertainty for peaks-over-threshold modeling.

**Model implication:** v2.1 automated threshold diagnostics are methodologically justified.

### Pickands, Balkema, and de Haan theorem

The peaks-over-threshold approach rests on the result that exceedances over a sufficiently high threshold converge to the generalized Pareto family for broad classes of parent distributions.

**Model implication:** The GPD tail is theoretically defensible, but only above a sufficiently high threshold. Threshold diagnostics are not optional.

---

## 6. Spatial Extremes

### Davison, Padoan, and Ribatet (2012)

This work reviews statistical modeling of spatial extremes.

**Model implication:** Independent cell-level tail modeling can understate aggregate risk. v2.1 includes diagnostics and leaves full spatial extremes for a future version.

### Cooley, Nychka, and Naveau (2007)

This work supports max-stable spatial extreme modeling.

**Model implication:** Max-stable models are future v3.0 candidates, not v2.1 scope.

### Spatial smoothing vs spatial extremes

Distance-weighted smoothing improves noisy marginal return-level maps, but it does not define a joint tail model. Spatial dependence in hail is event-driven: the same storm footprint produces dependence across cells. v2.1 addresses this primarily through sparse stochastic event templates rather than a formal max-stable process.

**Model implication:** Analytical maps should be compared with event-based stochastic maps before interpretation.

---

## 7. Stochastic Event Modeling

### Miralles, Davison, and Schmid (2023)

This work models hail insurance claims with spatial stochastic structures.

**Model implication:** Stochastic event catalogs and perturbations are appropriate for hail risk modeling.

### Commercial severe convective storm model practice

Commercial models generally use event catalogs, perturbations, spatial dependence, exposure, and vulnerability.

**Model implication:** v2.1 implements public-data hazard components but not full production loss modeling.

### Event-count dispersion

Severe convective events are temporally clustered by synoptic regime. A Poisson annual-count model is transparent and reproducible, but it can understate variance if the historical count distribution is overdispersed.

**Model implication:** Stage 13 should eventually test the annual event-count index of dispersion and consider a negative-binomial alternative.

---

## 8. Topography

### Li et al. (2021)

Li and coauthors discuss the role of elevated terrain and Gulf moisture in severe storm environments.

**Model implication:** Terrain matters for hail environments and hail survival.

### Andrews et al. (2024)

This work describes elevated mixed-layer climatology over CONUS and northern Mexico using ERA5.

**Model implication:** Terrain-linked severe storm environments support including topographic context.

### Rasmussen and Heymsfield (1987)

This hail microphysics work documents melting and shedding processes relevant to hail survival below the freezing level.

**Model implication:** Stage 12 terrain correction should remain bounded and disclosed as a first-order approximation, not a complete melting model.

---

## 9. Vulnerability

### Brown et al. (2015)

Brown and coauthors evaluated hail damage using property insurance claims.

**Model implication:** Roof type, material, age, and construction class matter. Stage 14 is placeholder until claims-calibrated.

### IBHS impact-testing literature

IBHS testing supports different vulnerability by roof material and impact resistance.

**Model implication:** Complete loss modeling requires detailed exposure and vulnerability calibration.

### Vulnerability calibration implication

Hail-size hazard alone is insufficient for insured loss estimation. Claims-calibrated vulnerability must account for construction, roof material, age, impact resistance, repair-cost inflation, deductible structure, and reporting thresholds.

**Model implication:** Stage 14 curves are integration-test priors, not production damage functions.

---

## 10. Climate Non-Stationarity

The v2.1 model remains stationary because the radar record is short relative to long-return-period estimation. Recommended diagnostics include Mann-Kendall trend tests and rolling 10-year summaries.

**Model implication:** Do not force trend into the tail model without stronger evidence and a longer homogeneous record.

Stationarity is a pragmatic modeling assumption, not a claim that the hail climate is constant. The immediate scientific control is disclosure: return-period products should state the record window and the stationary assumption explicitly.

---

## 11. AI-Assisted Scientific Software and Research Agents

The PNAS-style article attached to this repository makes a second claim beyond hail modeling: that human-directed frontier AI agents can accelerate the construction of transparent scientific infrastructure. That claim sits in a fast-moving literature on language models as scientific assistants, tool-using agents, multi-agent research systems, and autonomous experimenters.

### Boiko et al. (2023)

Boiko and coauthors introduced Coscientist, a GPT-4-driven system that used documentation search, code execution, and experimental automation to plan and execute chemistry workflows.

**Model implication:** The relevant comparison is not casual chatbot use. The stronger precedent is tool-using AI embedded in a supervised scientific workflow.

### Lu et al. (2024)

The AI Scientist framework proposed an end-to-end autonomous scientific discovery loop including idea generation, code execution, experiment running, visualization, paper writing, and simulated review.

**Model implication:** The hail project should position itself differently: not as autonomous discovery, but as human-directed scientific infrastructure construction with explicit provenance, tests, and review.

### Swanson et al. (2025)

The Virtual Lab study demonstrated a multi-agent AI-human collaboration for interdisciplinary biological research, including an LLM principal-investigator agent, specialized scientist agents, human feedback, and downstream experimental validation.

**Model implication:** A publishable AI-process claim needs concrete artifacts and validation, not merely a statement that AI helped. The hail manuscript should include a table linking AI-assisted interventions to code changes, tests, documentation, and scientific risk reduction.

### AI authorship and disclosure policy

Journal policy and research-integrity discussions increasingly converge on three controls: AI use must be disclosed, AI systems should not be listed as authors, and human authors remain responsible for verification. PNAS-family instructions require disclosure of generative-AI use for manuscript preparation and emphasize data, code, and methods availability.

**Model implication:** The PNAS article must include a detailed AI-use disclosure in Materials and Methods, verify exact model names before submission, and preserve enough development evidence for reviewers to evaluate the process.

### Reproducible computational science

The AI contribution is strongest when connected to reproducibility. A repository with durable stage outputs, manifests, tests, CI, logs, and versioned releases is more scientifically valuable than an informal transcript of AI use. Code and data availability guidance from PNAS-family journals and FORCE11-style software citation principles supports archiving the exact repository state used for the article.

**Model implication:** Before submission, the code release should receive a DOI and the manuscript should cite both the software release and public input datasets.

---

## 12. Novelty Relative to Prior Literature

### Hail science novelty

The project is not novel merely because it uses MESH. The MESH algorithm, MYRORSS, MRMS climatologies, GridRad MESH climatology, and MESH correction literature are established. The scientific novelty is the integration of those ingredients into a transparent US catastrophe-hazard pipeline that produces daily corrected rasters, coverage manifests, sparse historical events, analytical return-period maps, and stochastic catalog diagnostics from public data.

**Model implication:** The manuscript should claim integration, reproducibility, provenance, and hazard-model construction, not invention of the underlying radar hail estimator.

### Catastrophe-model novelty

Commercial catastrophe models routinely include stochastic event sets, vulnerability, exposure, and financial modules, but their internal data and algorithms are often proprietary. Academic hail work often focuses on climatology, radar retrieval, reports, environments, or claims subproblems rather than a full reproducible hazard pipeline.

**Model implication:** The strongest contribution is a public, auditable hazard-side catastrophe model scaffold. The paper should clearly state that exposure, claims-calibrated vulnerability, and financial loss are outside v2.1 scope.

### AI-process novelty

The AI-agent literature demonstrates autonomous and semi-autonomous research systems, but many examples are benchmark-focused, narrow-domain laboratory systems, or demonstrations of agent capability. This repository documents AI assistance in a production-style scientific codebase: branch management, CI repair, warning cleanup, source-manifest design, data-format bug discovery, map QA, long-run monitoring, and manuscript preparation.

**Model implication:** The manuscript can be novel if it reports the development process with enough specificity to be evaluated: what AI did, what humans decided, what tests passed, what defects were found, and where AI outputs were rejected or corrected.

### PNAS readiness implication

The project is plausible for PNAS only if the final manuscript connects the domain result to a broad scientific question. A narrow framing such as "we built a hail model with AI" is likely too incremental for a general journal. A stronger framing is: "human-directed frontier AI agents can help produce transparent, auditable scientific infrastructure for societally important hazards, demonstrated through a public radar-first US hail catastrophe model."

The claim should remain conditional until the full pipeline finishes. Final maps must pass geographic sanity checks, source-transition diagnostics, validation against SPC reports, tail-stability review, stochastic-vs-analytical comparison, and uncertainty disclosure.

---

## 13. References

Allen, J.T. and M.L. Tippett, 2015: The characteristics of United States hail reports: 1955–2014. *Electronic Journal of Severe Storms Meteorology*, 10(3), 1–31.

Allen, J.T., M.L. Tippett, and A.H. Sobel, 2015: An empirical model relating U.S. monthly hail occurrence to large-scale meteorological environment. *Journal of Advances in Modeling Earth Systems*, 7(1), 226–243.

Andrews, M.S., et al., 2024: Climatology of the elevated mixed layer over the contiguous United States and Northern Mexico using ERA5: 1979–2021. *Journal of Climate*, 37, 1833–1851.

Blair, S.F., et al., 2011: A radar-based assessment of the detectability of giant hail. *Electronic Journal of Severe Storms Meteorology*, 6(7), 1–30.

Blair, S.F., et al., 2017: High-resolution hail observations: implications for NWS warning operations. *Weather and Forecasting*, 32, 1101–1119.

Boiko, D.A., R. MacKnight, B. Kline, and G. Gomes, 2023: Autonomous chemical research with large language models. *Nature*, 624, 570–578.

Brown, T.M., et al., 2015: Evaluating hail damage using property insurance claims data. *Weather, Climate, and Society*, 7(3), 197–210.

Coles, S., 2001: *An Introduction to Statistical Modeling of Extreme Values.* Springer.

Cooley, D., D. Nychka, and P. Naveau, 2007: Bayesian spatial modeling of extreme precipitation return levels. *Journal of the American Statistical Association*, 102(479), 824–840.

Cintineo, J.L., K.M. Kuhl, J.A. Smith, M.L. Thomas, K.L. Ortega, T.M. Smith, and J. Gao, 2012: An objective high-resolution hail climatology of the contiguous United States. *Weather and Forecasting*, 27, 1235–1248.

Davison, A.C., S.A. Padoan, and M. Ribatet, 2012: Statistical modeling of spatial extremes. *Statistical Science*, 27(2), 161–186.

Gneiting, T., A.E. Raftery, A.H. Westveld III, and T. Goldman, 2005: Calibrated probabilistic forecasting using ensemble model output statistics and minimum CRPS estimation. *Monthly Weather Review*, 133(5), 1098–1118.

Hosking, J.R.M. and J.R. Wallis, 1997: *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press.

Li, F., D.R. Chavas, K.A. Reed, N. Rosenbloom, and D.T. Dawson, 2021: The role of elevated terrain and the Gulf of Mexico in the production of severe local storm environments over North America. *Journal of Climate*, 34, 7799–7819.

Lu, C., C. Lu, R.T. Lange, J. Foerster, J. Clune, and D. Ha, 2024: The AI Scientist: Towards fully automated open-ended scientific discovery. *arXiv:2408.06292*.

Miralles, O., A.C. Davison, and T. Schmid, 2023: Bayesian modeling of insurance claims for hail damage. *arXiv:2308.04926*.

Murillo, E.M. and C.R. Homeyer, 2019: Revised estimates of the maximum expected size of hail. *Journal of Applied Meteorology and Climatology*, 58, 2037–2056.

Murillo, E.M., C.R. Homeyer, and J.T. Allen, 2021: A 23-year severe hail climatology using GridRad MESH observations. *Monthly Weather Review*, 149, 945–958.

Ortega, K.L., 2018: Evaluating multi-radar, multi-sensor products for surface hailfall estimation. *Electronic Journal of Severe Storms Meteorology*, 13(1), 1–36.

Pickands, J., 1975: Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119–131.

Rasmussen, R.M. and A.J. Heymsfield, 1987: Melting and shedding of graupel and hail. *Journal of the Atmospheric Sciences*, 44, 2754–2763.

Scarrott, C. and A. MacDonald, 2012: A review of extreme value threshold estimation and uncertainty quantification. *REVSTAT*, 10(1), 33–60.

Smith, T.M., et al., 2016: Multi-Radar Multi-Sensor severe weather and aviation products: initial operating capabilities. *Bulletin of the American Meteorological Society*, 97, 1617–1630.

Swanson, K., W. Wu, N.L. Bulaong, J.E. Pak, and coauthors, 2025: The Virtual Lab of AI agents designs new SARS-CoV-2 nanobodies. *Nature*, 646, 716–723.

Wendt, N.A. and I.L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Weather and Forecasting*, 36, 645–659.

Witt, A., et al., 1998: An enhanced hail detection algorithm for the WSR-88D. *Weather and Forecasting*, 13, 286–303.

Williams, S.S., K.L. Ortega, T.M. Smith, A.E. Reinhart, and coauthors, 2022: Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms. *Bulletin of the American Meteorological Society*, 103, E838–E854.
