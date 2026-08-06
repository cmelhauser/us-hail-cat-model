"""Focused tests for metrics-driven PNAS publication text."""

from __future__ import annotations

import json
import sys
import types
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

## Competing Interests

None.

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
    assert "## Acknowledgments" in text
    assert "## Competing Interests" in text
    assert "SPC reports remain validation-only" in text
    assert "random 80/20" not in text.lower()
    assert "--allow-spc-derived-adjustments" not in text
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


def test_load_metrics_and_extractors(tmp_path: Path, monkeypatch, metrics: dict):
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    draft = tmp_path / "draft.md"
    draft.write_text(
        "## Introduction\n\nIntro text.\n\n## Conceptual Framework\n\n"
        "Representative AI-assisted interventions are summarized in Table 1.\n\n"
        "| # | Issue | Evidence | Patch | Validation | Residual risk |\n"
        "|---|---|---|---|---|---|\n| 1 | x | y | z | a | b |\n\n"
        "## Materials and Methods\n\nMethods.\n\n## Acknowledgments\n\nThanks.\n"
    )
    monkeypatch.setattr(publication, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(publication, "DRAFT_PATH", draft)
    monkeypatch.setattr(publication, "OUT_PATH", tmp_path / "out.md")
    monkeypatch.setattr(publication, "FIG_DIR", tmp_path / "figs")

    loaded = publication.load_metrics()
    assert loaded["total_daily_rasters"] == 4
    assert publication.extract_section(draft.read_text(), "## Missing") == ""
    assert "Intro text" in publication.extract_section(draft.read_text(), "## Introduction", "## Conceptual")
    assert publication.extract_heading_section(draft.read_text(), "## Acknowledgments")
    table = publication.extract_ai_process_table(draft.read_text())
    assert "AI-Assisted Development Process" in table


def test_fmt_and_stochastic_branches(metrics: dict):
    assert publication._fmt(None) == "—"
    assert publication._fmt(True) == "True"
    assert publication._fmt(1234.5, decimals=1) == "1,234.5"
    assert publication._fmt("text") == "text"

    metrics["stochastic"]["status"] = "not_available"
    assert "pending" in publication._stochastic_results(metrics)
    metrics["stochastic"]["status"] = "partial"
    metrics["stochastic"]["available_return_period_maps"] = [100]
    assert "partial" in publication._stochastic_results(metrics)


def test_build_sections_with_sparse_metrics(draft: str):
    sparse = {"generated": "2026-01-01", "stochastic": {"complete": False, "status": "pending"}}
    assert "pending" in publication.build_abstract(sparse)
    assert "pending" in publication.build_results(sparse)
    assert "pending" in publication.build_discussion(sparse)
    assert "unavailable" in publication.build_limitations(sparse)


def test_fig_block_available(tmp_path: Path, monkeypatch):
    fig_dir = tmp_path / "figs"
    fig_dir.mkdir()
    (fig_dir / "fig01.png").write_bytes(b"x")
    monkeypatch.setattr(publication, "FIG_DIR", fig_dir)
    block = publication.fig_block("fig01.png", "Figure 1", "Caption")
    assert "![Figure 1]" in block


def test_main_writes_publication(tmp_path: Path, monkeypatch, metrics: dict, draft: str):
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    draft_path = tmp_path / "draft.md"
    draft_path.write_text(draft)
    out_path = tmp_path / "pub.md"
    monkeypatch.setattr(publication, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(publication, "DRAFT_PATH", draft_path)
    monkeypatch.setattr(publication, "OUT_PATH", out_path)
    monkeypatch.setattr(publication, "FIG_DIR", tmp_path / "figs")
    publication.main()
    assert out_path.exists()


def test_extract_helpers_edge_cases():
    draft = "## Introduction\n\nText only.\n"
    assert publication.extract_section(draft, "## Missing", "## Also") == ""
    assert publication.extract_heading_section(draft, "## Missing") == ""
    assert publication.extract_ai_process_table("no table here") == ""

    broken = "Representative AI-assisted interventions are summarized in Table 1.\n\n| x |\n"
    assert publication.extract_ai_process_table(broken) == ""


def test_load_metrics_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(publication, "METRICS_PATH", tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        publication.load_metrics()


def test_main_invokes_review_docx(tmp_path: Path, monkeypatch, metrics: dict, draft: str):
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    draft_path = tmp_path / "draft.md"
    draft_path.write_text(draft)
    out_path = tmp_path / "pub.md"
    monkeypatch.setattr(publication, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(publication, "DRAFT_PATH", draft_path)
    monkeypatch.setattr(publication, "OUT_PATH", out_path)
    monkeypatch.setattr(publication, "FIG_DIR", tmp_path / "figs")

    called = {"n": 0}

    def fake_review():
        called["n"] += 1

    fake_mod = types.ModuleType("scripts.diagnostics.render_pnas_review_docx")
    fake_mod.main = fake_review
    monkeypatch.setitem(sys.modules, "scripts.diagnostics.render_pnas_review_docx", fake_mod)
    publication.main()
    assert called["n"] == 1
