"""Shared pytest helpers for CONUS hail cat model stage tests."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pytest


def repo_root() -> Path:
    return Path(os.environ.get("HAIL_MODEL_REPO", Path(__file__).resolve().parents[1]))


def scripts_dir() -> Path:
    root = repo_root()
    return root / "scripts" if (root / "scripts").exists() else root


def load_stage(filename: str):
    path = scripts_dir() / filename
    assert path.exists(), f"Missing stage script: {path}"
    module_name = filename.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def small_grid():
    arr = np.zeros((6, 6), dtype=np.float32)
    arr[2:4, 2:4] = [[25.4, 30.0], [28.0, 40.0]]
    return arr
