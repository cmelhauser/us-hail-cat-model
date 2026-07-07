"""Tests for per-cell hail-day climatology diagnostic."""

from __future__ import annotations

from datetime import date

import pytest
import numpy as np

from scripts._config import NCOLS, NROWS
from scripts.diagnostics.hail_day_climatology import (
    DEFAULT_THRESHOLDS,
    ThresholdSpec,
    selected_thresholds,
    summarize_per_cell,
)


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
    from scripts.diagnostics.hail_day_climatology import classify_source

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

