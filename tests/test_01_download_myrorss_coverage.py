"""Coverage tests for Stage 01 — mocked I/O, CLI branches, validation."""

from __future__ import annotations

import gzip
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio

from scripts._config import NCOLS, NROWS
from scripts._io import write_geotiff


def _minimal_myrorss_nc(
    px: np.ndarray,
    py: np.ndarray,
    mesh: np.ndarray,
) -> bytes:
    import netCDF4 as nc

    fd, tmp = tempfile.mkstemp(suffix=".nc")
    os.close(fd)
    try:
        with nc.Dataset(tmp, "w") as ds:
            ds.createDimension("pixel", len(px))
            ds.createVariable("pixel_x", "i2", ("pixel",))[:] = px
            ds.createVariable("pixel_y", "i2", ("pixel",))[:] = py
            v = ds.createVariable("MESH", "f4", ("pixel",))
            v[:] = mesh
            ds.Latitude = 55.005
            ds.Longitude = -130.005
            ds.LatGridSpacing = 0.01
            ds.LonGridSpacing = 0.01
            ds.MissingData = -99900.0
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp)


class _FakeS3Body:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload


class _FakeS3:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self._objects = objects or {}
        self.get_calls: list[str] = []

    def get_object(self, *, Bucket, Key):
        self.get_calls.append(Key)
        if Key not in self._objects:
            raise KeyError(Key)
        return {"Body": _FakeS3Body(self._objects[Key])}

    def get_paginator(self, name):
        assert name == "list_objects_v2"

        class _Pag:
            def __init__(self, outer):
                self._outer = outer

            def paginate(self, **kwargs):
                prefix = kwargs.get("Prefix", "")
                contents = [
                    {"Key": k}
                    for k in sorted(self._outer._objects)
                    if k.startswith(prefix) and (k.endswith(".netcdf") or k.endswith(".netcdf.gz"))
                ]
                return [{"Contents": contents}] if contents else [{}]

        return _Pag(self)


def test_stage01_thread_s3_client_and_get_s3(load_script, monkeypatch):
    s = load_script("01_download_myrorss.py")
    created = []

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            created.append((args, kwargs))
            return object()

    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3)
    c1 = s.get_s3_client()
    c2 = s._thread_s3_client()
    c3 = s._thread_s3_client()
    assert c1 is not None
    assert c2 is c3
    assert len(created) >= 1


def test_stage01_list_mesh_keys_for_convective_day(load_script):
    s = load_script("01_download_myrorss.py")
    day = date(2000, 1, 2)
    keys_a = ["2000/01/02/MESH/00.25/MESH_20000102-130000.netcdf"]
    keys_b = ["2000/01/03/MESH/00.25/MESH_20000103-110000.netcdf.gz"]
    s3 = _FakeS3({k: b"x" for k in keys_a + keys_b})
    out = s.list_mesh_keys_for_convective_day(s3, day)
    assert len(out) == 2
    assert any("130000" in k for k in out)
    assert any("110000" in k for k in out)


def test_stage01_sparse_updates_empty_mask(load_script):
    s = load_script("01_download_myrorss.py")
    # Outside CONUS
    nc = _minimal_myrorss_nc(
        np.array([0], dtype=np.int16),
        np.array([0], dtype=np.int16),
        np.array([50.0], dtype=np.float32),
    )
    r, c, v, n = s.sparse_updates_from_netcdf_bytes(nc)
    assert n == 0
    assert len(r) == 0
    daily = np.zeros((4, 4), dtype=np.float32)
    assert s.parse_sparse_mesh(nc, daily) == 0


def test_stage01_fetch_decode_sparse_success_and_error(load_script, monkeypatch):
    s = load_script("01_download_myrorss.py")
    px = np.array([s.CONUS_ROW_START + 1], dtype=np.int16)
    py = np.array([s.CONUS_COL_START + 1], dtype=np.int16)
    nc = _minimal_myrorss_nc(px, py, np.array([40.0], dtype=np.float32))
    gz = gzip.compress(nc)

    def fake_client():
        return _FakeS3({"k.netcdf": nc, "k.netcdf.gz": gz})

    monkeypatch.setattr(s, "_thread_s3_client", fake_client)
    key, r, c, v, n, err = s._fetch_decode_sparse("k.netcdf")
    assert err is None and n == 1
    key2, r2, c2, v2, n2, err2 = s._fetch_decode_sparse("k.netcdf.gz")
    assert err2 is None and n2 == 1

    monkeypatch.setattr(s, "_thread_s3_client", lambda: _FakeS3())
    _, _, _, _, n3, err3 = s._fetch_decode_sparse("missing")
    assert n3 == 0 and err3 is not None


