"""Extended tests for scripts/11_build_occurrence_probs.py."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from conftest import load_stage


@pytest.fixture
def s11():
    return load_stage("11_build_occurrence_probs.py")


def test_stage11_thresholds_are_increasing(s11):
    mm = [x * s11.MM_PER_IN for x in s11.THRESHOLDS_IN]
    assert all(b > a for a, b in zip(mm, mm[1:]))


def test_validate_outputs_missing(s11, tmp_path, monkeypatch):
    monkeypatch.setattr(s11, "OUT_DIR", tmp_path / "occ")
    assert s11.validate_outputs() is False


def test_validate_outputs_passes(s11, tmp_path, monkeypatch):
    out_dir = tmp_path / "occ"
    out_dir.mkdir()
    for t in s11.THRESHOLDS_IN:
        tag = f"{t:.2f}".replace(".", "p")
        (out_dir / f"p_occ_{tag}in.tif").write_bytes(b"x")
    monkeypatch.setattr(s11, "OUT_DIR", out_dir)
    assert s11.validate_outputs() is True


def test_main_builds_rasters(tmp_path, s11, monkeypatch):
    nrows, ncols = 2, 2
    monkeypatch.setattr(s11, "NROWS", nrows)
    monkeypatch.setattr(s11, "NCOLS", ncols)
    mesh_dir = tmp_path / "mesh"
    ydir = mesh_dir / "2015"
    ydir.mkdir(parents=True)
    data = np.array([[30.0, 0.0], [0.0, 60.0]], dtype=np.float32)
    with rasterio.open(
        ydir / "mesh_20150601.tif",
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

    out_dir = tmp_path / "occ"
    monkeypatch.setattr(s11, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s11, "OUT_DIR", out_dir)
    monkeypatch.setattr(sys, "argv", ["11_build_occurrence_probs.py"])
    with pytest.raises(SystemExit) as exc:
        s11.main()
    assert exc.value.code == 0
    assert len(list(out_dir.glob("p_occ_*.tif"))) == len(s11.THRESHOLDS_IN)


def test_main_validate_only(s11, tmp_path, monkeypatch):
    out_dir = tmp_path / "occ"
    out_dir.mkdir()
    for t in s11.THRESHOLDS_IN:
        tag = f"{t:.2f}".replace(".", "p")
        (out_dir / f"p_occ_{tag}in.tif").write_bytes(b"x")
    monkeypatch.setattr(s11, "OUT_DIR", out_dir)
    monkeypatch.setattr(sys, "argv", ["11_build_occurrence_probs.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s11.main()
    assert exc.value.code == 0
