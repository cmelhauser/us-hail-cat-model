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