def test_stage01_manifest_and_tif_helpers(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)

    good = tmp_path / "1999" / "mesh_19990401.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good)
    bad = tmp_path / "mesh_notadate.tif"
    bad.write_bytes(b"x")
    out_of_range = tmp_path / "2015" / "mesh_20150101.tif"
    out_of_range.parent.mkdir(parents=True)
    out_of_range.write_bytes(b"x")

    tifs = s.iter_stage01_tifs()
    assert good in tifs
    assert bad not in tifs
    assert out_of_range not in tifs

    row = s.manifest_row(
        date(1999, 4, 1), good, ["a.netcdf", "b.netcdf.gz"],
        10, 5, 12.0, "ok",
    )
    s.upsert_manifest_row(row)
    s.write_manifest_rows({row["date"]: row})
    rows = s.read_manifest_rows_by_date()
    assert rows["1999-04-01"]["status"] == "ok"
    active, peak = s.summarize_output_raster(good)
    assert active == 0 and peak == 0.0


def test_stage01_process_day_branches(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "CONUS_NROWS", 50)
    monkeypatch.setattr(s, "CONUS_NCOLS", 60)
    monkeypatch.setattr(s, "OUT_NROWS", 10)
    monkeypatch.setattr(s, "OUT_NCOLS", 12)
    day = date(2000, 6, 15)

    s3 = _FakeS3()
    assert s.process_day(s3, day, dry_run=True)["dry_run"] is True

    out_path = tmp_path / "2000" / "mesh_20000615.tif"
    out_path.parent.mkdir(parents=True)
    data = np.zeros((10, 12), dtype=np.float32)
    data[2, 3] = 25.0
    write_geotiff(data, out_path)
    monkeypatch.setattr(
        s, "list_mesh_keys_for_convective_day", lambda _s3, _d: ["k.netcdf"]
    )
    monkeypatch.setattr(s, "summarize_output_raster", lambda _p: (1, 25.0))
    skipped = s.process_day(s3, day, workers=1)
    assert skipped["skipped"] is True
    assert skipped["active_cells"] == 1

    out_path.unlink()
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: [])
    no_keys = s.process_day(_FakeS3(), day, workers=1)
    assert no_keys["files"] == 0 and no_keys["status"] == "missing_source"

    px = np.array([s.CONUS_ROW_START + 5], dtype=np.int16)
    py = np.array([s.CONUS_COL_START + 6], dtype=np.int16)
    nc = _minimal_myrorss_nc(px, py, np.array([301.0], dtype=np.float32))
    s3_obj = _FakeS3({"k.netcdf": nc})
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: ["k.netcdf"])
    seq = s.process_day(s3_obj, day, workers=1)
    assert seq["files"] == 1
    assert out_path.exists()

    out_path.unlink()
    def boom(*_a, **_k):
        raise RuntimeError("read fail")

    monkeypatch.setattr(s, "parse_sparse_mesh", boom)
    err_day = s.process_day(s3_obj, day, workers=1)
    assert err_day.get("errors", 0) == 1


