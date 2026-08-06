"""Extended tests for scripts/train_artifact_classifier.py."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from conftest import load_stage


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


def _write_mesh_tif(path: Path, value: float, nrows: int = 4, ncols: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros((nrows, ncols), dtype=np.float32)
    data[1, 1] = value
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-100, 40, 0.05, 0.05),
    ) as dst:
        dst.write(data, 1)


def test_load_raster_prefers_corrected(tmp_path, load_script):
    trainer = load_script("train_artifact_classifier.py")
    corrected = tmp_path / "corrected" / "2015" / "mesh_20150601.tif"
    raw = tmp_path / "raw" / "2015" / "mesh_20150601.tif"
    _write_mesh_tif(corrected, 55.0)
    _write_mesh_tif(raw, 10.0)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(trainer, "CORRECTED_DIR", tmp_path / "corrected")
    monkey.setattr(trainer, "DATA_ROOT", tmp_path)
    try:
        arr = trainer._load_raster("20150601")
        assert arr is not None
        assert float(arr[1, 1]) == 55.0
        assert trainer._load_raster("19990101") is None
    finally:
        monkey.undo()


def test_build_training_sets_gridrad_only(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    mesh_dir = tmp_path / "corrected"
    _write_mesh_tif(mesh_dir / "2015" / "mesh_20150601.tif", 60.0)
    _write_mesh_tif(mesh_dir / "2010" / "mesh_20100601.tif", 60.0)

    monkeypatch.setattr(trainer, "CORRECTED_DIR", mesh_dir)
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    nrows, ncols = 4, 4
    monkeypatch.setattr(
        trainer,
        "ensure_range_km_grid",
        lambda: np.full((nrows, ncols), 50.0, dtype=np.float32),
    )
    monkeypatch.setattr(
        trainer,
        "ensure_nearest_site_index_grid",
        lambda: np.zeros((nrows, ncols), dtype=np.int16),
    )
    monkeypatch.setattr(
        trainer,
        "azimuth_to_nearest_site_deg",
        lambda: np.zeros((nrows, ncols), dtype=np.float32),
    )

    pairs = pd.DataFrame(
        [
            {"date": "20150601", "grid_row": 1, "grid_col": 1, "spc_size_in": 1.5, "mesh75_mm": 60.0},
            {"date": "20100601", "grid_row": 1, "grid_col": 1, "spc_size_in": 1.5, "mesh75_mm": 60.0},
        ]
    )
    rng = np.random.default_rng(42)
    X, y, groups = trainer.build_training_sets(pairs, max_neg_per_day=5, rng=rng, gridrad_only=True)
    assert X.shape[0] == y.shape[0] == groups.shape[0]
    assert y.sum() >= 1
    assert all(g.startswith("2015") for g in groups[y == 1])


def test_build_training_sets_no_samples_raises(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    monkeypatch.setattr(trainer, "CORRECTED_DIR", tmp_path / "empty")
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    pairs = pd.DataFrame(columns=["date", "grid_row", "grid_col", "spc_size_in", "mesh75_mm"])
    with pytest.raises(RuntimeError, match="No training samples"):
        trainer.build_training_sets(pairs, max_neg_per_day=10, rng=np.random.default_rng(0))


def test_main_writes_model_and_diagnostics(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    pairs_path = tmp_path / "pairs.csv"
    pd.DataFrame(
        [{"date": "20160601", "grid_row": 1, "grid_col": 1, "spc_size_in": 1.5, "mesh75_mm": 55.0}]
    ).to_csv(pairs_path, index=False)
    out_model = tmp_path / "model.pkl"
    cal_dir = tmp_path / "cal"

    def fake_build(*_a, **_k):
        X = np.random.default_rng(0).normal(size=(80, len(trainer.ARTIFACT_FEATURE_NAMES))).astype(np.float32)
        y = np.array([0, 1] * 40, dtype=np.int8)
        groups = np.array([f"201{y%2+6}0601" for y in range(80)], dtype="U8")
        return X, y, groups

    monkeypatch.setattr(trainer, "build_training_sets", fake_build)
    monkeypatch.setattr(
        trainer,
        "train_classifier",
        lambda X, y, groups: (
            object(),
            {"roc_auc": 0.8, "split": "grouped_by_year", "train_years": ["2016"], "holdout_years": ["2017"], "n_train": 60, "n_test": 20},
        ),
    )
    monkeypatch.setattr(trainer, "CAL_DIR", cal_dir)
    monkeypatch.setattr(trainer, "OUT_DIAG", cal_dir / "diag.json")

    trainer.main(["--pairs", str(pairs_path), "--output", str(out_model)])
    assert out_model.is_file()
    with open(out_model, "rb") as f:
        payload = pickle.load(f)
    assert "model" in payload
    assert (cal_dir / "diag.json").is_file()
    diag = json.loads((cal_dir / "diag.json").read_text())
    assert diag["metrics"]["split"] == "grouped_by_year"


def test_main_missing_pairs_raises(tmp_path, load_script):
    trainer = load_script("train_artifact_classifier.py")
    with pytest.raises(FileNotFoundError, match="Missing pairs"):
        trainer.main(["--pairs", str(tmp_path / "nope.csv")])
