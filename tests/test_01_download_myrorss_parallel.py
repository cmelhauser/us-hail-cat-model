from __future__ import annotations

from datetime import date

import numpy as np


def test_stage01_workers_flag_default(load_script):
    s = load_script("01_download_myrorss.py")
    p = s.build_arg_parser()
    assert p.parse_args([]).workers == 8
    assert p.parse_args(["--workers", "1"]).workers == 1


def test_stage01_process_day_parallel_merge_matches_numpy(load_script, monkeypatch, tmp_path):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "CONUS_NROWS", 50)
    monkeypatch.setattr(s, "CONUS_NCOLS", 60)

    keys = ["ka", "kb", "kc"]

    # Provide sparse updates per key (CONUS coords).
    def fake_fetch(key):
        if key == "ka":
            r = np.array([1, 2], dtype=np.int32)
            c = np.array([3, 4], dtype=np.int32)
            v = np.array([10.0, 5.0], dtype=np.float32)
            return key, r, c, v, 2, None
        if key == "kb":
            r = np.array([1], dtype=np.int32)
            c = np.array([3], dtype=np.int32)
            v = np.array([55.0], dtype=np.float32)  # overwrites ka at (1,3)
            return key, r, c, v, 1, None
        r = np.array([10], dtype=np.int32)
        c = np.array([11], dtype=np.int32)
        v = np.array([22.0], dtype=np.float32)
        return key, r, c, v, 1, None

    monkeypatch.setattr(s, "_fetch_decode_sparse", fake_fetch)
    monkeypatch.setattr(s, "list_mesh_keys", lambda _s3, _day: list(keys))

    written: list[np.ndarray] = []

    def fake_write(data, path):
        written.append(np.asarray(data, dtype=np.float32).copy())

    monkeypatch.setattr(s, "write_geotiff", fake_write)
    monkeypatch.setattr(s, "summarize_output_raster", lambda _p: (0, 0.0))
    monkeypatch.setattr(s, "upsert_manifest_row", lambda _row: None)

    # Run
    out = s.process_day(None, date(2000, 1, 2), dry_run=False, workers=4)
    assert out["files"] == 3
    assert out["errors"] == 0
    assert out["pixels"] == 4
    assert len(written) == 1

    # Expected: build daily_max manually then block-max.
    daily_max = np.zeros((50, 60), dtype=np.float32)
    np.maximum.at(daily_max, (np.array([1, 2]), np.array([3, 4])), np.array([10.0, 5.0], dtype=np.float32))
    np.maximum.at(daily_max, (np.array([1]), np.array([3])), np.array([55.0], dtype=np.float32))
    np.maximum.at(daily_max, (np.array([10]), np.array([11])), np.array([22.0], dtype=np.float32))

    expected, _ = s.sanitize_mesh_array(s.block_max(daily_max, s.AGG_FACTOR))
    np.testing.assert_array_equal(written[0], expected)