def test_stage01_validate_outputs_paths(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path / "missing")
    assert s.validate_outputs() is False

    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "iter_stage01_tifs", lambda: [tmp_path / "mesh_19990401.tif"])
    assert s.validate_outputs() is False

    good = tmp_path / "1999" / "mesh_19990401.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good)
    monkeypatch.setattr(s, "iter_stage01_tifs", lambda: [good] * 4001)

    bad_crs = tmp_path / "1999" / "mesh_19990402.tif"
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), bad_crs)
    real_meta = rasterio.open(good).meta.copy()
    with rasterio.open(bad_crs, "w", **real_meta) as dst:
        dst.crs = "EPSG:3857"
        dst.write(np.zeros((NROWS, NCOLS), dtype=np.float32), 1)

    bad_shape = tmp_path / "1999" / "mesh_19990403.tif"
    with rasterio.open(
        bad_shape, "w", driver="GTiff", height=10, width=10, count=1,
        dtype="float32", crs="EPSG:4326",
        transform=rasterio.transform.from_bounds(-125, 24, -66, 50, 10, 10),
    ) as dst:
        dst.write(np.zeros((10, 10), dtype=np.float32), 1)

    bad_dtype = tmp_path / "1999" / "mesh_19990404.tif"
    with rasterio.open(
        bad_dtype, "w", driver="GTiff", height=NROWS, width=NCOLS, count=1,
        dtype="float64", crs="EPSG:4326",
        transform=rasterio.transform.from_origin(s.OUT_LON_MIN, s.OUT_LAT_MAX, s.OUT_DX, s.OUT_DX),
    ) as dst:
        dst.write(np.zeros((NROWS, NCOLS), dtype=np.float64), 1)

    bad_vals = tmp_path / "1999" / "mesh_19990405.tif"
    arr = np.zeros((NROWS, NCOLS), dtype=np.float32)
    arr[0, 0] = 500.0
    write_geotiff(arr, bad_vals)

    unreadable = tmp_path / "1999" / "mesh_19990406.tif"
    unreadable.write_bytes(b"not-a-tiff")

    monkeypatch.setattr(
        s,
        "iter_stage01_tifs",
        lambda: [good, bad_crs, bad_shape, bad_dtype, bad_vals, unreadable] + [good] * 3995,
    )
    assert s.validate_outputs() is False

    monkeypatch.setattr(s, "iter_stage01_tifs", lambda: [good] * 4001)
    assert s.validate_outputs() is True


def test_stage01_rebuild_manifest_and_qa_repair(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)

    day = date(1999, 5, 1)
    tif = tmp_path / "1999" / "mesh_19990501.tif"
    tif.parent.mkdir(parents=True)
    arr = np.array([[np.inf, 350.0, 10.0]], dtype=np.float32)
    arr_full = np.zeros((NROWS, NCOLS), dtype=np.float32)
    arr_full[0, :3] = arr
    write_geotiff(arr_full, tif)

    s3 = _FakeS3()
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: ["k.netcdf"])
    n = s.rebuild_manifest_from_outputs(s3, day, day)
    assert n == 1

    monkeypatch.setattr(s, "iter_stage01_tifs", lambda: [tif, tmp_path / "mesh_badname.tif"])
    s.upsert_manifest_row(
        s.manifest_row(day, tif, ["k.netcdf"], 1, 1, 10.0, "ok", read_errors=0)
    )
    stats = s.qa_repair_existing_outputs()
    assert stats["files_repaired"] >= 1
    assert stats["files_with_nonfinite"] >= 1
    assert stats["files_above_cap"] >= 1

    s.upsert_manifest_row(
        {
            **s.manifest_row(day, tif, ["k.netcdf"], 1, 1, 10.0, "ok"),
            "source_files": "not-int",
            "read_errors": "bad",
        }
    )
    s.qa_repair_existing_outputs()


def test_stage01_main_cli_branches(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "get_s3_client", lambda: _FakeS3())
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(s, "qa_repair_existing_outputs", lambda: {"files_scanned": 0})

    with pytest.raises(SystemExit) as exc:
        s.main(["--validate"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--qa-only"])
    assert exc.value.code == 0

    monkeypatch.setattr(s, "rebuild_manifest_from_outputs", lambda *_a, **_k: 3)
    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--year", "2000", "--month", "6"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--year", "2000"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only"])
    assert exc.value.code == 0

    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: {"files": 2, "max_mesh_mm": 55.0, "dry_run": True},
    )
    s.main(["--dry-run", "--year", "2000", "--month", "1"])

    calls = {"n": 0}

    def proc(s3, day, dry_run=False, workers=8):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"skipped": True}
        if calls["n"] == 2:
            return {"files": 0, "max_mesh_mm": 0.0}
        if calls["n"] <= 102:
            return {"files": 1, "max_mesh_mm": 0.0}
        return {"files": 3, "max_mesh_mm": 60.0}

    monkeypatch.setattr(s, "process_day", proc)
    with pytest.raises(SystemExit) as exc:
        s.main(["--year", "2000", "--month", "1", "--workers", "1"])
    assert exc.value.code == 0
