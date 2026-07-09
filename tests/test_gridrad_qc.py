"""Tests for GridRad native reflectivity QC (Stage 04c)."""

from __future__ import annotations

import numpy as np

from scripts._gridrad_qc import (
    apply_gridrad_native_qc,
    gridrad_filter_reflectivity,
    gridrad_remove_clutter,
)


def test_gridrad_filter_removes_low_echo_frequency():
    refl = np.full((2, 4, 4), 45.0, dtype=np.float32)
    nobs = np.full((2, 4, 4), 5.0, dtype=np.float32)
    necho = np.full((2, 4, 4), 1.0, dtype=np.float32)
    out = gridrad_filter_reflectivity(refl, nobs, necho)
    assert np.all(np.isnan(out))


def test_gridrad_remove_clutter_removes_isolated_speckle():
    refl = np.full((3, 5, 5), np.nan, dtype=np.float32)
    refl[1, 2, 2] = 50.0
    out = gridrad_remove_clutter(refl)
    assert np.isnan(out[1, 2, 2])


def test_apply_gridrad_native_qc_runs_without_obs_fields():
    refl = np.full((2, 3, 3), 40.0, dtype=np.float32)
    out = apply_gridrad_native_qc(refl, None, None)
    assert out.shape == refl.shape
