"""Smoke tests for radar artifact diagnostic helpers."""

from __future__ import annotations

import numpy as np
import pytest

from scripts._config import NROWS, NCOLS
from scripts.diagnostics.radar_artifact_diagnostic import (
    _mean_annual_max_from_year_peaks,
    local_median_8,
    plot_range_distance_map,
    range_binned_cell_stats,
)


def test_local_median_8_peak_isolated():
    data = np.zeros((5, 5), dtype=np.float32)
    data[2, 2] = 100.0
    med = local_median_8(data)
    assert med[2, 2] < 10.0


def test_mean_annual_max_from_year_peaks():
    a = np.zeros((4, 4), dtype=np.float32)
    a[1, 1] = 40.0
    b = np.zeros((4, 4), dtype=np.float32)
    b[1, 1] = 20.0
    out = _mean_annual_max_from_year_peaks({2020: a, 2021: b})
    assert out[1, 1] == 30.0


def test_range_binned_cell_stats_bins():
    mean_annual = np.zeros((10, 10), dtype=np.float32)
    mean_annual[2:4, 2:4] = 50.0
    range_km = np.full((10, 10), 60.0, dtype=np.float32)
    edges = np.array([0, 50, 100, 200], dtype=np.float32)
    df = range_binned_cell_stats(mean_annual, range_km, edges)
    assert len(df) == 3
    assert df.loc[1, "mean_annual_max_mm"] == 50.0


@pytest.mark.skipif(
    __import__("scripts._mapping", fromlist=["has_cartopy"]).has_cartopy() is False,
    reason="cartopy not installed",
)
def test_plot_range_distance_map_writes_png(tmp_path):
    range_km = np.linspace(0, 300, NROWS * NCOLS, dtype=np.float32).reshape(NROWS, NCOLS)
    path = plot_range_distance_map(range_km, tmp_path)
    assert path.exists()
    assert path.name == "map_nearest_radar_distance_km.png"
    assert path.stat().st_size > 1000
