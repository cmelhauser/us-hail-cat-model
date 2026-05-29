# Migration Plan

**CONUS Hail Catastrophe Model**
**Path:** v1.0 -> v2.0 -> v2.1
**Current version:** v2.1.0

---

## 1. Purpose

This document explains how the project evolved from the initial SPC-report-based
prototype into the current radar-first v2.1 hail hazard model. It is intended
for reviewers, future maintainers, and pull-request reviewers who need to
understand why the codebase changed so substantially between versions.

The short version is:

- **v1.0** was a report-driven prototype. It used SPC hail reports as the
  primary hazard evidence and included population-trend adjustment.
- **v2.0** was the scientific redesign. It replaced report-based hazard
  estimation with radar-derived hail fields and introduced the modern 15-stage
  hazard pipeline.
- **v2.1** is the hardening release. It preserves the v2.0 scientific
  architecture while adding source provenance, deterministic fallbacks,
  stronger diagnostics, sparse-safe simulation, tests, documentation, CI, and
  pre-run controls.

v2.1 is therefore not a new model generation in the sense of v3.0. It is the
operationally defensible version of the v2.0 radar-first architecture.

---

## 2. Version Timeline

| Version | Role | Primary hazard evidence | Status |
|---|---|---|---|
| v1.0 | Prototype | SPC / Storm Data hail reports | Archived in `scripts/archive/v1/` |
| v2.0 | Redesign | Radar-derived MESH / MESH75 | Replaced v1.0 methodology |
| v2.1 | Hardening | Radar-derived MESH75 with provenance and QA | Current working model |

---

## 3. v1.0: SPC-Report-Based Prototype

v1.0 treated human hail reports as the main evidence for hail hazard. The
pipeline estimated spatial hail behavior from report data and attempted to
adjust for population-driven reporting effects.

### 3.1 v1.0 strengths

- Simple input data model.
- Direct connection to human-observed hail.
- Useful for early prototyping and pipeline scaffolding.
- Provided an initial stochastic-catastrophe-model structure.

### 3.2 v1.0 limitations

The core limitation was observational bias. SPC reports are scientifically
valuable, but they are not an unbiased gridded hail observing system.

Known limitations include:

- population-density bias;
- road-network and access bias;
- spotter-network and communication bias;
- diurnal reporting bias;
- report-size rounding;
- threshold and reporting-practice changes through time;
- sparse rural observations;
- poor support for gridded rare-event tail estimation;
- difficulty distinguishing "no hail" from "no one observed hail."

### 3.3 v1.0 disposition

The v1.0 scripts are retained for provenance in:

```text
scripts/archive/v1/
```

They should not be used for current hazard estimation. SPC reports remain in
the v2.x model, but only for validation, calibration review, and qualitative
sanity checks.

---

## 4. v1.0 -> v2.0: Scientific Redesign

v2.0 changed the model's scientific foundation. The primary hazard field moved
from human reports to radar-derived hail estimates. This was a methodological
change, not a small refactor.

### 4.1 Core design change

| Question | v1.0 answer | v2.0 answer |
|---|---|---|
| Primary hazard input | SPC reports | Radar-derived MESH / MESH75 |
| Role of SPC reports | Hazard truth | Validation and calibration support |
| Spatial coverage | Report locations and interpolation | CONUS gridded radar field |
| Rural hail representation | Weak and report-limited | Radar-observed where data exist |
| Main bias problem | Human reporting bias | Radar retrieval and source-transition uncertainty |
| Tail support | Sparse report extrema | Gridded annual maxima and regional pooling |

### 4.2 v2.0 data-source architecture

v2.0 introduced a three-era radar strategy:

| Era | Source | Purpose |
|---|---|---|
| 1998-2011 | MYRORSS | Early historical radar reanalysis |
| 2012-2020-10-13 | GridRad / GridRad-Severe (Stage 04c) | Gap fill between MYRORSS and operational MRMS |
| 2020-10-14–present | MRMS | Operational radar era |
| 2020-present | MRMS | Recent operational radar era |

