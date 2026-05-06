"""Unit tests for Stage 02 MRMS parallel timestep merging (no live S3)."""

from __future__ import annotations

from datetime import date

import numpy as np


def test_stage02_workers_cli_defaults(load_script):
    s = load_script("02_download_mrms_mesh.py")
    p = s.build_arg_parser()
    assert p.parse_args([]).workers == 8
    assert p.parse_args(["--workers", "1"]).workers == 1


def test_stage02_process_day_parallel_merge_matches_numpy_maximum(load_script, monkeypatch, tmp_path):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "CONUS_NROWS", 100)
    monkeypatch.setattr(s, "CONUS_NCOLS", 100)

    keys = ["ka", "kb", "kc"]
    arr_a = np.zeros((100, 100), dtype=np.float32)
    arr_a[12, 34] = 10.0
    arr_b = np.zeros((100, 100), dtype=np.float32)
    arr_b[12, 34] = 55.0
    arr_c = np.zeros((100, 100), dtype=np.float32)
    arr_c[77, 88] = 20.0
    pmap = {"ka": arr_a, "kb": arr_b, "kc": arr_c}

    def fake_fetch(key):
        arr = pmap[key]
        return key, arr, int(np.count_nonzero(arr)), None

    monkeypatch.setattr(s, "_fetch_and_decode_timestep", fake_fetch)
    monkeypatch.setattr(s, "list_mesh_keys", lambda _s3, _day: list(keys))

    written: list[np.ndarray] = []

    def fake_write(data, path):
        written.append(np.asarray(data, dtype=np.float32).copy())

    monkeypatch.setattr(s, "write_geotiff", fake_write)

    day = date(2022, 6, 1)
    out = s.process_day(None, day, dry_run=False, workers=4)
    assert out["files"] == 3
    assert out["errors"] == 0
    assert len(written) == 1

    daily_max = np.maximum(np.maximum(arr_a, arr_b), arr_c)
    agg = s.block_max(daily_max, s.AGG_FACTOR)
    expected, _ = s.sanitize_hail_values(
        agg, max_hail_mm=s.QA_MAX_HAIL_MM, nodata=s.OUT_NODATA
    )
    np.testing.assert_array_equal(written[0], expected)
    assert abs(out["max_mesh_mm"] - float(expected.max())) < 1e-3


def test_stage02_process_day_parallel_skips_failed_timesteps(load_script, monkeypatch, tmp_path):
    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "CONUS_NROWS", 100)
    monkeypatch.setattr(s, "CONUS_NCOLS", 100)

    keys = ["ka", "kb"]
    arr_a = np.zeros((100, 100), dtype=np.float32)
    arr_a[5, 5] = 33.0

    def fake_fetch(key):
        if key == "kb":
            return key, None, 0, RuntimeError("simulated read failure")
        return key, arr_a, int(np.count_nonzero(arr_a)), None

    monkeypatch.setattr(s, "_fetch_and_decode_timestep", fake_fetch)
    monkeypatch.setattr(s, "list_mesh_keys", lambda _s3, _day: list(keys))

    written: list[np.ndarray] = []

    def fake_write(data, path):
        written.append(np.asarray(data, dtype=np.float32).copy())

    monkeypatch.setattr(s, "write_geotiff", fake_write)

    day = date(2022, 6, 2)
    out = s.process_day(None, day, dry_run=False, workers=4)
    assert out["files"] == 2
    assert out["errors"] == 1
    assert len(written) == 1

    agg = s.block_max(arr_a, s.AGG_FACTOR)
    expected, _ = s.sanitize_hail_values(
        agg, max_hail_mm=s.QA_MAX_HAIL_MM, nodata=s.OUT_NODATA
    )
    np.testing.assert_array_equal(written[0], expected)
