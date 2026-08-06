"""Tests for geometry-aware artifact classifier features."""

from __future__ import annotations

import numpy as np

from scripts._artifact_features import (
    ARTIFACT_FEATURE_NAMES,
    apply_hail_likelihood_weights,
    build_feature_matrix,
    build_single_cell_features,
)


def test_build_feature_matrix_shape():
    mesh = np.zeros((4, 4), dtype=np.float32)
    mesh[2, 2] = 40.0
    range_km = np.full((4, 4), 80.0, dtype=np.float32)
    az = np.zeros((4, 4), dtype=np.float32)
    feats, active = build_feature_matrix(
        mesh, range_km=range_km, azimuth_deg=az, day_of_year=180, source="GridRad",
    )
    assert feats.shape == (1, len(ARTIFACT_FEATURE_NAMES))
    assert active.sum() == 1


def test_single_cell_features_length():
    row = build_single_cell_features(50.0, 100.0, 45.0, 30.0, 150, "GridRad")
    assert row.shape == (len(ARTIFACT_FEATURE_NAMES),)


def test_hail_likelihood_weights_keep_likely_hail_and_reduce_weak_cells():
    mesh = np.array([[40.0, 50.0]], dtype=np.float32)
    active = np.array([[True, True]])
    out = apply_hail_likelihood_weights(
        mesh,
        np.array([0.25, 1.0], dtype=np.float32),
        active,
    )
    assert out.tolist() == [[10.0, 50.0]]
