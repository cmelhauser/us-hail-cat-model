import numpy as np
import pandas as pd
from conftest import dense_footprint_to_cells, load_stage


def _dense_to_cells(fp: np.ndarray, peak: np.ndarray) -> dict:
    return dense_footprint_to_cells(fp, peak)


def _write_event_outputs(path, csv_ids, npz_ids, *, omit_key=None):
    path.mkdir(exist_ok=True)
    pd.DataFrame(
        {
            "event_id": csv_ids,
            "peak_hail_mm": np.full(len(csv_ids), 40.0),
            "duration_days": np.ones(len(csv_ids), dtype=int),
        }
    ).to_csv(path / "event_catalog.csv", index=False)
    arrays = {
        "n_events": np.array([len(npz_ids)]),
        "event_ids": np.asarray(npz_ids, dtype=np.int32),
    }
    for eid in npz_ids:
        for prefix, value in (
            ("rows", np.array([1], dtype=np.int16)),
            ("cols", np.array([2], dtype=np.int16)),
            ("vals", np.array([40.0], dtype=np.float32)),
        ):
            key = f"{prefix}_{eid}"
            if key != omit_key:
                arrays[key] = value
    np.savez(path / "event_peaks.npz", **arrays)


def test_stage08_group_events_rejects_large_centroid_jump(monkeypatch):
    from datetime import date
    s = load_stage("08_build_event_catalog.py")
    monkeypatch.setattr(s, "BUFFER_CELLS", 20)
    fp1 = np.zeros((50, 50), dtype=bool); fp1[1, 1] = True
    fp2 = np.zeros((50, 50), dtype=bool); fp2[45, 45] = True
    dates = [date(2020, 5, 1), date(2020, 5, 2)]
    cells = [
        _dense_to_cells(fp1, fp1.astype(float) * 30),
        _dense_to_cells(fp2, fp2.astype(float) * 30),
    ]
    groups = s.group_events(dates, cells)
    assert groups == [[0], [1]]


def test_stage08_sparse_overlap_matches_dense_integral_image():
    s = load_stage("08_build_event_catalog.py")
    rng = np.random.default_rng(42)
    for _ in range(20):
        fp1 = rng.random((80, 80)) > 0.97
        fp2 = rng.random((80, 80)) > 0.97
        r1, c1 = np.where(fp1)
        r2, c2 = np.where(fp2)
        sparse = s.footprints_overlap_sparse(r1, c1, r2, c2, buffer=5)
        dense = s.footprints_overlap(fp1, fp2)
        assert sparse == dense


def test_stage08_sparse_catalog_contains_active_cells():
    from datetime import date
    s = load_stage("08_build_event_catalog.py")
    fp = np.zeros((s.NROWS, s.NCOLS), dtype=bool); fp[10, 10] = True
    peak = np.zeros((s.NROWS, s.NCOLS), dtype=np.float32); peak[10, 10] = 40.0
    cells = [_dense_to_cells(fp, peak)]
    df, sparse = s.build_catalog([date(2020, 5, 1)], cells, [[0]])
    assert len(df) == 1
    assert sparse[0]["vals"].tolist() == [40.0]


def test_stage08_merge_event_peak_empty_group():
    s = load_stage("08_build_event_catalog.py")
    empty = {"rows": np.empty(0, dtype=np.int16), "cols": np.empty(0, dtype=np.int16), "vals": np.empty(0, dtype=np.float32)}
    rows, cols, vals = s.merge_event_peak([0], [empty])
    assert rows.size == cols.size == vals.size == 0


def test_stage08_footprint_centroid_sparse_empty():
    s = load_stage("08_build_event_catalog.py")
    lat, lon = s.footprint_centroid_sparse(
        np.empty(0, dtype=np.int16),
        np.empty(0, dtype=np.int16),
    )
    assert np.isnan(lat) and np.isnan(lon)


def test_stage08_validation_rejects_csv_npz_event_id_mismatch(
    tmp_path, monkeypatch
):
    s = load_stage("08_build_event_catalog.py")
    _write_event_outputs(tmp_path, [*range(99), 100], list(range(100)))
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    assert s.validate_outputs() is False


def test_stage08_validation_rejects_missing_per_event_npz_key(
    tmp_path, monkeypatch
):
    s = load_stage("08_build_event_catalog.py")
    ids = list(range(100))
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    _write_event_outputs(tmp_path, ids, ids)
    assert s.validate_outputs() is True

    _write_event_outputs(tmp_path, ids, ids, omit_key="vals_99")
    assert s.validate_outputs() is False


