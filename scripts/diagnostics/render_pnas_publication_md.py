#!/usr/bin/env python3
"""
Build a publication-ready PNAS manuscript markdown with embedded figures.

Reads frozen metrics from ``data/analysis/pnas_article_metrics.json`` and
embeds PNGs from ``docs/figures/pnas/``. Stochastic figures (12–13) are
included when Stage 13/14 outputs exist.

Usage (repo root):
  .venv/bin/python scripts/diagnostics/render_pnas_publication_md.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts._config import MODEL_VERSION

MANUSCRIPT_TITLE = (
    "Scientific Infrastructure at Agent Speed: An Open Source US Hail Hazard Model"
)

METRICS_PATH = REPO / "data" / "analysis" / "pnas_article_metrics.json"
FIG_DIR = REPO / "docs" / "figures" / "pnas"
OUT_PATH = REPO / "docs" / "pnas_article_publication.md"
DRAFT_PATH = REPO / "docs" / "pnas_article_ai_hail_model.md"

FIGURES = [
    ("fig01_data_source_timeline.png", "Figure 1", "Radar data sources and splice dates for the convective-day MESH archive (12 UTC → 12 UTC labels)."),
    ("fig02_manifest_coverage_by_year.png", "Figure 2", "Source-coverage manifest status by year (MYRORSS, GridRad gap-fill, MRMS)."),
    ("fig03_source_transition_daily_peaks.png", "Figure 3", "Daily CONUS peak MESH distributions at source-transition windows."),
    ("fig04_calibration_ecdf_by_source.png", "Figure 4", "Era-pooled calibration: raw vs corrected daily peak ECDFs by radar era."),
    ("fig05_seasonal_national_hail_days.png", "Figure 5", "National seasonal cycle of any-cell hail days by MESH75 threshold."),
    ("fig06_hail_days_per_year_29mm.png", "Figure 6", "Mean annual hail days per 0.05° cell at the 29 mm skill threshold (Lambert Conformal)."),
    ("fig07_validation_by_size_bin.png", "Figure 7", "MESH75 vs SPC validation: bias and probability of detection by report-size bin."),
    ("fig07b_mesh_vs_spc_scatter.png", "Figure 7 (supplement)", "Collocated SPC report size vs MESH75."),
    ("fig08_rp_100yr_analytical.png", "Figure 8", "Analytical 100-year return-period hail map (smoothed; Lambert Conformal)."),
    ("fig09_rp_1000yr_analytical.png", "Figure 9", "Analytical 1,000-year return-period hail map (smoothed; Lambert Conformal)."),
    ("fig10_annual_event_counts.png", "Figure 10", "Annual sparse historical event counts at 29 mm (Stage 08)."),
    ("fig11_ai_development_workflow.png", "Figure 11", "Human-directed AI-assisted development loop."),
    ("fig12_rp_100yr_stochastic.png", "Figure 12", "Stochastic 100-year empirical return-period map (50,000-yr catalog; Lambert Conformal)."),
    ("fig13_analytical_vs_stochastic.png", "Figure 13", "Analytical vs stochastic 100-year return-period comparison (Lambert Conformal)."),
]


def load_metrics() -> dict:
    if not METRICS_PATH.is_file():
        raise FileNotFoundError(f"Missing metrics: {METRICS_PATH}")
    return json.loads(METRICS_PATH.read_text())


def fig_block(filename: str, label: str, caption: str) -> str:
    path = FIG_DIR / filename
    if not path.is_file():
        return (
            f"\n<!-- {label}: {filename} pending — regenerate after Stage 13/14 -->\n\n"
            f"**{label}** — *{caption}* *(figure pending)*\n"
        )
    rel = f"figures/pnas/{filename}"
    return (
        f"\n**{label}.** {caption}\n\n"
        f"![{label}]({rel})\n"
    )


def extract_section(draft: str, heading: str, until: str | None = None) -> str:
    start = draft.find(heading)
    if start < 0:
        return ""
    if until:
        end = draft.find(until, start + len(heading))
        if end < 0:
            end = len(draft)
    else:
        end = len(draft)
    return draft[start:end].strip()


def build_results(m: dict) -> str:
    ev = m.get("event_catalog", {})
    val_excerpt = m.get("validation", {}).get("validation_summary_excerpt", "")
    rp100 = m.get("return_period_maps", {}).get("rp_100yr", {})
    rp1000 = m.get("return_period_maps", {}).get("rp_1000yr", {})
    clim = m.get("hail_day_climatology_29mm", {})
    ms = m.get("manifest_status", {})

    return f"""## Results

