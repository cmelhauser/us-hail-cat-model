"""Tests for PNAS figure renderer skip behavior."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from scripts.diagnostics.render_pnas_article_figures import (
    MANIFESTS,
    _stochastic_metrics,
    _validation_metrics,
    collect_metrics,
    fig_manifest_coverage,
    fig_source_transition_peaks,
    run_figure,
)


def _write_tif(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="float32",
        transform=from_origin(-125, 50, 0.05, 0.05),
    ) as dst:
        dst.write(values.astype(np.float32), 1)


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

    manifests = {
        "MYRORSS": pd.DataFrame(
            {"date": ["2010-06-01"], "status": ["ok"]}
        ),
        "GridRad": pd.DataFrame(
            {
                "date": ["2018-06-01", "2018-06-02"],
                "status": ["ok", "missing_source"],
            }
        ),
        "MRMS": pd.DataFrame(
            {"date": ["2022-06-01"], "status": ["ok"]}
        ),
    }
    for source, frame in manifests.items():
        path = tmp_path / f"{source}.csv"
        frame.to_csv(path, index=False)
        monkeypatch.setitem(rpf.MANIFESTS, source, path)
    monkeypatch.setattr(rpf, "HAIL_CLIM_DIR", tmp_path / "clim")
    monkeypatch.setattr(rpf, "VALID_DIR", tmp_path / "validation")
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", tmp_path / "stochastic" / "maps")
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", tmp_path / "stochastic" / "pet")
    monkeypatch.setattr(
        rpf,
        "STOCH_CATALOG",
        tmp_path / "stochastic" / "catalog" / "summary.parquet",
    )
    metrics = collect_metrics(pd.DataFrame(), {"extra_key": 1})
    assert metrics["model_version"]
    assert metrics["extra_key"] == 1
    assert metrics["myrorss_days"] == 1
    assert metrics["gridrad_missing_source"] == 1
    assert metrics["manifest_status"]["gridrad"]["missing_source"] == 1
    assert metrics["validation"]["n_pairs"] is None
    assert metrics["stochastic"]["status"] == "not_available"
    out = capsys.readouterr().out
    assert "WARNING: SKIP metrics_hail_day_climatology" in out


def test_validation_metrics_include_pair_count_and_holdout_disclosure(
    tmp_path: Path,
    monkeypatch,
):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    (validation_dir / "validation_summary.txt").write_text(
        "Total report–MESH pairs: 12,345\n"
    )
    diagnostics = tmp_path / "artifact_classifier_diagnostics.json"
    diagnostics.write_text(
        '{"metrics": {"n_train": 80, "n_test": 20, "roc_auc": 0.9}}'
    )
    monkeypatch.setattr(rpf, "VALID_DIR", validation_dir)
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER_DIAGNOSTICS", diagnostics)

    metrics = _validation_metrics()

    assert metrics["n_pairs"] == 12_345
    assert metrics["holdout_tuning_disclosure_required"] is True
    assert metrics["artifact_classifier_split"]["n_test"] == 20
    assert "not an independent validation dataset" in metrics[
        "holdout_tuning_disclosure"
    ]


def test_stochastic_metrics_report_partial_state_and_available_peak(
    tmp_path: Path,
    monkeypatch,
):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    map_dir = tmp_path / "maps"
    _write_tif(map_dir / "rp_00100yr_stochastic.tif", np.array([[0, 41.25]]))
    monkeypatch.setattr(rpf, "RP_YEARS", (100, 1000))
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", map_dir)
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", tmp_path / "pet")
    monkeypatch.setattr(rpf, "STOCH_CATALOG", tmp_path / "missing.parquet")

    metrics = _stochastic_metrics()

    assert metrics["complete"] is False
    assert metrics["status"] == "partial"
    assert metrics["available_return_period_maps"] == [100]
    assert metrics["peak_metrics"]["rp_100yr_map_max_mm"] == 41.2


def test_stochastic_metrics_report_complete_state_and_pet_peaks(
    tmp_path: Path,
    monkeypatch,
):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    map_dir = tmp_path / "maps"
    pet_dir = tmp_path / "pet"
    _write_tif(map_dir / "rp_00100yr_stochastic.tif", np.array([[0, 40]]))
    _write_tif(map_dir / "rp_01000yr_stochastic.tif", np.array([[0, 70]]))
    pet_dir.mkdir()
    pd.DataFrame(
        {
            "return_period_yr": [100, 1000],
            "peak_hail_mm": [55.5, 88.8],
        }
    ).to_csv(pet_dir / "pet_occurrence.csv", index=False)
    pd.DataFrame(
        {
            "return_period_yr": [100],
            "agg_n_cells": [10],
            "agg_n_events": [3],
        }
    ).to_csv(pet_dir / "pet_aggregate.csv", index=False)
    catalog = tmp_path / "catalog.parquet"
    pd.DataFrame({"sim_year": [0, rpf.N_SIM_YEARS - 1]}).to_parquet(
        catalog,
        index=False,
    )
    monkeypatch.setattr(rpf, "RP_YEARS", (100, 1000))
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", map_dir)
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", pet_dir)
    monkeypatch.setattr(rpf, "STOCH_CATALOG", catalog)

    metrics = _stochastic_metrics()

    assert metrics["complete"] is True
    assert metrics["status"] == "complete"
    assert metrics["simulated_years"] == rpf.N_SIM_YEARS
    assert metrics["peak_metrics"]["rp_1000yr_map_max_mm"] == 70.0
    assert metrics["peak_metrics"]["oep_100yr_peak_mm"] == 55.5

    pd.DataFrame({"sim_year": [0, 999]}).to_parquet(catalog, index=False)
    smoke_metrics = _stochastic_metrics()
    assert smoke_metrics["complete"] is False
    assert smoke_metrics["status"] == "partial"
    assert smoke_metrics["simulated_years"] == 1000
