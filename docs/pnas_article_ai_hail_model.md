# The Age of AI: Building a US Catastrophe Hail Model

**Draft manuscript for PNAS-style submission**

**Working title:** The Age of AI: Building a US Catastrophe Hail Model  
**Article type:** Perspective-informed research article / computational science case study  
**Status:** Draft with results placeholders pending completion of full pipeline run  
**Target journal:** Proceedings of the National Academy of Sciences (PNAS)  

---

## Author Line

**[Author Name(s) to be added]**

**Affiliations:** [To be added]

**Corresponding author:** [To be added]

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

Artificial intelligence is beginning to alter not only how scientific results are analyzed, but how scientific infrastructure is built. We present a case study in AI-assisted catastrophe model development: a US hail hazard model constructed as a fully automated, reproducible pipeline using frontier language-model agents under human direction. The model ingests public radar and environmental datasets, including MYRORSS, GridRad or GridRad-Severe, operational MRMS, ERA5 isotherm fields, and SPC hail reports for validation. It builds a 0.05 degree CONUS hail archive, calibrates radar-derived MESH to MESH75, constructs sparse historical hail events, fits regional extreme-value models, applies spatial smoothing and topographic correction, and generates a long stochastic event catalog. We describe both the scientific model and the development process: literature review, code generation, debugging, testing, documentation, run monitoring, and methodological hardening performed with Claude Opus v6 and ChatGPT 5.5 [verify exact model/version names before submission]. Final hazard results, validation statistics, return-period maps, and stochastic comparisons will be inserted after the full pipeline completes. This study frames AI-assisted model building as a reproducible scientific workflow rather than a code-generation novelty.

---

## Introduction

Severe convective storms are among the most frequent and costly natural hazards in the United States, and hail is a major contributor to insured loss. Yet hail hazard remains difficult to model because direct observations are incomplete, storm reports are biased by human presence and reporting practices, radar products require calibration, and long-return-period estimation must extrapolate from a short homogeneous record.

At the same time, scientific software development is entering a new phase. Frontier language models can read code, generate tests, inspect documentation, design workflows, reason over literature, and operate long-running computational processes. The relevant scientific question is no longer whether AI can write isolated functions. It is whether AI can help build, document, validate, and maintain a nontrivial end-to-end scientific model under human supervision.

This paper presents a concrete case study: the construction of a US hail catastrophe hazard model using AI-assisted development. The work has two linked contributions. First, it describes a radar-first hail model that converts public atmospheric data into gridded hazard, return-period maps, and stochastic event catalogs. Second, it documents the process by which AI agents were used to accelerate literature review, pipeline implementation, debugging, testing, documentation, data-quality review, and run monitoring.

The title phrase "The Age of AI" is used deliberately. The study does not claim that AI replaces scientific judgment. Rather, it examines a practical collaboration pattern: a human model owner sets goals, evaluates outputs, makes methodological decisions, and directs priorities, while AI systems perform high-volume implementation, synthesis, audit, and operational monitoring tasks. The resulting artifact is not merely a manuscript or a prototype, but a runnable repository with explicit assumptions, tests, validation commands, source-provenance records, and documentation.

### Relationship to prior work

The hail-science contribution builds on four mature literatures. The first is the literature on human hail-report bias, which shows that severe-hail reports are shaped by population, roads, observer practices, report-size rounding, and reporting thresholds. The second is radar-based hail estimation, including the original Severe Hail Index and MESH algorithm, corrected MESH relationships, MYRORSS, MRMS, and GridRad-based climatologies. The third is extreme-value analysis for rare environmental hazards, including peaks-over-threshold models, generalized Pareto tails, regional pooling, threshold diagnostics, and spatial-extremes warnings. The fourth is catastrophe-model practice: sparse event footprints, stochastic catalogs, vulnerability, and uncertainty communication.

