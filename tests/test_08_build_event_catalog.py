import numpy as np
from conftest import load_stage


def test_stage08_group_events_rejects_large_centroid_jump(monkeypatch):
    from datetime import date
    s = load_stage("08_build_event_catalog.py")
    monkeypatch.setattr(s, "BUFFER_CELLS", 20)
    fp1 = np.zeros((50, 50), dtype=bool); fp1[1, 1] = True
    fp2 = np.zeros((50, 50), dtype=bool); fp2[45, 45] = True
    dates = [date(2020, 5, 1), date(2020, 5, 2)]
    groups = s.group_events(dates, [fp1, fp2], [fp1.astype(float)*30, fp2.astype(float)*30])
    assert groups == [[0], [1]]


def test_stage08_sparse_catalog_contains_active_cells():
    from datetime import date
    s = load_stage("08_build_event_catalog.py")
    fp = np.zeros((s.NROWS, s.NCOLS), dtype=bool); fp[10, 10] = True
    peak = np.zeros((s.NROWS, s.NCOLS), dtype=np.float32); peak[10, 10] = 40.0
    df, sparse = s.build_catalog([date(2020, 5, 1)], [fp], [peak], [[0]])
    assert len(df) == 1
    assert sparse[0]["vals"].tolist() == [40.0]
