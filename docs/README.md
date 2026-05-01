# Documentation

**CONUS Hail Catastrophe Model v2.0 — All 15 stages written**

| Document | Description |
|---|---|
| [`executive_summary.md`](executive_summary.md) | One-page overview, key results, limitations |
| [`methodology.md`](methodology.md) | Full methodology: data, pipeline, CDF fitting, stochastic catalog |
| [`technical_documentation.md`](technical_documentation.md) | Pipeline technical reference, parameters, schemas |
| [`data_dictionary.md`](data_dictionary.md) | Every output file: path, format, bands, units, nodata |
| [`literature_review.md`](literature_review.md) | Supporting literature for all methodology decisions |
| [`migration_plan.md`](migration_plan.md) | v1.0 → v2.0 transition details |
| [`reproduce.md`](reproduce.md) | Step-by-step reproduction guide |
| [`explainer.md`](explainer.md) | Non-technical explainer for stakeholders |

## Data Layout

All data lives under `data/` (gitignored), organized into three categories:

```
data/historical/    ← Raw radar, SPC reports, corrected MESH, climatology, events
data/analysis/      ← CDF parameters, calibration, occurrence, topography, vulnerability
data/stochastic/    ← 50,000-yr catalog, return period maps, EP tables
```

## Figures

```
docs/figures/historical/   ← Historical RP maps, climatology, event footprints
docs/figures/stochastic/   ← Stochastic RP maps, EP curves
docs/figures/analysis/     ← Validation, diagnostics, comparison charts
```
