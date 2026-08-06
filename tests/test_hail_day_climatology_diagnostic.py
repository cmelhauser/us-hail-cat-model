"""Tests for per-cell hail-day climatology diagnostic."""

from __future__ import annotations

from datetime import date

import pytest
import numpy as np
import pandas as pd

from scripts._config import NCOLS, NROWS
from scripts.diagnostics.hail_day_climatology import (
    DEFAULT_THRESHOLDS,
    ThresholdSpec,
    accumulate_hail_days,
    classify_source,
    iter_mesh_tifs,
    plot_seasonal_curves,
    selected_thresholds,
    summarize_per_cell,
    write_readme,
)
from tests._diagnostics_fixtures import seed_mesh_days


def test_default_thresholds_include_literature_set():
    keys = {t.key for t in DEFAULT_THRESHOLDS}
    assert "conv_25p4mm" in keys
    assert "skill_29mm" in keys
    assert "mesh75_41p9mm" in keys
    assert "sig_50p8mm" in keys


def test_summarize_per_cell_basic_stats():
    counts = np.zeros((20, 20), dtype=np.uint32)
    counts[5:8, 5:8] = 30
    spec = ThresholdSpec("lo", 25.4, "low", "test")
    summary = summarize_per_cell(counts, 10, spec)
    assert summary["cells_with_any_hail_days"] == 9
    assert summary["max_days_per_year_any_cell"] == 3.0


def test_selected_thresholds_filters_keys():
    specs = selected_thresholds("skill_29mm,conv_25p4mm")
    assert [s.key for s in specs] == ["conv_25p4mm", "skill_29mm"]


def test_selected_thresholds_unknown_key_exits():
    with pytest.raises(SystemExit):
        selected_thresholds("not_a_real_threshold")


def test_classify_source_by_era():
    assert classify_source(date(2005, 6, 1)) == "MYRORSS"
    assert classify_source(date(2015, 6, 1)) == "GridRad"
    assert classify_source(date(2022, 6, 1)) == "MRMS"


def test_national_annual_dataframe_shape():
    from scripts.diagnostics.hail_day_climatology import national_annual_dataframe

    annual = {
        2020: {"skill_29mm": 100, "conv_25p4mm": 120},
        2021: {"skill_29mm": 90, "conv_25p4mm": 110},
    }
    df = national_annual_dataframe(annual)
    assert len(df) == 2
    assert "skill_29mm" in df.columns


@pytest.mark.skipif(
    __import__("scripts._mapping", fromlist=["has_cartopy"]).has_cartopy() is False,
    reason="cartopy not installed",
)
def test_plot_maps_writes_lambert_png(tmp_path):
    from scripts.diagnostics.hail_day_climatology import ThresholdSpec, plot_maps

    rates = {
        "skill_29mm": np.zeros((NROWS, NCOLS), dtype=np.float32),
    }
    rates["skill_29mm"][100:110, 200:210] = 3.0
    specs = (ThresholdSpec("skill_29mm", 29.0, "29 mm skill", "Wendt"),)
    paths = plot_maps(rates, specs, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].stat().st_size > 1000


def test_iter_mesh_tifs_and_accumulate(tmp_path, monkeypatch):
    import scripts.diagnostics.hail_day_climatology as hdc

    monkeypatch.setattr(hdc, "NROWS", 8)
    monkeypatch.setattr(hdc, "NCOLS", 8)
    seed_mesh_days(tmp_path, [date(2010, 6, 1), date(2010, 6, 2)], peak=35.0, nrows=8, ncols=8)
    specs = selected_thresholds("skill_29mm")
    cell, monthly, annual, years, n_files = accumulate_hail_days(
        tmp_path, specs, None, None
    )
    assert n_files == 2
    assert years == [2010]
    assert cell["skill_29mm"].sum() > 0


def test_plot_seasonal_and_write_readme(tmp_path):
    monthly_df = pd.DataFrame(
        {
            "threshold_label": ["29 mm"],
            **{f"month_{m:02d}": [10 * m] for m in range(1, 13)},
        }
    )
    plot_seasonal_curves(monthly_df, tmp_path)
    assert (tmp_path / "seasonal_national_hail_days_by_threshold.png").exists()
    write_readme(tmp_path, pd.DataFrame([{"threshold_key": "skill_29mm", "gp_max_days_per_year": 3.0}]))


def test_main_hail_day_climatology(tmp_path, monkeypatch):
    import sys

    import scripts.diagnostics.hail_day_climatology as hdc

    mesh = tmp_path / "mesh"
    out = tmp_path / "out"
    seed_mesh_days(mesh, [date(2010, 6, 1), date(2010, 6, 2)], peak=35.0, nrows=8, ncols=8)
    monkeypatch.setattr(hdc, "NROWS", 8)
    monkeypatch.setattr(hdc, "NCOLS", 8)
    monkeypatch.setattr(hdc.sys, "argv", [
        "hail_day_climatology.py",
        "--mesh-dir", str(mesh),
        "--out-dir", str(out),
        "--thresholds", "skill_29mm,conv_25p4mm",
    ])
    hdc.main()
    assert (out / "threshold_benchmark_summary.csv").exists()
    assert (out / "hail_days_per_year_skill_29mm.tif").exists()


def test_iter_mesh_tifs_filters_and_empty_accumulate(tmp_path, monkeypatch):
    import scripts.diagnostics.hail_day_climatology as hdc

    monkeypatch.setattr(hdc, "NROWS", 8)
    monkeypatch.setattr(hdc, "NCOLS", 8)
    seed_mesh_days(tmp_path, [date(2010, 6, 1)], nrows=8, ncols=8)
    assert list(iter_mesh_tifs(tmp_path, date(2015, 1, 1), None)) == []
    assert list(iter_mesh_tifs(tmp_path, None, date(2005, 1, 1))) == []

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    specs = selected_thresholds(None)
    _, _, annual, years, n_files = accumulate_hail_days(empty_dir, specs, None, None)
    assert n_files == 0 and years == []


def test_main_exits_when_mesh_missing(tmp_path, monkeypatch, capsys):
    import sys

    import scripts.diagnostics.hail_day_climatology as hdc

    monkeypatch.setattr(hdc.sys, "argv", [
        "hail_day_climatology.py",
        "--mesh-dir", str(tmp_path / "missing"),
        "--out-dir", str(tmp_path / "out"),
    ])
    with pytest.raises(SystemExit):
        hdc.main()
    assert "WARNING: SKIP hail_day_climatology" in capsys.readouterr().out

