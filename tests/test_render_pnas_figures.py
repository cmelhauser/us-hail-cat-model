"""Tests for PNAS figure renderer skip behavior."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from scripts.diagnostics.render_pnas_article_figures import (
    MANIFESTS,
    _render_rp_map_png,
    _stochastic_metrics,
    _validation_metrics,
    classify_source,
    collect_metrics,
    fig_ai_workflow,
    fig_analytical_vs_stochastic,
    fig_calibration_ecdf,
    fig_data_source_timeline,
    fig_event_dispersion,
    fig_hail_days_map,
    fig_manifest_coverage,
    fig_rp_maps,
    fig_seasonal_thresholds,
    fig_source_transition_peaks,
    fig_stochastic_rp,
    fig_validation_by_bin,
    load_manifest,
    run_figure,
    setup_plt,
)
from tests._diagnostics_fixtures import write_grid_tif


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
        json.dumps(
            {
                "split": "grouped_by_year",
                "train_years": [2015, 2016],
                "holdout_years": [2017],
                "metrics": {"n_train": 80, "n_test": 20, "roc_auc": 0.9},
            }
        )
    )
    monkeypatch.setattr(rpf, "VALID_DIR", validation_dir)
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER_DIAGNOSTICS", diagnostics)

    metrics = _validation_metrics()

    assert metrics["n_pairs"] == 12_345
    assert metrics["holdout_tuning_disclosure_required"] is True
    assert metrics["artifact_classifier_split"]["n_test"] == 20
    assert "year-grouped holdout" in metrics["holdout_tuning_disclosure"]
    assert "random 80/20" not in metrics["holdout_tuning_disclosure"]
    assert "not an independent" in metrics["holdout_tuning_disclosure"]


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


def test_setup_plt_and_classify_source():
    setup_plt()
    from datetime import date

    assert classify_source(date(2010, 6, 1)) == "MYRORSS"
    assert classify_source(date(2015, 6, 1)) == "GridRad"
    assert classify_source(date(2022, 6, 1)) == "MRMS"


def test_load_manifest(tmp_path: Path):
    path = tmp_path / "manifest.csv"
    pd.DataFrame({"date": ["2015-06-01"], "status": ["ok"]}).to_csv(path, index=False)
    df = load_manifest(path, "GridRad")
    assert df.iloc[0]["source"] == "GridRad"


def test_run_figure_os_error(tmp_path: Path, capsys):
    def boom(_out):
        raise OSError("disk full")

    assert run_figure("fig_os", boom, tmp_path / "x.png", default={}) == {}
    assert "WARNING: SKIP fig_os" in capsys.readouterr().out


def test_figure_helpers_with_synthetic_inputs(tmp_path: Path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf
    from scripts._config import NCOLS, NROWS

    fig_data_source_timeline(tmp_path / "fig01.png")
    fig_ai_workflow(tmp_path / "fig11.png")

    manifest = tmp_path / "myrorss.csv"
    pd.DataFrame(
        {"date": ["2010-06-01", "2010-06-02"], "status": ["ok", "missing_source"]}
    ).to_csv(manifest, index=False)
    pivot = fig_manifest_coverage({"MYRORSS": manifest}, tmp_path / "fig02.png")
    assert not pivot.empty

    peaks = tmp_path / "peaks.csv"
    pd.DataFrame(
        {
            "date": pd.date_range("2010-01-01", periods=40, freq="ME"),
            "peak_mm": np.linspace(10, 80, 40),
        }
    ).to_csv(peaks, index=False)
    monkeypatch.setattr(rpf, "PEAKS_CSV", peaks)
    stats = fig_source_transition_peaks(tmp_path / "fig03.png")
    assert stats

    cal_peaks = tmp_path / "cal.csv"
    pd.DataFrame(
        {
            "source": ["MYRORSS", "GridRad", "MRMS"],
            "peak_raw_mm": [20.0, 30.0, 25.0],
            "peak_cal_mm": [25.0, 35.0, 28.0],
        }
    ).to_csv(cal_peaks, index=False)
    monkeypatch.setattr(rpf, "CAL_PEAKS_CSV", cal_peaks)
    assert fig_calibration_ecdf(tmp_path / "fig04.png")

    clim = tmp_path / "clim"
    clim.mkdir()
    pd.DataFrame(
        {
            "threshold_label": ["29 mm"],
            **{f"month_{mo:02d}": [mo * 2] for mo in range(1, 13)},
        }
    ).to_csv(clim / "monthly_national_hail_days.csv", index=False)
    monkeypatch.setattr(rpf, "HAIL_CLIM_DIR", clim)
    fig_seasonal_thresholds(tmp_path / "fig05.png")

    hail_days = np.zeros((NROWS, NCOLS), dtype=np.float32)
    hail_days[100:110, 200:210] = 3.0
    write_grid_tif(clim / "hail_days_per_year_skill_29mm.tif", hail_days)
    fig_hail_days_map(tmp_path / "fig06.png")

    valid = tmp_path / "validation"
    valid.mkdir()
    pd.DataFrame({"bin": ["1"], "n": [10], "bias_in": [0.1], "pod": [0.8]}).to_csv(
        valid / "calibration_report.csv", index=False
    )
    (valid / "validation_summary.txt").write_text("Total report–MESH pairs: 100\n")
    monkeypatch.setattr(rpf, "VALID_DIR", valid)
    assert fig_validation_by_bin(tmp_path / "fig07.png")

    cdf = tmp_path / "cdf"
    cdf.mkdir()
    rp100 = np.zeros((NROWS, NCOLS), dtype=np.float32)
    rp100[100:120, 200:220] = 50.0
    rp1000 = np.zeros((NROWS, NCOLS), dtype=np.float32)
    rp1000[100:120, 200:220] = 70.0
    write_grid_tif(cdf / "rp_00100yr_hail_smooth.tif", rp100)
    write_grid_tif(cdf / "rp_01000yr_hail_smooth.tif", rp1000)
    monkeypatch.setattr(rpf, "CDF_DIR", cdf)
    rp_stats = fig_rp_maps(tmp_path / "fig08.png", tmp_path / "fig09.png")
    assert "rp_100yr" in rp_stats

    events = tmp_path / "events.csv"
    pd.DataFrame({"start_date": pd.date_range("2010-01-01", periods=20, freq="ME")}).to_csv(
        events, index=False
    )
    monkeypatch.setattr(rpf, "EVENT_CSV", events)
    assert fig_event_dispersion(tmp_path / "fig10.png")


def test_validation_metrics_non_grouped_split(tmp_path: Path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    model = tmp_path / "model.pkl"
    model.write_bytes(b"x")
    diagnostics = tmp_path / "artifact_classifier_diagnostics.json"
    diagnostics.write_text(
        json.dumps({"split": "random", "metrics": {"n_train": 10, "n_test": 5}})
    )
    monkeypatch.setattr(rpf, "VALID_DIR", validation_dir)
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER_DIAGNOSTICS", diagnostics)
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER", model)

    metrics = _validation_metrics()
    assert "random" in metrics["holdout_tuning_disclosure"]


def test_main_render_pnas_figures(tmp_path: Path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    out_fig = tmp_path / "figs"
    out_metrics = tmp_path / "metrics.json"
    monkeypatch.setattr(rpf, "OUT_FIG", out_fig)
    monkeypatch.setattr(rpf, "OUT_METRICS", out_metrics)
    monkeypatch.setattr(rpf, "PEAKS_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(rpf, "CAL_PEAKS_CSV", tmp_path / "missing_cal.csv")
    monkeypatch.setattr(rpf, "HAIL_CLIM_DIR", tmp_path / "clim")
    monkeypatch.setattr(rpf, "VALID_DIR", tmp_path / "validation")
    monkeypatch.setattr(rpf, "EVENT_CSV", tmp_path / "events.csv")
    monkeypatch.setattr(rpf, "CDF_DIR", tmp_path / "cdf")
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", tmp_path / "stoch_maps")
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", tmp_path / "stoch_pet")
    monkeypatch.setattr(rpf, "STOCH_CATALOG", tmp_path / "catalog.parquet")
    for source in MANIFESTS:
        monkeypatch.setitem(rpf.MANIFESTS, source, tmp_path / f"{source}.csv")
    rpf.main()
    assert out_metrics.exists()


def test_stochastic_and_comparison_figures(tmp_path: Path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf
    from scripts._config import NCOLS, NROWS

    map_dir = tmp_path / "maps"
    map_dir.mkdir()
    rp100 = np.zeros((NROWS, NCOLS), dtype=np.float32)
    rp100[100:120, 200:220] = 45.0
    write_grid_tif(map_dir / "rp_00100yr_stochastic.tif", rp100)
    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    write_grid_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", rp100)
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", map_dir)
    monkeypatch.setattr(rpf, "CDF_DIR", cdf_dir)
    fig_stochastic_rp(tmp_path / "fig12.png")
    fig_analytical_vs_stochastic(tmp_path / "fig13.png")
    assert (tmp_path / "fig12.png").exists()
    assert (tmp_path / "fig13.png").exists()


def test_render_rp_map_png_branches(tmp_path: Path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf
    from scripts._config import NCOLS, NROWS

    missing = tmp_path / "missing.tif"
    assert _render_rp_map_png(missing, tmp_path / "out.png", title="x") is False

    tif = tmp_path / "rp.tif"
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[50:60, 50:60] = 30.0
    write_grid_tif(tif, data)
    assert _render_rp_map_png(tif, tmp_path / "mm.png", title="mm", inches=False) is True
