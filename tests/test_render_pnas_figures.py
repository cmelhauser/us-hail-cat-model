"""Tests for PNAS figure renderer skip behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.diagnostics.render_pnas_article_figures import (
    MANIFESTS,
    collect_metrics,
    fig_manifest_coverage,
    fig_source_transition_peaks,
    run_figure,
)


def test_run_figure_skips_on_missing_file(tmp_path: Path, capsys):
    def boom(_out):
        raise FileNotFoundError("no peaks")

    result = run_figure("fig_test", boom, tmp_path / "x.png", default={})
    assert result == {}
    assert "WARNING: SKIP fig_test" in capsys.readouterr().out


def test_fig_manifest_coverage_warns_when_empty(tmp_path: Path, capsys):
    missing = {k: tmp_path / f"{k}.csv" for k in MANIFESTS}
    pivot = fig_manifest_coverage(missing, tmp_path / "fig02.png")
    assert pivot.empty
    assert "WARNING: SKIP fig02_manifest_coverage" in capsys.readouterr().out


def test_fig_source_transition_skips_without_peaks(tmp_path: Path, monkeypatch, capsys):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    monkeypatch.setattr(rpf, "PEAKS_CSV", tmp_path / "missing.csv")
    stats = fig_source_transition_peaks(tmp_path / "fig03.png")
    assert stats == {}
    assert "WARNING: SKIP fig03_source_transition" in capsys.readouterr().out


def test_collect_metrics_partial_inputs(tmp_path: Path, monkeypatch, capsys):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    manifest = tmp_path / "myrorss.csv"
    pd.DataFrame(
        {"date": ["2010-06-01"], "status": ["ok"]}
    ).to_csv(manifest, index=False)
    monkeypatch.setitem(rpf.MANIFESTS, "MYRORSS", manifest)
    monkeypatch.setattr(rpf, "HAIL_CLIM_DIR", tmp_path / "clim")
    metrics = collect_metrics(pd.DataFrame(), {"extra_key": 1})
    assert metrics["model_version"]
    assert metrics["extra_key"] == 1
    assert metrics["myrorss_days"] == 1
    out = capsys.readouterr().out
    assert "WARNING: SKIP metrics_hail_day_climatology" in out
