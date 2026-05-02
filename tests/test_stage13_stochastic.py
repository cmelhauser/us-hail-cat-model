
def test_sparse_translation_clips_domain(load_script):
    import numpy as np
    s = load_script("13_generate_stochastic_catalog.py")
    rng = np.random.default_rng(1)
    rows = np.array([0, s.NROWS - 1], dtype=np.int32)
    cols = np.array([0, s.NCOLS - 1], dtype=np.int32)
    rr, cc, keep, dr, dc = s.translate_sparse(rows, cols, rng, sigma_cells=10)
    assert np.all((rr >= 0) & (rr < s.NROWS))
    assert np.all((cc >= 0) & (cc < s.NCOLS))


def test_sparse_active_index_and_update(load_script):
    import numpy as np
    s = load_script("13_generate_stochastic_catalog.py")
    events = [
        {"event_id": 0, "rows": np.array([10], dtype=np.int32), "cols": np.array([20], dtype=np.int32), "vals": np.array([40.0], dtype=np.float32)},
        {"event_id": 1, "rows": np.array([11], dtype=np.int32), "cols": np.array([21], dtype=np.int32), "vals": np.array([60.0], dtype=np.float32)},
    ]
    ar, ac, lookup = s.build_active_index(events)
    row = np.zeros(len(ar), dtype=np.float32)
    n_cells, peak = s.update_sparse_max(row, events[0]["rows"], events[0]["cols"], events[0]["vals"], lookup)
    assert n_cells == 1
    assert peak == 40.0
    assert row.max() == 40.0
