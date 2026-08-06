"""Tests for the research SPC weak-label classifier."""

from __future__ import annotations

import numpy as np


def test_classifier_uses_disjoint_year_holdout(load_script):
    trainer = load_script("train_artifact_classifier.py")
    rng = np.random.default_rng(42)
    n_per_year = 40
    years = ("2016", "2017", "2018", "2019")
    groups = np.concatenate(
        [np.full(n_per_year, f"{year}0601", dtype="U8") for year in years]
    )
    y = np.tile(np.array([0, 1], dtype=np.int8), len(groups) // 2)
    X = rng.normal(size=(len(groups), len(trainer.ARTIFACT_FEATURE_NAMES))).astype(
        np.float32
    )
    X[:, 0] += y * 2.0

    _model, metrics = trainer.train_classifier(X, y, groups)

    assert metrics["split"] == "grouped_by_year"
    assert set(metrics["train_years"]).isdisjoint(metrics["holdout_years"])
    assert metrics["n_train"] + metrics["n_test"] == len(y)
