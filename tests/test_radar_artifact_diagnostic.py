"""Smoke tests for radar artifact diagnostic helpers."""

from __future__ import annotations

import numpy as np

from scripts.diagnostics.radar_artifact_diagnostic import local_median_8, range_binned_cell_stats


def test_local_median_8_peak_isolated():
    data = np.zeros((5, 5), dtype=np.float32)
    data[2, 2] = 100.0
    med = local_median_8(data)
    assert med[2, 2] < 10.0


def test_range_binned_cell_stats_bins():
    mean_annual = np.zeros((10, 10), dtype=np.float32)
    mean_annual[2:4, 2:4] = 50.0
    range_km = np.full((10, 10), 60.0, dtype=np.float32)
    edges = np.array([0, 50, 100, 200], dtype=np.float32)
    df = range_binned_cell_stats(mean_annual, range_km, edges)
    assert len(df) == 3
    assert df.loc[1, "mean_annual_max_mm"] == 50.0