The AI-process contribution builds on a rapidly emerging literature on large language models as scientific assistants and agents. Recent systems have demonstrated tool-using agents for chemistry, multi-agent scientific collaboration, autonomous idea generation, code execution, experiment execution, simulated review, and domain-specific research workflows. These studies show that AI systems can contribute to parts of scientific work, but most are either benchmark-oriented, laboratory-specific, or focused on autonomous discovery within a narrow scaffold. This manuscript instead studies an applied scientific-infrastructure build: a human-directed, multi-month repository that combines literature review, scientific modeling, data engineering, CI, documentation, long-running execution, and manuscript preparation.

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
- placeholder vulnerability curves for integration testing.

---

## Data

The model uses radar-derived hail information as the primary hazard field. Human hail reports are used for validation, not as the gridded hazard truth.

### MYRORSS

MYRORSS provides the early historical radar reanalysis period from April 1998 through December 2011. The pipeline reads both plain `.netcdf` and `.netcdf.gz` archive objects, decodes sparse source files, accumulates daily maximum MESH, aggregates to a 0.05 degree grid, and writes GeoTIFF outputs. A daily manifest records source availability, source file counts, read errors, active cells, maximum MESH, and processing status.

### GridRad and GridRad-Severe

GridRad or GridRad-Severe is used to fill the gap between MYRORSS and operational MRMS. Severe Hail Index is derived from three-dimensional reflectivity and ERA5 isotherm fields, then converted to MESH75.

### MRMS

Operational MRMS supplies the recent radar era from 2020 onward. The pipeline handles native orientation and longitude conventions before writing daily model-grid MESH rasters.

### ERA5

ERA5 monthly 0 C and -20 C isotherm heights support GridRad SHI computation and environmental filtering.

### SPC hail reports

SPC reports support validation and calibration review. Because reports are affected by population, road networks, report practices, and reporting threshold changes, they are not used as the primary hazard field.

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

MYRORSS and MRMS MESH products are converted to corrected MESH75. GridRad-derived MESH75 is calibrated through optional conditional calibration or deterministic quantile mapping. Environmental filtering may be probabilistic when model artifacts are available, but deterministic fallback behavior is required and can be forced with `--skip-ml`.

### Event identification

Daily corrected rasters are thresholded at 25.4 mm. Spatially and temporally coherent footprints are merged into events under constraints on temporal gap, buffered overlap, event duration, centroid displacement, and peak intensity jump. Events are stored as sparse arrays:

```text
rows_event_id
cols_event_id
vals_event_id
```

This sparse representation is central to memory safety in the stochastic catalog.

### Extreme value modeling

At each grid cell, annual maximum hail is represented by a zero-inflated frequency-severity model. Positive values are modeled with a lognormal body and a generalized Pareto tail. Tail shape parameters are pooled regionally to reduce instability from sparse exceedance samples. Threshold diagnostics record exceedance counts, mean residual life behavior, shape stability, goodness-of-fit, and selected thresholds.

### Stochastic catalog

The stochastic catalog resamples historical sparse event templates. Annual event counts are drawn from a Poisson distribution, event dates are sampled from a smoothed seasonal distribution, templates are selected by seasonal similarity, and footprints receive sparse spatial translation, lognormal intensity perturbation, and optional shape perturbation. Analytical and stochastic return-period maps are compared as a structural diagnostic.

---

## AI-Assisted Development Process

### Agent roles

The repository was developed through interaction with two frontier AI systems: Claude Opus v6 and ChatGPT 5.5 [verify exact model/version names before submission]. The agents were used as research assistants, software engineers, documentation editors, code reviewers, and operational monitors.

The human operator remained responsible for scientific direction, acceptance criteria, prioritization, and interpretation. The AI systems were not treated as authors of scientific claims, but as tools used in model construction and manuscript preparation.

### Development activities

AI assistance was used for:

