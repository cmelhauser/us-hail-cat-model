"""Tests for geometry-aware artifact classifier features."""

from __future__ import annotations

import numpy as np
import pytest

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


def test_era_one_hot_sources():
    from scripts._artifact_features import era_one_hot

    assert era_one_hot("GridRad") == (1.0, 0.0)
    assert era_one_hot("MRMS") == (0.0, 1.0)
    assert era_one_hot("MYRORSS") == (0.0, 0.0)


def test_build_feature_matrix_empty_active():
    mesh = np.zeros((3, 3), dtype=np.float32)
    range_km = np.zeros((3, 3), dtype=np.float32)
    az = np.zeros((3, 3), dtype=np.float32)
    feats, active = build_feature_matrix(
        mesh, range_km=range_km, azimuth_deg=az, day_of_year=100, source="GridRad", active_mm=5.0
    )
    assert feats.size == 0
    assert not active.any()


def test_hail_likelihood_weights_length_mismatch():
    mesh = np.array([[40.0]], dtype=np.float32)
    active = np.array([[True]])
    with pytest.raises(ValueError, match="probability length"):
        apply_hail_likelihood_weights(mesh, np.array([0.5, 0.5], dtype=np.float32), active)


def test_era_one_hot_mrms_and_unknown():
    from scripts._artifact_features import era_one_hot

    assert era_one_hot("MRMS") == (0.0, 1.0)
    assert era_one_hot("myrorss") == (0.0, 0.0)


def test_build_feature_matrix_empty_active_mrms_default_threshold():
    mesh = np.zeros((3, 3), dtype=np.float32)
    range_km = np.zeros((3, 3), dtype=np.float32)
    az = np.zeros((3, 3), dtype=np.float32)
    feats, active = build_feature_matrix(
        mesh, range_km=range_km, azimuth_deg=az, day_of_year=10, source="MRMS"
    )
    assert feats.shape == (0, len(ARTIFACT_FEATURE_NAMES))
    assert not active.any()


def test_hail_likelihood_weights_length_mismatch_message():
    mesh = np.array([[40.0]], dtype=np.float32)
    active = np.array([[True]])
    try:
        apply_hail_likelihood_weights(mesh, np.array([0.5, 0.5], dtype=np.float32), active)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "probability length" in str(exc)
