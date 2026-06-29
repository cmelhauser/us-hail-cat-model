import numpy as np
from conftest import load_stage


def _dense_to_cells(fp: np.ndarray, peak: np.ndarray) -> dict:
    rows, cols = np.where(fp)
    return {
        "rows": rows.astype(np.int16),
        "cols": cols.astype(np.int16),
        "vals": peak[rows, cols].astype(np.float32),
    }


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
