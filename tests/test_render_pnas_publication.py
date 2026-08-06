"""Focused tests for metrics-driven PNAS publication text."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.diagnostics.render_pnas_publication_md as publication


@pytest.fixture
def metrics() -> dict:
    return {
        "generated": "2026-08-05",
        "total_daily_rasters": 4,
        "myrorss_days": 1,
        "gridrad_days": 2,
        "mrms_days": 1,
        "manifest_status": {
            "myrorss": {"ok": 1, "missing_source": 0},
            "gridrad": {"ok": 1, "missing_source": 7},
            "mrms": {"ok": 1},
        },
        "event_catalog": {
            "n_events": 456,
            "mean_events_per_year": 15.7,
            "std_events_per_year": 4.2,
            "index_of_dispersion": 2.34,
        },
        "validation": {
            "n_pairs": 12_345,
            "validation_summary_excerpt": "Synthetic current-run summary",
            "holdout_tuning_disclosure_required": True,
            "holdout_tuning_disclosure": "Synthetic holdout disclosure.",
        },
        "hail_day_climatology_29mm": {
            "gp_max_days_per_year": 3.2,
            "gp_mean_days_per_year": 1.1,
            "national_any_cell_days_per_year": 200.0,
        },
        "return_period_maps": {
            "rp_100yr": {"max_mm": 80.0, "cells_ge_25mm": 100},
            "rp_1000yr": {"max_mm": 120.0},
        },
        "stochastic": {
            "complete": False,
            "status": "partial",
            "configured_years": 50_000,
            "available_return_period_maps": [100],
            "peak_metrics": {"rp_100yr_map_max_mm": 75.0},
        },
    }


@pytest.fixture
def draft() -> str:
    return """# Draft

## Author Line

**Test Author**

---

## Classification

Physical Sciences

---

## Keywords

hail; reproducibility

---

## Introduction

Current introduction.

## Conceptual Framework

Representative AI-assisted interventions are summarized in Table 1.

| # | Issue discovered (AI-assisted audit) | Evidence | Patch / artifact | Validation | Residual risk |
|---|---|---|---|---|---|
| 1 | Source gap | Manifest | Reader | Test | Monitor |
| 9 | Radar artifacts | stale speckle 9.7% | stale five-pass wording | stale 1.8% | Review |

## Materials and Methods

Methods describe configured stages without claiming run completion.

## Acknowledgments

Thanks.

## References

Reference.
"""


def test_partial_publication_has_pending_state_and_no_stale_claims(
    tmp_path: Path,
    monkeypatch,
    metrics: dict,
    draft: str,
):
    figure_dir = tmp_path / "figures"
    figure_dir.mkdir()
    (figure_dir / "fig12_rp_100yr_stochastic.png").touch()
    (figure_dir / "fig13_analytical_vs_stochastic.png").touch()
    monkeypatch.setattr(publication, "FIG_DIR", figure_dir)

    text = publication.build_publication(metrics, draft)

    assert "Stage **13** publication outputs are **partial**" in text
    assert "Figure 12 pending" in text
    assert "![Figure 12]" not in text
    assert "A completed 50,000-year sparse stochastic catalog" not in text
    assert "and completed 50,000-year sparse stochastic resampling" not in text
    assert "7 `missing_source`" in text
    assert "**12,345** report–MESH pairs" in text
    assert "**456** sparse historical events" in text
    assert "## Author Line" in text
    assert "## AI-Assisted Development Process" in text
    assert (
        "optional research-only spc-derived adjustments" in text.lower()
        or "optional research hail-likelihood classifier" in text.lower()
        or "five core artifact-filter passes + site remediation" in text.lower()
    )
    for stale in ("173,766", "8,798", "7,792", "303 yr", "269 yr", "11.7", "9.7%", "1.8%"):
        assert stale not in text


def test_complete_publication_claims_completion_without_pending_stochastic_text(
    tmp_path: Path,
    monkeypatch,
    metrics: dict,
    draft: str,
):
    figure_dir = tmp_path / "figures"
    figure_dir.mkdir()
    (figure_dir / "fig12_rp_100yr_stochastic.png").touch()
    (figure_dir / "fig13_analytical_vs_stochastic.png").touch()
    monkeypatch.setattr(publication, "FIG_DIR", figure_dir)
    metrics["stochastic"].update(
        {
            "complete": True,
            "status": "complete",
            "peak_metrics": {
                "rp_100yr_map_max_mm": 75.0,
                "oep_100yr_peak_mm": 82.0,
            },
        }
    )

    text = publication.build_publication(metrics, draft)

    assert "Stage **13** publication outputs are **complete**" in text
    assert "A completed 50,000-year sparse stochastic catalog" in text
    assert "![Figure 12]" in text
    assert "Figure 12 pending" not in text
    assert "stochastic conclusions remain pending" not in text


def test_missing_figure_renders_explicit_pending_block(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(publication, "FIG_DIR", tmp_path)

    block = publication.fig_block("missing.png", "Figure X", "Expected panel")

    assert "**Figure X pending.**" in block
    assert "Expected file: `missing.png`" in block
    assert "![" not in block


def test_renderer_source_contains_no_superseded_metric_constants():
    source = Path(publication.__file__).read_text()

    for stale in ("173,766", "8,798", "7,792", "303.4", "268.7", "11.7", "9.7%"):
        assert stale not in source