### Data coverage and hazard pipeline (model {MODEL_VERSION})

The corrected convective-day archive contains **{m.get('total_daily_rasters', '—'):,}** daily MESH rasters (1998–2026): **{m.get('myrorss_days', '—'):,}** MYRORSS days (manifest: {ms.get('myrorss', {}).get('ok', '—')} ok / {ms.get('myrorss', {}).get('missing_source', '—')} missing_source), **{m.get('gridrad_days', '—'):,}** GridRad gap-fill days ({ms.get('gridrad', {}).get('ok', '—')} ok / {m.get('gridrad', {}).get('missing_source', '—')} missing_source), and **{m.get('mrms_days', '—'):,}** MRMS days. Stage **01** MYRORSS re-ingest with corrected WDSS-II sparse-grid axes completed **2026-07-08**, restoring eastern CONUS coverage truncated in earlier ingests.

### Event catalog and dispersion

Stage **08** identified **{ev.get('n_events', '—'):,}** sparse historical events at **29 mm** over 29 years (**{ev.get('mean_events_per_year', '—')}** yr⁻¹; σ = {ev.get('std_events_per_year', '—')}). The index of dispersion (variance/mean) is **{ev.get('index_of_dispersion', '—')}**, indicating strong year-to-year clustering relative to a Poisson process.

### Hail-day climatology

At **29 mm**, Great Plains per-cell maxima reach **{clim.get('gp_max_days_per_year', '—')}** hail days yr⁻¹ (mean **{clim.get('gp_mean_days_per_year', '—')}** yr⁻¹ across active cells). National any-cell totals average **{clim.get('national_any_cell_days_per_year', '—')}** days yr⁻¹ (Fig. 5–6).

### Validation against SPC reports

Stage **06** produced **173,766** report–MESH pairs on the rebuilt corrected archive. Summary excerpt:

```text
{val_excerpt.strip()}
```

### Analytical return periods

Smoothed analytical maps (Stages **09–10–12**) yield CONUS maxima of **{rp100.get('max_mm', '—')} mm** at 100 years and **{rp1000.get('max_mm', '—')} mm** at 1,000 years ({rp100.get('cells_ge_25mm', '—'):,} CONUS cells ≥ 25.4 mm on the 100-yr map). Eastern CONUS hazard is restored relative to the pre-fix MYRORSS ingest (Figs. 8–9).

### Stochastic catalog

Stage **13** 50,000-year sparse resampling was **in progress** at manuscript build time; Figs. 12–13 and final stochastic peak tables are inserted when `data/stochastic/maps/` exists. Re-run:

```bash
.venv/bin/python scripts/diagnostics/render_pnas_article_figures.py
.venv/bin/python scripts/diagnostics/render_pnas_publication_md.py
```
"""


def build_abstract(m: dict) -> str:
    ev = m.get("event_catalog", {})
    return f"""## Abstract

Artificial intelligence is beginning to alter not only how scientific results are analyzed, but how scientific infrastructure is built. We present a case study in AI-assisted catastrophe model development: a US hail hazard model constructed as a fully automated, reproducible pipeline using frontier language-model agents under human direction. The model ingests public radar and environmental datasets—MYRORSS, GridRad or GridRad-Severe, operational MRMS, ERA5 isotherm fields, and SPC hail reports for validation—and builds a 0.05° CONUS archive of **{m.get('total_daily_rasters', 9797):,}** convective days (1998–2026). Era-pooled calibration, a five-pass GridRad artifact filter, and range-dependent debias produce corrected MESH75; **{ev.get('n_events', '—'):,}** sparse historical events are identified at a **29 mm** skill threshold (**{ev.get('mean_events_per_year', '—')}** yr⁻¹). Regional extreme-value models and spatial pooling yield analytical return-period maps; a **50,000-year** stochastic catalog extends the hazard layer. We document both the scientific model and the development process—literature synthesis, implementation, testing, data QA, documentation, and run monitoring—with `claude-sonnet-4-6`, `claude-opus-4-6` (Anthropic, May 2026), and `gpt-5.5-medium` (OpenAI, May 2026) under human scientific responsibility.
"""


def main() -> None:
    metrics = load_metrics()
    draft = DRAFT_PATH.read_text() if DRAFT_PATH.is_file() else ""

    intro = extract_section(draft, "## Introduction", "## Conceptual Framework")
    methods_tail = extract_section(draft, "## Materials and Methods", "## Acknowledgments")
    limitations = extract_section(draft, "## Limitations", "## Materials and Methods")
    refs = extract_section(draft, "## References")

    discussion = """## Discussion

