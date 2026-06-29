"""Tests for per-cell hail-day climatology diagnostic."""

from __future__ import annotations

import numpy as np

from scripts.diagnostics.hail_day_climatology import (
    DEFAULT_THRESHOLDS,
    ThresholdSpec,
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