- reviewing the existing repository;
- identifying methodological risks;
- implementing code hardening;
- adding a Stage 01 source manifest;
- diagnosing archive-format issues in MYRORSS;
- updating README and scientific documentation;
- writing and running targeted tests;
- managing git branches, commits, pull requests, and merges;
- monitoring a long-running full pipeline run;
- distinguishing missing-source days from true no-hail days;
- drafting manuscript text and documentation.

### Development-process evidence

The AI-assisted development process is reported through quantitative repository and workflow metrics. Final values will be inserted after the full model run and manuscript freeze:

```text
Repository start date:
Repository freeze date for submission:
Total commits:
Commits substantially assisted by AI:
Pull requests opened and merged:
Files changed by category: code, tests, docs, configuration
Lines of code and documentation added:
Automated test count before and after AI-assisted hardening:
CI runs passed / failed / rerun:
Pipeline stages monitored by AI:
Detected defects attributable to AI-assisted audit:
Human interventions and methodological decisions:
Approximate wall-clock development time:
Approximate model/API cost, if available and appropriate:
```

Representative AI-assisted interventions are summarized in Table [X], with each intervention tied to a concrete repository artifact: issue discovered, evidence, patch, validation, and residual risk.

### Example: source manifest discovery

During a pre-run review, many apparently empty daily GeoTIFFs were found. AI-assisted investigation showed that some early MYRORSS archive files were plain `.netcdf` rather than `.netcdf.gz`, and the previous reader ignored them. The Stage 01 script was updated to read both formats, and a manifest was added to distinguish missing source from no-hail days. This illustrates the model-building value of AI agents as persistent auditors: the issue was not a novel algorithmic insight, but a data-engineering defect that would have materially affected the historical record.

### Reproducibility controls

The repository includes documentation, pre-run review notes, validation commands, gitignored generated data products, stage logs, and a staged execution plan. AI-generated changes were reviewed through diffs, tests, py_compile checks, smoke runs, and branch synchronization.

### Governance and disclosure

AI use is disclosed in the Materials and Methods section. The disclosure names the systems used, the categories of work performed, and the human-review controls applied to AI-generated outputs. AI systems are not listed as authors because they cannot take responsibility for accuracy, integrity, or accountability. All AI outputs used in the code, documentation, analysis, and manuscript were reviewed and accepted under human responsibility.

---

## Results

**This section will be completed after the full pipeline run finishes.**

### Stage completion and data coverage

Placeholder values to insert:

```text
Total daily MESH rasters:
MYRORSS manifest rows:
Missing-source days:
No-hail source-present days:
Read-error days:
Corrected MESH75 rasters:
Historical event count:
Years represented in annual maxima:
```

### Validation against SPC reports

Placeholder values to insert:

```text
Matched SPC-radar pairs:
Mean bias by report-size bin:
RMSE:
MAE:
Probability of detection by threshold:
Regional validation summary:
Source-era comparison:
```

### Return-period maps

Placeholder values to insert:

```text
10-year hail-size range:
100-year hail-size range:
500-year hail-size range:
1,000-year hail-size range:
50,000-year hail-size range:
Peak hazard regions:
Areas of analytical-vs-stochastic divergence:
```

### Stochastic catalog

Placeholder values to insert:

```text
Simulated years:
Synthetic events:
Mean annual event count:
Index of dispersion:
Empirical RP map agreement with analytical RP:
PET occurrence table summary:
PET aggregate table summary:
```

### AI-assisted development results

Placeholder values to insert:

```text
Development duration:
Number of AI-assisted commits:
Number of AI-detected defects fixed before full run:
Number of documentation pages expanded:
Number of automated tests added or repaired:
Number of long-run monitoring checks:
Examples of AI audit findings:
```

### Figure placeholders

Expected main figures:

1. AI-assisted development workflow and repository architecture.
2. Data-source timeline: MYRORSS, GridRad, MRMS, ERA5, SPC validation.
3. Stage 01 manifest coverage and source-status summary.
4. Corrected annual hail climatology.
5. Analytical 100-year and 1,000-year hail return-period maps.
6. Stochastic vs analytical return-period comparison.
7. Validation against SPC reports.
8. AI-assisted development evidence table or timeline.