This work contributes a public-data hail hazard model and a case study in AI-assisted scientific software development. The hail model demonstrates that a radar-first pipeline can be built from public datasets, calibrated across source eras, converted into sparse historical events, and extended into a stochastic catalog.

Separating radar hazard from report validation remains the central scientific design choice: MESH provides a physically motivated spatial field, while SPC reports test consistency with independent human observations. Sparse event storage is the central computational choice—localized footprints are resampled at catalog scale without dense `(n_events, n_rows, n_cols)` arrays.

The **2026-07-08** rebuild incorporated a MYRORSS coordinate-fix re-ingest (eastern CONUS restored), a five-pass GridRad artifact filter with spatiotemporal persistence, and refreshed range debias from **173,766** validation pairs. Event frequency fell from the prior smoke-affected eastern truncation (**8,798** → **7,792** events; **303** → **269** yr⁻¹), while analytical return-period peaks increased materially once eastern hail entered the EVT record—underscoring that ingest geometry and artifact QA are first-order hazard uncertainties, not secondary polish.

AI assistance (**theonlymuffinbot**) was most valuable inside a disciplined repository: explicit tests, stage boundaries, manifests, and git-reviewed changes. Agents accelerated audit breadth; the human operator retained methodological decisions and accountability.
"""

    fig_section = "## Figures\n"
    for fname, label, cap in FIGURES:
        fig_section += fig_block(fname, label, cap)

    body = f"""# {MANUSCRIPT_TITLE}

**Publication manuscript (PNAS-style)**  
**Model version:** {MODEL_VERSION}  
**Metrics freeze:** {metrics.get('generated', date.today().isoformat())}  
**Code:** [github.com/cmelhauser/us-hail-cat-model](https://github.com/cmelhauser/us-hail-cat-model)  
**Corresponding author:** Christopher Melhauser (christopher.melhauser@gmail.com)

---

## Significance Statement

Catastrophe models are usually built by specialized teams over long development cycles. This study describes a reproducible, radar-first US hail catastrophe hazard model built from public data through a human-directed AI workflow, with explicit source provenance, validation against SPC reports, and a documented AI-assisted development audit trail.

---

{build_abstract(metrics)}

---

{intro}

---

## Hail Hazard Model

*(Summary; full methodological detail in `docs/pnas_article_ai_hail_model.md` and `docs/methodology.md`.)*

The model uses a fixed **0.05°** CONUS grid (520 × 1180), convective-day MESH rasters (12 UTC → 12 UTC), era-pooled quantile mapping to a GridRad anchor, optional range debias, a five-pass GridRad artifact filter, sparse historical events at **29 mm**, regional GPD tails with L-moment pooling, **150 km** spatial CDF smoothing, CONUS masking with freezing-level-aware topographic correction, and **50,000-year** sparse stochastic resampling.

---

{build_results(metrics)}

---

{fig_section}

---

{discussion}

---

{limitations}

---

{methods_tail}

---

{refs}
"""

    OUT_PATH.write_text(body)
    n_figs = sum(1 for f, _, _ in FIGURES if (FIG_DIR / f).is_file())
    print(f"Wrote {OUT_PATH} ({n_figs}/{len(FIGURES)} figures embedded)")

    try:
        from scripts.diagnostics.render_pnas_review_docx import main as render_review_docx

        render_review_docx()
    except Exception as exc:
        print(f"Review DOCX skipped: {exc}")


if __name__ == "__main__":
    main()
