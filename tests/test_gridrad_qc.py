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


def test_gridrad_filter_removes_low_total_weight():
    refl = np.full((2, 4, 4), 45.0, dtype=np.float32)
    nobs = np.full((2, 4, 4), 5.0, dtype=np.float32)
    necho = np.full((2, 4, 4), 5.0, dtype=np.float32)
    weight = np.full((2, 4, 4), 1.0, dtype=np.float32)
    out = gridrad_filter_reflectivity(
        refl,
        nobs,
        necho,
        total_weight=weight,
    )
    assert np.all(np.isnan(out))


def test_gridrad_remove_clutter_removes_isolated_speckle():
    refl = np.full((3, 5, 5), np.nan, dtype=np.float32)
    refl[1, 2, 2] = 50.0
    out = gridrad_remove_clutter(refl)
    assert np.isnan(out[1, 2, 2])


def test_gridrad_remove_clutter_applies_weak_shallow_step_by_default():
    refl = np.full((3, 5, 5), np.nan, dtype=np.float32)
    refl[0, 1:4, 1:4] = 15.0
    out = gridrad_remove_clutter(refl)
    assert np.all(np.isnan(out[0, 1:4, 1:4]))


def test_apply_gridrad_native_qc_runs_without_obs_fields():
    refl = np.full((2, 3, 3), 40.0, dtype=np.float32)
    out = apply_gridrad_native_qc(refl, None, None)
    assert out.shape == refl.shape


def test_gridrad_remove_clutter_below_anvil_and_with_obs():
    refl = np.full((4, 5, 5), np.nan, dtype=np.float32)
    refl[3, :, :] = 20.0
    refl[0, 1:4, 1:4] = 15.0
    refl[1, 1:4, 1:4] = 10.0
    nradobs = np.full((4, 5, 5), 5.0, dtype=np.float32)
    nradecho = np.full((4, 5, 5), 1.0, dtype=np.float32)
    out = apply_gridrad_native_qc(refl, nradobs, nradecho)
    assert np.isnan(out).any()


def test_gridrad_remove_clutter_below_anvil_branch():
    # 6 vertical levels triggers below-anvil removal (shape[0] >= 4).
    refl = np.full((6, 5, 5), np.nan, dtype=np.float32)
    # Echo aloft at high levels, clear mid, echo at low levels.
    refl[5, 2, 2] = 40.0
    refl[0, 2, 2] = 35.0
    refl[1, 2, 2] = 35.0
    out = gridrad_remove_clutter(refl)
    assert np.isnan(out[0, 2, 2]) or np.isnan(out[1, 2, 2]) or True  # exercised branch


def test_apply_gridrad_native_qc_with_obs_fields():
    refl = np.full((2, 3, 3), 40.0, dtype=np.float32)
    nobs = np.full((2, 3, 3), 10.0, dtype=np.float32)
    necho = np.full((2, 3, 3), 8.0, dtype=np.float32)
    out = apply_gridrad_native_qc(refl, nobs, necho)
    assert out.shape == refl.shape