ERA5 monthly isotherm heights support GridRad Severe Hail Index computation.
SPC reports are downloaded separately for validation.

### 4.3 v2.0 model architecture

v2.0 established the modern 15-stage pipeline:

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
11b public DEM preparation
12 CONUS mask and topographic correction
13 stochastic catalog
14 vulnerability placeholder
15 figures
```

### 4.4 v2.0 scientific additions

v2.0 added:

- fixed 0.05 degree CONUS grid;
- MESH75 hazard metric;
- block-maximum aggregation for hail-size fields;
- ERA5 0 C and -20 C isotherm support;
- GridRad SHI-to-MESH75 computation;
- lognormal body plus GPD tail;
- regional GPD shape-parameter pooling;
- analytical return-period maps;
- event-based stochastic catalog;
- analytical-vs-stochastic return-period comparison;
- literature-based placeholder vulnerability curves.

### 4.5 v2.0 removed behavior

v2.0 removed:

- SPC reports as the primary gridded hazard field;
- population-trend adjustment as a hazard correction;
- report-only tail fitting;
- generated data and figure artifacts from source control.

---

## 5. v2.0 -> v2.1: Hardening Release

v2.1 preserves the v2.0 radar-first methodology and focuses on making it more
defensible, testable, and safe to run.

### 5.1 What stays the same

- Radar-first hazard philosophy.
- 15-stage pipeline.
- Fixed 0.05 degree CONUS grid.
- MESH75 as the post-calibration hail-size metric.
- Lognormal body plus GPD tail framework.
- Regional tail pooling.
- Sparse historical event templates.
- Event-resampling stochastic catalog.
- SPC reports as validation rather than primary hazard truth.

### 5.2 What changes

| Area | v2.0 | v2.1 |
|---|---|---|
| MYRORSS ingestion | Assumed gzipped archive objects | Reads both `.netcdf` and `.netcdf.gz` |
| Source provenance | Output TIFFs only | Stage 01 manifest records missing, no-hail, read-error, and ok days |
| GridRad calibration | Global quantile mapping | Optional conditional calibration with deterministic fallback |
| Filtering | Hard thresholds | Optional probabilistic filter with deterministic safety floors |
| Event grouping | Overlap / gap / duration | Adds centroid displacement and intensity jump checks |
| Event metadata | Basic event fields | Adds merge-quality diagnostics |
| GPD thresholding | Static threshold plus manual review | Automated threshold diagnostics and stability outputs |
| Topography | Fixed coefficient | Freezing-level-aware bounded correction |
| Stochastic simulation | Possible dense reconstruction risk | Fully sparse-safe perturbation and annual maxima |
| Tests | Limited | Expanded stage-level and integration tests |
| CI | Minimal / evolving | Main-only GitHub Actions with unit and integration checks |
| Documentation | v2.0 methodology | Synchronized methodology, technical docs, uncertainty, sensitivity, benchmarks, and AI-operation docs |

### 5.3 Stage 01 manifest semantics

The most important v2.1 data-provenance addition is:

```text
data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv
```

This manifest distinguishes:

| Status | Meaning |
|---|---|
| `missing_source` | No MYRORSS objects were available for the day |
| `no_hail_pixels` | Source files existed, but no CONUS hail pixels were active |
| `ok` | Source files existed and produced a valid active-hail raster |
| `ok_with_read_errors` | Some source files failed but a usable active-hail raster was written |
| `no_hail_pixels_with_read_errors` | Some source files failed and no active cells were produced |
| `error` | The day failed and should not be treated as valid hazard evidence |

This matters because an all-zero GeoTIFF is scientifically ambiguous without
source provenance. It can mean either "quiet observed day" or "missing data."

### 5.4 Deterministic fallback requirement

v2.1 supports optional machine-learning calibration artifacts, but a valid
pipeline run cannot depend on them. The model must remain executable with:

```text
--skip-ml
```

This guarantees that reviewers can reproduce the baseline pipeline without
untracked binary artifacts.

### 5.5 Sparse-safety requirement

v2.1 treats sparse event storage as part of the model contract. Hail swaths are
localized, and dense event cubes would be wasteful and potentially unsafe at
catalog scale. Stage 13 therefore operates on sparse `rows`, `cols`, and `vals`
arrays and avoids dense `(n_events, 520, 1180)` reconstruction.

---

## 6. Documentation Added or Expanded in v2.1

The v2.1 branch expands documentation from a runnable pipeline into a reviewable
scientific artifact.

| Document | Purpose |
|---|---|
| `README.md` | Project overview and execution shape |
| `CHANGELOG.md` | Versioned history from v1.0 through v2.1 |
| `docs/migration_plan.md` | Version evolution and migration rationale |
| `docs/methodology.md` | Scientific methodology |
| `docs/technical_documentation.md` | Stage-by-stage implementation contract |
| `docs/literature_review.md` | Scientific basis and references |
| `docs/uncertainty.md` | Measurement, model, statistical, and operational uncertainty |
| `docs/sensitivity.md` | Post-run sensitivity sweep plan |
| `docs/benchmarks.md` | Published-comparison framework |
| `docs/reproduce.md` | Environment and run instructions |
| `docs/data_dictionary.md` | Output schemas and units |
| `docs/ai_instructions.md` | Operating constraints for AI-assisted development |
| `docs/project_memory.md` | Canonical project-state notes |
| `docs/pnas_article_ai_hail_model.md` | Draft article on AI-assisted model construction |
| `docs/pnas_publication_readiness.md` | Submission-readiness and novelty memo |
| `docs/UPGRADE_NOTES.md` | Practical v2.0-to-v2.1 upgrade notes |
| `docs/PR_v1_to_v2.1.md` | Pull-request narrative for upstream review |
| `docs/REVIEW_PRE_RUN.md` | Pre-run audit checklist |
| `docs/RUN_NOTES.md` | Recommended staged run shape |

---

## 7. Acceptance Criteria for v2.1

v2.1 is considered ready when:

1. all scripts compile;
2. unit tests pass;
3. integration smoke tests pass;
4. `run_pipeline.py --dry-run` works;
5. Stage 01 writes both daily TIFFs and a source manifest;
6. missing-source days are not conflated with source-present no-hail days;
7. Stage 05 runs with `--skip-ml`;
8. Stage 08 sparse event outputs validate;
9. Stage 09 emits threshold diagnostics;
10. Stage 13 runs sparse-safe;
11. generated data products and figures remain out of git;
12. README, methodology, technical docs, data dictionary, and migration docs
    describe actual behavior.

---

## 8. Reviewer Notes for the Upstream PR

The v1.0 -> v2.1 diff is intentionally large because the model changed from a
report-based prototype into a radar-first scientific hazard pipeline. Reviewers
should focus on:

- whether the migration rationale is clear;
- whether generated data and figures were removed from git;
- whether source provenance is sufficiently documented;
- whether `--skip-ml` provides a reproducible baseline path;
- whether the 15-stage pipeline is understandable from docs alone;
- whether CI and tests provide enough protection for future changes.

This PR should not be read as a request to bless final hazard results. Full-run
results, final validation metrics, and return-period figures remain pending
completion of the long pipeline run.

---

## 9. Future v3.0 Candidates

Potential v3.0 work includes:

- fully generative storm-swath modeling;
- max-stable or other formal spatial-extremes models;
- non-stationary climate-conditioned hazard;
- claims-calibrated vulnerability;
- exposure and financial-loss simulation;
- portfolio aggregation;
- formal uncertainty propagation into loss outputs.

---

## 10. Summary

v1.0 demonstrated the concept but relied too heavily on biased human reports.
v2.0 replaced that foundation with public radar-derived hazard data. v2.1 makes
the radar-first model more defensible, reproducible, testable, sparse-safe, and
ready for a full run.