### Table placeholders

Expected main or supplementary tables:

1. Data sources, temporal coverage, variables, and model role.
2. Pipeline stages, inputs, outputs, and validation checks.
3. Stage 01 manifest status counts by year.
4. AI-assisted development interventions and validation evidence.
5. Model limitations and mitigation controls.

---

## Discussion

This work contributes a public-data hail hazard model and a case study in AI-assisted scientific software development. The hail model demonstrates that a radar-first pipeline can be built from public datasets, calibrated across source eras, converted into sparse historical events, and extended into a stochastic catalog. The AI process demonstrates that language-model agents can support not only code generation, but also literature synthesis, data QA, documentation, version control, and operational monitoring.

The most important scientific design choice is the separation of radar hazard from report validation. Hail reports remain essential, but their observational bias makes them unsuitable as the primary gridded hazard field. Radar-derived MESH provides a physically motivated spatial field, while validation against reports tests consistency with independent human-observed outcomes.

The most important computational design choice is sparse event storage. Hail footprints are localized, and dense event cubes would waste memory and constrain stochastic simulation. Sparse templates allow event perturbation and resampling at catalog scale.

The most important AI-process lesson is that AI assistance is most powerful when embedded in a disciplined workflow. The agents were useful because the repository had explicit tests, logs, stage boundaries, documentation, and git controls. AI did not remove the need for scientific judgment; it increased the speed and breadth with which assumptions, code paths, data provenance, and documentation could be inspected.

This matters beyond hail. Many societally important hazards have public data, known scientific ingredients, and fragmented code examples, but lack transparent, maintained, end-to-end models. Human-directed AI agents can lower the fixed cost of assembling such models while making assumptions more visible. In this sense, AI may change not only scientific discovery but also the production of reusable scientific infrastructure.

---

## Limitations

The model is hazard-only and does not include exposure or claims-calibrated vulnerability. Tail estimates are point estimates and do not yet include bootstrap confidence intervals. The model assumes stationarity over the radar record. Source transitions among MYRORSS, GridRad, and MRMS remain a key uncertainty. The stochastic catalog currently uses a Poisson event-count model, which may underrepresent overdispersion in active severe-convective years.

The AI-process analysis is also limited. This is a case study rather than a randomized comparison of human-only and AI-assisted development. The exact contribution of each AI system is difficult to isolate because the workflow was interactive and iterative. The article therefore frames AI as an enabling workflow component, not as an independently validated replacement for expert model development.

---

## Materials and Methods

### Computational environment

The model is implemented as a staged Python repository. Each stage writes durable outputs to `data/`, diagnostics to `logs/` or `docs/figures/`, and documentation to `docs/`. Generated model outputs are excluded from git tracking.

### Pipeline stages

The full pipeline contains 15 stages:

```text
01 MYRORSS ingestion
02 MRMS ingestion
03 SPC reports
04a ERA5 isotherms
04b GridRad gap fill
05 bias correction and filtering
06 SPC validation
07 climatology
08 event catalog
09 regional CDF fitting
10 spatially pooled CDF
11 occurrence probabilities
12 CONUS mask and topographic correction
13 stochastic catalog
14 vulnerability placeholder
15 figures
```

### AI disclosure

Large language models were used in the development of the codebase, documentation, monitoring workflow, and manuscript draft. The systems used were Claude Opus v6 and ChatGPT 5.5 [verify exact public model names, model snapshots, access dates, and vendors before submission]. AI assistance included literature synthesis, code generation, code review, test repair, documentation editing, shell-command planning, git workflow support, and long-running pipeline monitoring. AI outputs were reviewed, edited, tested, and accepted under human direction. AI systems are not listed as authors and are not treated as accountable scientific contributors.

### Data and code availability

The code is maintained in a git repository and is intended for public release at:

```text
[Repository URL to be inserted]
```