def _write_corrected_mesh(path, value: float = 40.0, *, nrows: int = 8, ncols: int = 8) -> None:
    import rasterio
    from rasterio.transform import from_origin

    data = np.zeros((nrows, ncols), dtype=np.float32)
    data[2, 2] = value
    profile = {
        "driver": "GTiff",
        "height": nrows,
        "width": ncols,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-100, 40, 0.05, 0.05),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def test_stage08_load_daily_data_and_grouping_branches(load_script, tmp_path, monkeypatch):
    from datetime import date, timedelta

    s = load_script("08_build_event_catalog.py")
    in_dir = tmp_path / "mesh"
    in_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)

    for i in range(7):
        d = date(2020, 5, 1) + timedelta(days=i)
        _write_corrected_mesh(in_dir / f"mesh_{d.strftime('%Y%m%d')}.tif")

    dates, cells = s.load_daily_data()
    assert len(dates) == 7
    assert all(c["vals"].size == 1 for c in cells)

    groups = s.group_events(dates, cells)
    assert len(groups) >= 2

    r1 = np.repeat(np.arange(3000, dtype=np.int16), 1)
    c1 = np.zeros(3000, dtype=np.int16)
    r2 = np.zeros(3000, dtype=np.int16)
    c2 = np.zeros(3000, dtype=np.int16)
    assert s.footprints_overlap_sparse(r1, c1, r2, c2, buffer=5) is True

    lat, lon = s.footprint_centroid_sparse(
        np.array([1, 2], dtype=np.int16),
        np.array([1, 2], dtype=np.int16),
        np.array([30.0, 50.0], dtype=np.float32),
    )
    assert np.isfinite(lat) and np.isfinite(lon)


def test_stage08_build_catalog_save_and_summary(load_script):
    from datetime import date

    s = load_script("08_build_event_catalog.py")
    fp = np.zeros((20, 20), dtype=bool)
    fp[5, 5] = True
    fp[5, 6] = True
    peak = fp.astype(np.float32) * 35.0
    cells = [
        _dense_to_cells(fp, peak),
        _dense_to_cells(fp, peak + 5),
    ]
    dates = [date(2020, 6, 1), date(2020, 6, 2)]
    df, sparse = s.build_catalog(dates, cells, [[0, 1]])
    assert len(df) == 1
    assert df.iloc[0]["merge_quality_flag"] == "ok"
    s.print_summary(df)
    assert 0 in sparse


def test_stage08_validate_outputs_error_branches(load_script, tmp_path, monkeypatch):
    import pandas as pd

    s = load_script("08_build_event_catalog.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)

    assert s.validate_outputs() is False

    (tmp_path / "event_catalog.csv").write_text("")
    assert s.validate_outputs() is False

    pd.DataFrame({"event_id": [0], "peak_hail_mm": [40.0]}).to_csv(
        tmp_path / "event_catalog.csv", index=False
    )
    assert s.validate_outputs() is False

    ids = list(range(100))
    _write_event_outputs(tmp_path, ids, ids)
    assert s.validate_outputs() is True

    bad = pd.DataFrame(
        {
            "event_id": ids,
            "peak_hail_mm": [40.0] * 99 + [350.0],
            "duration_days": [1] * 100,
        }
    )
    bad.to_csv(tmp_path / "event_catalog.csv", index=False)
    assert s.validate_outputs() is False


def test_stage08_main_end_to_end(load_script, tmp_path, monkeypatch):
    import sys
    from datetime import date, timedelta

    import pytest

    s = load_script("08_build_event_catalog.py")
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)
    monkeypatch.setattr(s, "OUT_DIR", out_dir)

    start = date(2019, 5, 1)
    for i in range(100):
        d = start + timedelta(days=i * 3)
        _write_corrected_mesh(in_dir / f"mesh_{d.strftime('%Y%m%d')}.tif", value=35.0 + (i % 5))

    monkeypatch.setattr(sys, "argv", ["08_build_event_catalog.py"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0
    assert (out_dir / "event_catalog.csv").exists()
    assert (out_dir / "event_peaks.npz").exists()

    monkeypatch.setattr(sys, "argv", ["08_build_event_catalog.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


def test_stage08_remaining_validation_branches(load_script, tmp_path, monkeypatch):
    import pandas as pd

    s = load_script("08_build_event_catalog.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)

    assert s.group_events([], []) == []
    assert s.footprints_overlap_sparse(
        np.empty(0, dtype=np.int16),
        np.empty(0, dtype=np.int16),
        np.array([1], dtype=np.int16),
        np.array([1], dtype=np.int16),
    ) is False

    lat, lon = s.footprint_centroid_sparse(
        np.array([1], dtype=np.int16),
        np.array([1], dtype=np.int16),
        np.array([0.0], dtype=np.float32),
    )
    assert np.isfinite(lat)

    ids = list(range(100))
    _write_event_outputs(tmp_path, ids, ids)
    (tmp_path / "event_catalog.csv").write_text(
        (tmp_path / "event_catalog.csv").read_text().replace("0,", "bad,", 1)
    )
    assert s.validate_outputs() is False

    _write_event_outputs(tmp_path, ids, ids)
    df = pd.read_csv(tmp_path / "event_catalog.csv")
    df.loc[0, "duration_days"] = 99
    df.to_csv(tmp_path / "event_catalog.csv", index=False)
    assert s.validate_outputs() is False

    _write_event_outputs(tmp_path, ids, ids)
    df = pd.read_csv(tmp_path / "event_catalog.csv")
    df.loc[0, "event_id"] = 0
    df.loc[1, "event_id"] = 0
    df.to_csv(tmp_path / "event_catalog.csv", index=False)
    assert s.validate_outputs() is False

    _write_event_outputs(tmp_path, ids, ids)
    with open(tmp_path / "event_peaks.npz", "rb") as handle:
        raw = np.load(handle)
        arrays = {k: raw[k] for k in raw.files}
    arrays["n_events"] = np.array([99])
    np.savez(tmp_path / "event_peaks.npz", **arrays)
    assert s.validate_outputs() is False
