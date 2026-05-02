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

**Engineer / developer running the pipeline:**
6. [`reproduce.md`](reproduce.md) — environment setup, data acquisition, run commands
7. [`technical_documentation.md`](technical_documentation.md) — stage-by-stage implementation details
8. [`data_dictionary.md`](data_dictionary.md) — output file schemas, units, and conventions
9. [`REVIEW_PRE_RUN.md`](../REVIEW_PRE_RUN.md) — pre-execution audit artifact (start here before any run)

**AI agent or future developer:**
10. [`ai_instructions.md`](ai_instructions.md) — non-negotiable constraints, high-risk stages, test categories
11. [`project_memory.md`](project_memory.md) — canonical project state, design decisions, known issues

**Version history and migration:**
12. [`migration_plan.md`](migration_plan.md) — v1→v2→v2.1→v3 roadmap
13. [`UPGRADE_NOTES.md`](../UPGRADE_NOTES.md) — v2.0→v2.1 breaking changes and migration steps
14. [`../CHANGELOG.md`](../CHANGELOG.md) — versioned change history

---

## Document Summaries

| Document | Type | Summary |
|---|---|---|
| [`executive_summary.md`](executive_summary.md) | Overview | 5-minute model overview for decision-makers |
| [`explainer.md`](explainer.md) | Overview | Plain-language methodology with no equations |
| [`methodology.md`](methodology.md) | Scientific | Full methodology: MESH75, EVT, stochastic simulation, vulnerability |
| [`literature_review.md`](literature_review.md) | Scientific | Annotated bibliography covering all model components |
| [`uncertainty.md`](uncertainty.md) | Scientific | Uncertainty budget across six categories; companion to methodology |
| [`technical_documentation.md`](technical_documentation.md) | Engineering | Per-stage implementation: inputs, outputs, algorithms, CLI |
| [`data_dictionary.md`](data_dictionary.md) | Engineering | All output files: paths, schemas, units, nodata conventions |
| [`reproduce.md`](reproduce.md) | Engineering | Step-by-step instructions to reproduce the model from scratch |
| [`REVIEW_PRE_RUN.md`](../REVIEW_PRE_RUN.md) | Audit | Checklist completed before each full pipeline execution |
| [`ai_instructions.md`](ai_instructions.md) | Governance | Operating constraints for AI-assisted development |
| [`project_memory.md`](project_memory.md) | Governance | Current project state: what's done, known issues, next priorities |
| [`migration_plan.md`](migration_plan.md) | Governance | Version roadmap and migration guidance |
| [`UPGRADE_NOTES.md`](../UPGRADE_NOTES.md) | Governance | v2.0→v2.1 patch notes |
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
