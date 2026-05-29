# Documentation Index — CONUS Hail Catastrophe Model v2.1

This directory contains the complete documentation for the v2.1 hail hazard model.
Use the reading paths below to orient yourself quickly.

---

## Quick-Start Reading Paths

**New to the project (5 minutes):**
1. [`executive_summary.md`](executive_summary.md) — what the model does, what it produces, key caveats

**Non-technical stakeholder:**
2. [`explainer.md`](explainer.md) — plain-language explanation; no equations

**Scientist / reviewer:**
3. [`methodology.md`](methodology.md) — full scientific methodology with equations and citations
4. [`literature_review.md`](literature_review.md) — supporting literature across all model components
5. [`uncertainty.md`](uncertainty.md) — uncertainty budget: measurement, algorithmic, sampling, model, stochastic
6. [`sensitivity.md`](sensitivity.md) — hyperparameter sweep plan; run after first pipeline execution
7. [`benchmarks.md`](benchmarks.md) — published RP comparison framework; post-run validation targets
8. [`vulnerability_derivation.md`](vulnerability_derivation.md) — MDR curve sources, limitations, calibration path
9. [`pnas_article_ai_hail_model.md`](pnas_article_ai_hail_model.md) — draft PNAS-style article on AI-assisted model construction
10. [`pnas_publication_readiness.md`](pnas_publication_readiness.md) — novelty assessment, evidence gaps, and submission-readiness checklist

**Engineer / developer running the pipeline:**
1. [`RUN_NOTES.md`](RUN_NOTES.md) — live run status, restart commands, disk/workers notes
2. [`reproduce.md`](reproduce.md) — environment setup, data acquisition, run commands
3. [`technical_documentation.md`](technical_documentation.md) — stage-by-stage implementation details
4. [`data_dictionary.md`](data_dictionary.md) — output file schemas, units, and conventions
5. [`REVIEW_PRE_RUN.md`](REVIEW_PRE_RUN.md) — pre-execution audit artifact (start here before any run)
6. [`../scripts/diagnostics/summarize_mesh_daily_peaks.py`](../scripts/diagnostics/summarize_mesh_daily_peaks.py) — optional mesh-era peak CSV/ECDF (`data/analysis/mesh_daily_peaks/`)

**AI agent or future developer:**
1. [`../AGENTS.md`](../AGENTS.md) — canonical AI-agent and developer orientation
2. [`ai_instructions.md`](ai_instructions.md) — non-negotiable constraints, high-risk stages, test categories
3. [`project_memory.md`](project_memory.md) — canonical project state, design decisions, known issues
4. [`GIT_REMOTES.md`](GIT_REMOTES.md) — push/PR policy (`origin` only, not `upstream`)

**Version history and migration:**
1. [`migration_plan.md`](migration_plan.md) — v1→v2→v2.1→v3 roadmap
2. [`UPGRADE_NOTES.md`](UPGRADE_NOTES.md) — v2.0→v2.1 breaking changes and migration steps
3. [`PR_v1_to_v2.1.md`](PR_v1_to_v2.1.md) — upstream PR narrative for the v1.0→v2.0→v2.1 arc
4. [`../CHANGELOG.md`](../CHANGELOG.md) — versioned change history

---

## Document Summaries

| Document | Type | Summary |
|---|---|---|
| [`executive_summary.md`](executive_summary.md) | Overview | 5-minute model overview for decision-makers |
| [`explainer.md`](explainer.md) | Overview | Plain-language methodology with no equations |
| [`methodology.md`](methodology.md) | Scientific | Full methodology: MESH75, EVT, stochastic simulation, vulnerability — includes §0 notation glossary |
| [`literature_review.md`](literature_review.md) | Scientific | Annotated bibliography covering all model components |
| [`uncertainty.md`](uncertainty.md) | Scientific | Uncertainty budget across six categories; companion to methodology |
| [`sensitivity.md`](sensitivity.md) | Scientific | Hyperparameter sensitivity sweep plan: stages 08, 09, 10, 12, 13 |
| [`benchmarks.md`](benchmarks.md) | Scientific | Published RP comparison framework; post-run validation targets |
| [`vulnerability_derivation.md`](vulnerability_derivation.md) | Scientific | MDR curve derivation, placeholder limitations, calibration roadmap |
| [`pnas_article_ai_hail_model.md`](pnas_article_ai_hail_model.md) | Manuscript | Draft PNAS-style article on AI-assisted catastrophe model development |
| [`pnas_publication_readiness.md`](pnas_publication_readiness.md) | Manuscript | PNAS novelty assessment, reviewer risks, evidence plan, go/no-go criteria |
| [`technical_documentation.md`](technical_documentation.md) | Engineering | Per-stage implementation: inputs, outputs, algorithms, CLI |
| [`data_dictionary.md`](data_dictionary.md) | Engineering | All output files: paths, schemas, units, nodata conventions |
| [`reproduce.md`](reproduce.md) | Engineering | Step-by-step instructions to reproduce the model from scratch |
| [`RUN_NOTES.md`](RUN_NOTES.md) | Engineering | First-run context, current stage status, restart commands |
| [`REVIEW_PRE_RUN.md`](REVIEW_PRE_RUN.md) | Audit | Checklist completed before each full pipeline execution |
| [`AGENTS.md`](../AGENTS.md) | Governance | Canonical AI-agent and developer orientation |
| [`ai_instructions.md`](ai_instructions.md) | Governance | Operating constraints for AI-assisted development |
| [`project_memory.md`](project_memory.md) | Governance | Current project state: what's done, known issues, next priorities |
| [`migration_plan.md`](migration_plan.md) | Governance | Version roadmap and migration guidance |
| [`UPGRADE_NOTES.md`](UPGRADE_NOTES.md) | Governance | v2.0→v2.1 patch notes |
| [`PR_v1_to_v2.1.md`](PR_v1_to_v2.1.md) | Governance | Reviewer-facing PR narrative for the upstream merge |
| [`CHANGELOG.md`](../CHANGELOG.md) | Governance | Full version history |

---

## Figures

Diagnostic figures are saved to `docs/figures/` (gitignored; generated at run time):

```
docs/figures/
├── historical/       # MESH climatology, annual max maps, SPC validation
├── analysis/         # GPD fits, MRL plots, RP maps, occurrence rasters
│   └── sensitivity/  # Hyperparameter sensitivity plots (planned)
└── stochastic/       # Stochastic RP maps, analytical vs empirical comparison
```

---

## Conventions

- All raster outputs use **EPSG:4326** (geographic coordinates).
- Grid: **0.05°**, 520 rows × 1180 columns, LAT_MAX = 50.005°N, LON_MIN = 125.005°W.
- Hail size units: **millimetres (mm)** throughout (except occurrence threshold labels
  which retain the conventional inch notation, e.g. `p_occ_1p00in.tif`).
- Return periods: 10, 25, 50, 100, 200, 250, 500, 1000, 5000, 10000, 50000 years.
- NoData value: **−1.0** for float32 rasters, **−9999** for integer rasters.
- Stage 01 uses `data/historical/mesh_0.05deg/manifest_stage01_myrorss.csv`
  to distinguish missing MYRORSS source days from available-source no-hail days;
  all-zero GeoTIFFs alone are not sufficient for that distinction.
