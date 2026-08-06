"""Additional Stage 01/02 coverage for sequential paths and validation edge cases."""

from __future__ import annotations

import gzip
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio

from scripts._config import NCOLS, NROWS
from scripts._io import write_geotiff
from tests.test_01_download_myrorss_coverage import _FakeS3, _FakeS3Body, _minimal_myrorss_nc


def test_stage01_parse_sparse_mesh_updates_daily_max(load_script):
    s = load_script("01_download_myrorss.py")
    px = np.array([s.CONUS_ROW_START + 2], dtype=np.int16)
    py = np.array([s.CONUS_COL_START + 3], dtype=np.int16)
    nc = _minimal_myrorss_nc(px, py, np.array([33.0], dtype=np.float32))
    daily = np.zeros((50, 60), dtype=np.float32)
    n = s.parse_sparse_mesh(nc, daily)
    assert n == 1
    assert daily.max() > 0


def test_stage01_process_day_sequential_success_and_parallel_qa_log(
    load_script, tmp_path, monkeypatch,
):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "CONUS_NROWS", 50)
    monkeypatch.setattr(s, "CONUS_NCOLS", 60)
    monkeypatch.setattr(s, "OUT_NROWS", 10)
    monkeypatch.setattr(s, "OUT_NCOLS", 12)
    day = date(2000, 7, 4)

    px = np.array([s.CONUS_ROW_START + 5], dtype=np.int16)
    py = np.array([s.CONUS_COL_START + 6], dtype=np.int16)
    nc = _minimal_myrorss_nc(px, py, np.array([301.0], dtype=np.float32))
    s3 = _FakeS3({"k.netcdf": nc})
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: ["k.netcdf"])

    seq = s.process_day(s3, day, workers=1)
    assert seq["files"] == 1

    def bad_fetch(key):
        px2 = np.array([s.CONUS_ROW_START + 1], dtype=np.int16)
        py2 = np.array([s.CONUS_COL_START + 1], dtype=np.int16)
        nc2 = _minimal_myrorss_nc(px2, py2, np.array([301.0], dtype=np.float32))
        return key, np.array([1], np.int32), np.array([1], np.int32), np.array([301.0], np.float32), 1, None

    monkeypatch.setattr(s, "_fetch_decode_sparse", bad_fetch)
    day2 = date(2000, 7, 5)
    par = s.process_day(s3, day2, workers=2)
    assert par["files"] == 1

    def err_fetch(key):
        return key, np.array([], np.int32), np.array([], np.int32), np.array([], np.float32), 0, RuntimeError("x")

    monkeypatch.setattr(s, "_fetch_decode_sparse", err_fetch)
    day3 = date(2000, 7, 6)
    par_err = s.process_day(s3, day3, workers=2)
    assert par_err["errors"] >= 1


def test_stage01_rebuild_manifest_missing_keys_only(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    day = date(1999, 6, 1)
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: [])
    n = s.rebuild_manifest_from_outputs(_FakeS3(), day, day)
    assert n == 1


def test_stage01_validate_spot_check_failures(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    good = tmp_path / "1999" / "mesh_19990601.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good)
    monkeypatch.setattr(s, "iter_stage01_tifs", lambda: [good] * 4001)
    assert s.validate_outputs() is True


def test_stage01_main_year_only_and_dry_run_progress(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "get_s3_client", lambda: _FakeS3())
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(s, "qa_repair_existing_outputs", lambda: {"files_scanned": 0})

    n = {"v": 0}

    def proc(*_a, **_k):
        n["v"] += 1
        if n["v"] <= 100:
            return {"files": 1, "dry_run": True}
        return {"files": 1, "max_mesh_mm": 75.0}

    monkeypatch.setattr(s, "process_day", proc)
    with pytest.raises(SystemExit):
        s.main(["--year", "2000"])


def test_stage02_timestep_conus_mesh_from_grib_bytes(load_script, monkeypatch, tmp_path):
    from unittest.mock import MagicMock, patch

    s = load_script("02_download_mrms_mesh.py")
    conus = np.zeros((s.CONUS_NROWS, s.CONUS_NCOLS), dtype=np.float32)
    conus[10, 10] = 40.0
    conus[0, 0] = -1.0
    conus[1, 1] = np.nan
    conus[2, 2] = 400.0

    full = np.zeros((s.NATIVE_NROWS, s.NATIVE_NCOLS), dtype=np.float32)
    full[s.CONUS_ROW_START:s.CONUS_ROW_END, s.CONUS_COL_START:s.CONUS_COL_END] = conus[::-1, :]

    mesh_var = MagicMock()
    mesh_var.values = full
    mock_ds = MagicMock()
    mock_ds.data_vars = {"MESH": mesh_var}
    mock_ds.__getitem__ = MagicMock(return_value=mesh_var)
    mock_ds.close = MagicMock()

    with patch("xarray.open_dataset", return_value=mock_ds):
        out, n = s.timestep_conus_mesh_from_grib_bytes(b"fake-grib")
    assert n == 1
    assert out[10, 10] == 40.0


def test_stage02_process_day_sequential_and_parallel_errors(load_script, tmp_path, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "CONUS_NROWS", 100)
    monkeypatch.setattr(s, "CONUS_NCOLS", 100)
    monkeypatch.setattr(s, "OUT_NROWS", 20)
    monkeypatch.setattr(s, "OUT_NCOLS", 20)
    day = date(2020, 11, 1)

    conus = np.zeros((100, 100), dtype=np.float32)
    conus[8, 8] = 301.0
    gz = gzip.compress(b"grib")

    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: ["k.grib2.gz"])
    monkeypatch.setattr(
        s,
        "timestep_conus_mesh_from_grib_bytes",
        lambda _b: (conus, 1),
    )

    s3 = _FakeS3({"k.grib2.gz": gz})
    res = s.process_day(s3, day, workers=1)
    assert res["files"] == 1

    def bad_fetch(key):
        return key, None, 0, RuntimeError("bad")

    monkeypatch.setattr(s, "_fetch_and_decode_timestep", bad_fetch)
    day2 = date(2020, 11, 2)
    err = s.process_day(s3, day2, workers=2)
    assert err["errors"] >= 1


def test_stage02_rebuild_and_main_year_paths(load_script, tmp_path, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "get_s3_client", lambda: _FakeS3())
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: [])

    n = s.rebuild_manifest_from_outputs(_FakeS3(), date(2020, 10, 15), date(2020, 10, 15))
    assert n == 1

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"files": 1, "max_mesh_mm": 55.0})
    with pytest.raises(SystemExit):
        s.main(["--year", "2020"])


def test_stage02_validate_invalid_values_fail(load_script, tmp_path, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    good = tmp_path / "2020" / "mesh_20201015.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good)

    bad_vals = tmp_path / "2020" / "mesh_20201016.tif"
    arr = np.zeros((NROWS, NCOLS), dtype=np.float32)
    arr[0, 0] = 400.0
    write_geotiff(arr, bad_vals)

    many = [good] * 1000 + [bad_vals]
    orig_rglob = Path.rglob

    def fake_rglob(self, pattern):
        if pattern == "mesh_????????.tif" and self == tmp_path:
            return iter(many)
        return orig_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    assert s.validate_outputs() is False
