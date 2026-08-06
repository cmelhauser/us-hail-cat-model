"""Coverage tests for Stage 02 — mocked S3/GRIB, CLI, validation."""

from __future__ import annotations

import gzip
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio

from scripts._config import NCOLS, NROWS
from scripts._io import write_geotiff


class _FakeS3Body:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload


class _FakeS3:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self._objects = objects or {}

    def get_object(self, *, Bucket, Key):
        return {"Body": _FakeS3Body(self._objects[Key])}

    def get_paginator(self, name):
        class _Pag:
            def __init__(self, outer):
                self._outer = outer

            def paginate(self, **kwargs):
                prefix = kwargs.get("Prefix", "")
                contents = [
                    {"Key": k}
                    for k in sorted(self._outer._objects)
                    if k.startswith(prefix) and k.endswith(".grib2.gz")
                ]
                return [{"Contents": contents}] if contents else [{}]

        return _Pag(self)


def test_stage02_thread_s3_and_list_keys(load_script, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            return object()

    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3)
    assert s.get_s3_client() is not None
    assert s._thread_s3_client() is s._thread_s3_client()

    s3 = _FakeS3(
        {
            "CONUS/MESH_00.50/20200601/MRMS_MESH_00.50_20200601-130000.grib2.gz": b"x",
            "CONUS/MESH_00.50/20200602/MRMS_MESH_00.50_20200602-110000.grib2.gz": b"y",
        }
    )
    keys = s.list_mesh_keys_for_convective_day(s3, date(2020, 6, 1))
    assert len(keys) == 2


def test_stage02_timestep_and_parse_grib(load_script, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")
    conus = np.zeros((s.CONUS_NROWS, s.CONUS_NCOLS), dtype=np.float32)
    conus[10, 20] = 45.0

    monkeypatch.setattr(
        s,
        "timestep_conus_mesh_from_grib_bytes",
        lambda _b: (conus.copy(), 1),
    )
    daily = np.zeros_like(conus)
    assert s.parse_grib2_mesh(b"fake", daily) == 1
    assert daily[10, 20] == 45.0

    def fake_fetch(key):
        if key == "bad":
            return key, None, 0, RuntimeError("fail")
        return key, conus, 1, None

    monkeypatch.setattr(s, "_thread_s3_client", lambda: _FakeS3({"ok.grib2.gz": b""}))
    monkeypatch.setattr(s, "timestep_conus_mesh_from_grib_bytes", lambda _b: (conus, 1))
    k, arr, n, err = s._fetch_and_decode_timestep("ok.grib2.gz")
    assert err is None and n == 1
    _, _, n2, err2 = s._fetch_and_decode_timestep("bad.grib2.gz")
    assert err2 is not None


def test_stage02_summarize_mrms_key_formats(load_script):
    s = load_script("02_download_mrms_mesh.py")
    plain, gz = s.summarize_mrms_key_formats(["a.grib2", "b.grib2.gz"])
    assert plain == 1 and gz == 1


def test_stage02_process_day_branches(load_script, tmp_path, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "CONUS_NROWS", 100)
    monkeypatch.setattr(s, "CONUS_NCOLS", 100)
    monkeypatch.setattr(s, "OUT_NROWS", 20)
    monkeypatch.setattr(s, "OUT_NCOLS", 20)
    day = date(2020, 10, 15)

    s3 = _FakeS3()
    assert s.process_day(s3, day, dry_run=True)["dry_run"] is True

    out_path = tmp_path / "2020" / "mesh_20201015.tif"
    out_path.parent.mkdir(parents=True)
    write_geotiff(np.zeros((20, 20), dtype=np.float32), out_path)
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: ["k.grib2.gz"])
    assert s.process_day(s3, day, workers=1)["skipped"] is True

    out_path.unlink()
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: [])
    no_keys = s.process_day(_FakeS3(), day, workers=1)
    assert no_keys["files"] == 0

    conus = np.zeros((100, 100), dtype=np.float32)
    conus[5, 5] = 301.0
    gz_payload = gzip.compress(b"grib")

    def seq_get(*_a, **_k):
        return {"Body": _FakeS3Body(gz_payload)}

    s3_seq = _FakeS3({"k.grib2.gz": gz_payload})
    s3_seq.get_object = seq_get  # type: ignore[method-assign]
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: ["k.grib2.gz"])
    monkeypatch.setattr(s, "parse_grib2_mesh", lambda _b, dm: int(np.count_nonzero(dm)))
    monkeypatch.setattr(
        s,
        "timestep_conus_mesh_from_grib_bytes",
        lambda _b: (conus, 1),
    )

    def parse_merge(grib_bytes, daily_max):
        c, n = s.timestep_conus_mesh_from_grib_bytes(grib_bytes)
        np.maximum(daily_max, c, out=daily_max)
        return n

    monkeypatch.setattr(s, "parse_grib2_mesh", parse_merge)
    res = s.process_day(s3_seq, day, workers=1)
    assert res["files"] == 1
    assert out_path.exists()

    out_path.unlink()
    def boom(*_a, **_k):
        raise RuntimeError("grib fail")

    monkeypatch.setattr(s, "parse_grib2_mesh", boom)
    err_res = s.process_day(s3_seq, day, workers=1)
    assert err_res.get("errors", 0) == 1


def test_stage02_rebuild_manifest_and_validate(load_script, tmp_path, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)

    assert s.validate_outputs() is False

    good = tmp_path / "2020" / "mesh_20201015.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good)
    monkeypatch.setattr(
        s,
        "iter_dates",
        lambda start, end: [date(2020, 10, 15)],
    )

    s3 = _FakeS3()
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda _s3, _d: [])
    n = s.rebuild_manifest_from_outputs(s3, date(2020, 10, 15), date(2020, 10, 15))
    assert n == 1

    bad = tmp_path / "2020" / "mesh_20201016.tif"
    arr = np.zeros((NROWS, NCOLS), dtype=np.float32)
    arr[0, 0] = 400.0
    write_geotiff(arr, bad)
    tifs = sorted(p for p in tmp_path.rglob("mesh_????????.tif") if p.stem >= "mesh_20201014")
    assert len(tifs) >= 2
    monkeypatch.setattr(
        s,
        "OUT_DIR",
        tmp_path,
    )
    # Too few files
    assert s.validate_outputs() is False

    # Patch rglob count by creating many good files listing
    many = [good] * 1001
    orig_rglob = Path.rglob

    def fake_rglob(self, pattern):
        if pattern == "mesh_????????.tif" and self == tmp_path:
            return iter(many)
        return orig_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    assert s.validate_outputs() is True


def test_stage02_main_cli_branches(load_script, tmp_path, monkeypatch):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "get_s3_client", lambda: _FakeS3())
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(s, "rebuild_manifest_from_outputs", lambda *_a, **_k: 2)

    with pytest.raises(SystemExit) as exc:
        s.main(["--validate"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--year", "2021", "--month", "7"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--year", "2021"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only"])
    assert exc.value.code == 0

    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: {"files": 1, "max_mesh_mm": 60.0},
    )
    with pytest.raises(SystemExit) as exc:
        s.main(["--year", "2020", "--month", "10", "--workers", "1"])
    assert exc.value.code == 0

    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: {"files": 0, "dry_run": True},
    )
    s.main(["--dry-run", "--year", "2020", "--month", "10"])