Input datasets are public or publicly documented. Generated data products are reproducible from the pipeline but are not committed to the source repository because of size. The exact code release used for the manuscript will be archived at [repository DOI to be inserted], and large generated artifacts will be retained or regenerated according to [artifact-retention instructions to be inserted].

---

## Acknowledgments

[To be added: funding, institutional support, computational resources, and human contributors.]

---

## Competing Interests

[To be added.]

---

## References

Allen, J. T. and M. K. Tippett, 2015: The characteristics of United States hail reports: 1955-2014. *Electronic Journal of Severe Storms Meteorology*, 10(3), 1-31.

Allen, J. T., M. K. Tippett, and A. H. Sobel, 2015: An empirical model relating U.S. monthly hail occurrence to large-scale meteorological environment. *Journal of Advances in Modeling Earth Systems*, 7(1), 226-243.

Balkema, A. A. and L. de Haan, 1974: Residual life time at great age. *Annals of Probability*, 2(5), 792-804.

Boiko, D. A., R. MacKnight, B. Kline, and G. Gomes, 2023: Autonomous chemical research with large language models. *Nature*, 624, 570-578.

Blair, S. F., et al., 2011: A radar-based assessment of the detectability of giant hail. *Electronic Journal of Severe Storms Meteorology*, 6(7), 1-30.

Blair, S. F., et al., 2017: High-resolution hail observations: implications for NWS warning operations. *Weather and Forecasting*, 32, 1101-1119.

Coles, S., 2001: *An Introduction to Statistical Modeling of Extreme Values.* Springer.

Davison, A. C., S. A. Padoan, and M. Ribatet, 2012: Statistical modeling of spatial extremes. *Statistical Science*, 27(2), 161-186.

Grossi, P. and H. Kunreuther, 2005: *Catastrophe Modeling: A New Approach to Managing Risk.* Springer.

Hosking, J. R. M. and J. R. Wallis, 1997: *Regional Frequency Analysis: An Approach Based on L-Moments.* Cambridge University Press.

Lu, C., C. Lu, R. T. Lange, J. Foerster, J. Clune, and D. Ha, 2024: The AI Scientist: towards fully automated open-ended scientific discovery. *arXiv:2408.06292*.

Murillo, E. M. and C. R. Homeyer, 2019: Severe hail fall and hailstorm detection using remote sensing observations. *Journal of Applied Meteorology and Climatology*, 58, 947-970.

Murillo, E. M., C. R. Homeyer, and J. T. Allen, 2021: A 23-year severe hail climatology using GridRad MESH observations. *Monthly Weather Review*, 149, 945-958.

Proceedings of the National Academy of Sciences, 2026: Information for authors. National Academy of Sciences.

Scarrott, C. and A. MacDonald, 2012: A review of extreme value threshold estimation and uncertainty quantification. *REVSTAT*, 10(1), 33-60.

Smith, T. M., et al., 2016: Multi-Radar Multi-Sensor severe weather and aviation products: initial operating capabilities. *Bulletin of the American Meteorological Society*, 97, 1617-1630.

Swanson, K., W. Wu, N. L. Bulaong, J. E. Pak, and coauthors, 2025: The Virtual Lab of AI agents designs new SARS-CoV-2 nanobodies. *Nature*, 646, 716-723.

Wendt, N. A. and I. L. Jirak, 2021: An hourly climatology of operational MRMS MESH-diagnosed severe and significant hail with comparisons to Storm Data hail reports. *Weather and Forecasting*, 36, 645-659.

Williams, S. S., K. L. Ortega, T. M. Smith, and coauthors, 2022: Comprehensive radar data for the contiguous United States: Multi-Year Reanalysis of Remotely Sensed Storms. *Bulletin of the American Meteorological Society*, 103, E838-E854.

Witt, A., et al., 1998: An enhanced hail detection algorithm for the WSR-88D. *Weather and Forecasting*, 13, 286-303.
