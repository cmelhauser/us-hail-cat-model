import numpy as np
from conftest import load_stage


def test_stage13_sparse_event_active_mask_unique_cells():
    s = load_stage("13_generate_stochastic_catalog.py")
    events = [
        {"rows": np.array([1, 1]), "cols": np.array([2, 2]), "vals": np.array([30, 40], dtype=np.float32)},
        {"rows": np.array([2]), "cols": np.array([3]), "vals": np.array([50], dtype=np.float32)},
    ]
    rows, cols = s.sparse_event_active_mask(events)
    assert len(rows) == 2
    assert set(zip(rows.tolist(), cols.tolist())) == {(1, 2), (2, 3)}


def test_stage13_update_sparse_annual_max():
    s = load_stage("13_generate_stochastic_catalog.py")
    ann = np.zeros(2, dtype=np.float32)
    lookup = {1 * s.NCOLS + 2: 0, 2 * s.NCOLS + 3: 1}
    s.update_sparse_annual_max(ann, lookup, np.array([1, 2]), np.array([2, 3]), np.array([30.0, 50.0], dtype=np.float32))
    assert ann.tolist() == [30.0, 50.0]


def test_stage13_ann_max_uses_memmap_when_large(tmp_path, monkeypatch):
    s = load_stage("13_generate_stochastic_catalog.py")
    monkeypatch.setattr(s, "ANN_MAX_INMEM_BYTES", 100)
    ann_max, mmap_path = s._open_ann_max_store(50, 200, tmp_path)
    assert mmap_path is not None
    assert mmap_path.exists()
    assert ann_max.shape == (50, 200)
    ann_max[0, 0] = 42.0
    ann_max.flush()
    assert float(np.memmap(mmap_path, dtype=np.float32, mode="r", shape=(50, 200))[0, 0]) == 42.0
