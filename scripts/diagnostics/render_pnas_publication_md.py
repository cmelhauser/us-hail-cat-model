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
import re
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


def fig_block(
    filename: str,
    label: str,
    caption: str,
    *,
    available: bool | None = None,
    pending_reason: str = "required generated figure is unavailable",
) -> str:
    path = FIG_DIR / filename
    if available is None:
        available = path.is_file()
    if not available or not path.is_file():
        return (
            f"\n> **{label} pending.** {caption}  \n"
            f"> Reason: {pending_reason}. Expected file: `{filename}`.\n"
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


def extract_heading_section(draft: str, heading: str) -> str:
    """Extract one level-two markdown section without substring ambiguity."""
    match = next(
        (
            candidate
            for candidate in re.finditer(
                rf"(?m)^{re.escape(heading)}\s*$",
                draft,
            )
        ),
        None,
    )
    if match is None:
        return ""
    next_heading = re.search(r"(?m)^##\s+", draft[match.end():])
    end = match.end() + next_heading.start() if next_heading else len(draft)
    section_lines = draft[match.start():end].strip().splitlines()
    while section_lines and (
        not section_lines[-1].strip() or section_lines[-1].strip() == "---"
    ):
        section_lines.pop()
    return "\n".join(section_lines)


def extract_ai_process_table(draft: str) -> str:
    """Extract Table 1 only when its markdown structure is intact."""
    marker = "Representative AI-assisted interventions are summarized in Table 1."
    start = draft.find(marker)
    if start < 0:
        return ""
    region = draft[start:]
    next_heading = re.search(r"(?m)^#{2,6}\s+", region[len(marker):])
    if next_heading:
        region = region[: len(marker) + next_heading.start()]
    lines = region.splitlines()
    try:
        table_start = next(i for i, line in enumerate(lines) if line.startswith("| # |"))
    except StopIteration:
        return ""
    table_lines = []
    for line in lines[table_start:]:
        if not line.startswith("|"):
            break
        table_lines.append(line)
    if len(table_lines) < 3 or "Residual risk" not in table_lines[0]:
        return ""

    safe_lines = []
    for line in table_lines:
        if line.startswith("| 9 |"):
            safe_lines.append(
                "| 9 | Radar geometry artifacts in prior RP maps | Visible NEXRAD "
                "rings/spokes triggered post-run QA | Five core artifact-filter passes "
                "+ site remediation + optional research classifier | Post-v2.3 radar "
                "QA metrics pending publication freeze | Reassess analytical/stochastic "
                "maps after complete Stage 13 outputs |"
            )
        else:
            safe_lines.append(line)
    return (
        "## AI-Assisted Development Process\n\n"
        f"{marker}\n\n"
        + "\n".join(safe_lines)
    )


def _fmt(value, decimals: int | None = None) -> str:
    if value is None or value == "—":
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if decimals is not None:
            return f"{value:,.{decimals}f}"
        return f"{value:,}"
    return str(value)


def _stochastic_complete(m: dict) -> bool:
    return bool(m.get("stochastic", {}).get("complete", False))


def _stochastic_results(m: dict) -> str:
    stochastic = m.get("stochastic", {})
    status = stochastic.get("status", "not_available")
    years = _fmt(stochastic.get("configured_years", 50_000))
    peaks = stochastic.get("peak_metrics", {})
    available_maps = stochastic.get("available_return_period_maps", [])
    peak_100 = peaks.get("rp_100yr_map_max_mm")
    oep_100 = peaks.get("oep_100yr_peak_mm")
    available_text = (
        f" Available map return periods: {', '.join(_fmt(rp) for rp in available_maps)} years."
        if available_maps
        else ""
    )
    peak_text = ""
    if peak_100 is not None:
        peak_text += f" The stochastic 100-year map maximum is **{_fmt(peak_100)} mm**."
    if oep_100 is not None:
        peak_text += f" The 100-year occurrence-exceedance peak is **{_fmt(oep_100)} mm**."

    if status == "complete":
        return (
            f"Stage **13** publication outputs are **complete** for the configured "
            f"**{years}-year** sparse simulation: all required return-period maps and "
            f"both exceedance tables are available.{peak_text}"
        )
    if status == "partial":
        return (
            "Stage **13** publication outputs are **partial**. The manuscript does not "
            "treat the stochastic catalog as complete until every required map and both "
            f"exceedance tables are present.{available_text}{peak_text}"
        )
    return (
        f"Stage **13** publication outputs are **pending** for the configured "
        f"**{years}-year** sparse simulation; no completed stochastic-catalog result "
        "is claimed."
    )


def build_results(m: dict) -> str:
    ev = m.get("event_catalog", {})
    validation = m.get("validation", {})
    val_excerpt = validation.get("validation_summary_excerpt", "")
    rp100 = m.get("return_period_maps", {}).get("rp_100yr", {})
    rp1000 = m.get("return_period_maps", {}).get("rp_1000yr", {})
    clim = m.get("hail_day_climatology_29mm", {})
    ms = m.get("manifest_status", {})
    disclosure = validation.get("holdout_tuning_disclosure")

    event_text = (
        f"Stage **08** identified **{_fmt(ev.get('n_events'))}** sparse historical "
        f"events at **29 mm** (**{_fmt(ev.get('mean_events_per_year'))}** yr⁻¹; "
        f"σ = {_fmt(ev.get('std_events_per_year'))}). The observed index of dispersion "
        f"is **{_fmt(ev.get('index_of_dispersion'))}**."
        if ev.get("n_events") is not None
        else "Stage **08** event metrics are pending in this metrics freeze."
    )
    climatology_text = (
        f"At **29 mm**, Great Plains per-cell maxima reach "
        f"**{_fmt(clim.get('gp_max_days_per_year'))}** hail days yr⁻¹ (mean "
        f"**{_fmt(clim.get('gp_mean_days_per_year'))}** yr⁻¹ across active cells). "
        f"National any-cell totals average "
        f"**{_fmt(clim.get('national_any_cell_days_per_year'))}** days yr⁻¹ "
        "(Figs. 5–6)."
        if clim
        else "The 29 mm hail-day climatology metrics are pending."
    )
    validation_text = (
        f"Stage **06** produced **{_fmt(validation.get('n_pairs'))}** report–MESH "
        "pairs on the rebuilt corrected archive."
        if validation.get("n_pairs") is not None
        else "The Stage **06** report–MESH pair count is unavailable in this metrics freeze."
    )
    if disclosure:
        validation_text += f" **Holdout/tuning disclosure:** {disclosure}"
    rp_text = (
        f"Smoothed analytical maps (Stages **09–10–12**) yield CONUS maxima of "
        f"**{_fmt(rp100.get('max_mm'))} mm** at 100 years and "
        f"**{_fmt(rp1000.get('max_mm'))} mm** at 1,000 years "
        f"({_fmt(rp100.get('cells_ge_25mm'))} CONUS cells ≥ 25.4 mm on the "
        "100-year map; Figs. 8–9)."
        if rp100 and rp1000
        else "Analytical return-period metrics are pending in this metrics freeze."
    )

    return f"""## Results

### Data coverage and hazard pipeline (model {MODEL_VERSION})

The corrected convective-day archive contains **{_fmt(m.get('total_daily_rasters'))}** daily MESH rasters: **{_fmt(m.get('myrorss_days'))}** MYRORSS days (manifest: {_fmt(ms.get('myrorss', {}).get('ok'))} ok / {_fmt(ms.get('myrorss', {}).get('missing_source'))} `missing_source`), **{_fmt(m.get('gridrad_days'))}** GridRad gap-fill days ({_fmt(ms.get('gridrad', {}).get('ok'))} ok / {_fmt(ms.get('gridrad', {}).get('missing_source'))} `missing_source`), and **{_fmt(m.get('mrms_days'))}** MRMS days.

### Event catalog and dispersion

{event_text}

### Hail-day climatology

{climatology_text}

### Validation against SPC reports

{validation_text}

```text
{val_excerpt.strip()}
```

### Analytical return periods

{rp_text}

### Stochastic catalog

{_stochastic_results(m)}
"""


def build_abstract(m: dict) -> str:
    ev = m.get("event_catalog", {})
    stochastic_clause = (
        "A completed 50,000-year sparse stochastic catalog provides empirical "
        "return-period maps and exceedance tables."
        if _stochastic_complete(m)
        else "The configured 50,000-year sparse stochastic catalog remains pending "
        "complete publication outputs and is not reported as a completed result."
    )
    return f"""## Abstract

Artificial intelligence is beginning to alter not only how scientific results are analyzed, but how scientific infrastructure is built. We present a case study in AI-assisted catastrophe model development: a US hail hazard model constructed as a fully automated, reproducible pipeline using frontier language-model agents under human direction. The model ingests public radar and environmental datasets—MYRORSS, GridRad or GridRad-Severe, operational MRMS, ERA5 isotherm fields, and SPC hail reports for validation—and builds a 0.05° CONUS archive of **{_fmt(m.get('total_daily_rasters'))}** convective days. Era-pooled calibration, five core radar artifact-filter passes, site remediation, optional research-only range-dependent debias, and an optional research hail-likelihood classifier produce corrected MESH75; **{_fmt(ev.get('n_events'))}** sparse historical events are identified at a **29 mm** skill threshold (**{_fmt(ev.get('mean_events_per_year'))}** yr⁻¹). Regional extreme-value models and spatial pooling yield analytical return-period maps. {stochastic_clause} We document both the scientific model and the development process under human scientific responsibility.
"""


def build_discussion(m: dict) -> str:
    validation = m.get("validation", {})
    event = m.get("event_catalog", {})
    state = (
        "The complete stochastic publication outputs permit analytical-versus-"
        "stochastic comparison as a model-risk diagnostic."
        if _stochastic_complete(m)
        else "Analytical-versus-stochastic conclusions remain pending; partial or "
        "missing Stage 13 outputs are not interpreted as a completed catalog."
    )
    measured = []
    if validation.get("n_pairs") is not None:
        measured.append(f"{_fmt(validation['n_pairs'])} SPC report–MESH pairs")
    if event.get("n_events") is not None:
        measured.append(f"{_fmt(event['n_events'])} historical sparse events")
    evidence = (
        "This metrics freeze contains " + " and ".join(measured) + "."
        if measured
        else "Validation and event counts remain pending in this metrics freeze."
    )
    return f"""## Discussion

This work contributes a public-data hail hazard model and a case study in AI-assisted scientific software development. The radar-first pipeline combines source provenance, era calibration, five core artifact-filter passes, site remediation, and optional research-only SPC-derived adjustments (range debias + hail-likelihood classifier) with sparse event storage and regional extreme-value analysis.

Separating radar hazard from report validation remains the central scientific design choice: MESH provides a physically motivated spatial field, while SPC reports test consistency with independent human observations. Sparse event storage is the central computational choice—localized footprints are resampled without dense `(n_events, n_rows, n_cols)` arrays.

{evidence} These generated values replace prior-run manuscript constants. {state}

AI assistance (**theonlymuffinbot**) operated inside explicit tests, stage boundaries, manifests, and human review. Scientific direction and accountability remain with Christopher Melhauser.
"""


def build_limitations(m: dict) -> str:
    event = m.get("event_catalog", {})
    iod = event.get("index_of_dispersion")
    dispersion = (
        f"The historical event-catalog index of dispersion is **{_fmt(iod)}**; "
        if iod is not None
        else "The historical event-catalog dispersion metric is unavailable; "
    )
    stochastic = (
        "the completed stochastic catalog uses a Poisson event-count model, which "
        "may underrepresent clustering in active severe-convective years."
        if _stochastic_complete(m)
        else "the configured stochastic catalog uses a Poisson event-count model, "
        "but catalog-level conclusions remain pending complete outputs."
    )
    return f"""## Limitations

The model is hazard-only and does not include exposure, vulnerability curves, or financial loss. Tail estimates are point estimates and do not yet include bootstrap confidence intervals. The model assumes stationarity over the radar record, and source transitions among MYRORSS, GridRad, and MRMS remain key uncertainties. {dispersion}{stochastic}

SPC reports are spatially and socially biased, and the optional research artifact classifier uses SPC-collocated weak labels. Its random train/test split is not an independent scientific holdout and must be disclosed when classifier results are reported.

The AI-process analysis is a case study rather than a randomized comparison of human-only and AI-assisted development. All AI-generated outputs require human review and remain under human scientific responsibility.
"""


def build_publication(metrics: dict, draft: str) -> str:
    """Build manuscript text from one frozen metrics object and source draft."""
    intro = extract_section(draft, "## Introduction", "## Conceptual Framework")
    methods_tail = extract_section(draft, "## Materials and Methods", "## Acknowledgments")
    refs = extract_section(draft, "## References")
    front_matter = "\n\n---\n\n".join(
        section
        for section in (
            extract_heading_section(draft, "## Author Line"),
            extract_heading_section(draft, "## Classification"),
            extract_heading_section(draft, "## Keywords"),
        )
        if section
    )
    ai_process_table = extract_ai_process_table(draft)
    stochastic_complete = _stochastic_complete(metrics)

    fig_section = "## Figures\n"
    for fname, label, cap in FIGURES:
        is_stochastic = fname in {
            "fig12_rp_100yr_stochastic.png",
            "fig13_analytical_vs_stochastic.png",
        }
        available = None if not is_stochastic else stochastic_complete
        pending_reason = (
            "Stage 13 publication outputs are incomplete"
            if is_stochastic
            else "required generated figure is unavailable"
        )
        fig_section += fig_block(
            fname,
            label,
            cap,
            available=available,
            pending_reason=pending_reason,
        )

    stochastic_method = (
        "and completed 50,000-year sparse stochastic resampling"
        if stochastic_complete
        else "with 50,000-year sparse stochastic resampling configured but publication outputs pending"
    )

    body = f"""# {MANUSCRIPT_TITLE}

**Publication manuscript (PNAS-style)**  
**Model version:** {MODEL_VERSION}  
**Metrics freeze:** {metrics.get('generated', date.today().isoformat())}  
**Code:** [github.com/cmelhauser/us-hail-cat-model](https://github.com/cmelhauser/us-hail-cat-model)  
**Corresponding author:** Christopher Melhauser (christopher.melhauser@gmail.com)

---

{front_matter}

---

## Significance Statement

Catastrophe models are usually built by specialized teams over long development cycles. This study describes a reproducible, radar-first US hail catastrophe hazard model built from public data through a human-directed AI workflow, with explicit source provenance, validation against SPC reports, and a documented AI-assisted development audit trail.

---

{build_abstract(metrics)}

---

{intro}

---

{ai_process_table}

---

## Hail Hazard Model

*(Summary; full methodological detail in `docs/pnas_article_ai_hail_model.md` and `docs/methodology.md`.)*

The model uses a fixed **0.05°** CONUS grid (520 × 1180), convective-day MESH rasters (12 UTC → 12 UTC), era-pooled quantile mapping to a GridRad anchor, five core radar artifact-filter passes plus site remediation, optional research-only SPC-derived range debias and hail-likelihood classifier (`--allow-spc-derived-adjustments`), sparse historical events at **29 mm**, regional GPD tails with L-moment pooling, **150 km** spatial CDF smoothing, CONUS masking with freezing-level-aware topographic correction, {stochastic_method}.

---

{build_results(metrics)}

---

{fig_section}

---

{build_discussion(metrics)}

---

{build_limitations(metrics)}

---

{methods_tail}

---

{refs}
"""
    return body


def main() -> None:
    metrics = load_metrics()
    draft = DRAFT_PATH.read_text() if DRAFT_PATH.is_file() else ""
    body = build_publication(metrics, draft)

    OUT_PATH.write_text(body)
    stochastic_complete = _stochastic_complete(metrics)
    stochastic_figures = {
        "fig12_rp_100yr_stochastic.png",
        "fig13_analytical_vs_stochastic.png",
    }
    n_figs = sum(
        1
        for filename, _, _ in FIGURES
        if (FIG_DIR / filename).is_file()
        and (filename not in stochastic_figures or stochastic_complete)
    )
    print(f"Wrote {OUT_PATH} ({n_figs}/{len(FIGURES)} figures embedded)")

    try:
        from scripts.diagnostics.render_pnas_review_docx import main as render_review_docx

        render_review_docx()
    except Exception as exc:
        print(f"Review DOCX skipped: {exc}")


if __name__ == "__main__":
    main()
