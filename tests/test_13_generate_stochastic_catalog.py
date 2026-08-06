import numpy as np
import pandas as pd
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


def test_stage13_should_stream_events_thresholds():
    s = load_stage("13_generate_stochastic_catalog.py")
    assert s._should_stream_events(999, 10.0, None) is False
    assert s._should_stream_events(1000, 1.0, s.OUT_DIR / "catalog.parquet") is True
    assert s._should_stream_events(100, 600.0, s.OUT_DIR / "catalog.parquet") is True
    assert s._should_stream_events(100, 10.0, s.OUT_DIR / "catalog.parquet") is False


def test_stage13_stochastic_event_writer_batches(tmp_path):
    s = load_stage("13_generate_stochastic_catalog.py")
    path = tmp_path / "events.parquet"
    writer = s.StochasticEventWriter(path, batch_size=2)
    for i in range(5):
        writer.append({"sim_year": 0, "event_idx": i, "peak_hail_mm": float(i)})
    writer.close()
    assert writer.total == 5
    assert path.exists()
    df = pd.read_parquet(path)
    assert len(df) == 5


def test_stage13_compute_empirical_rps_chunked():
    s = load_stage("13_generate_stochastic_catalog.py")
    n_years, n_active = 20, 8
    ann_max = np.tile(np.arange(1, n_years + 1, dtype=np.float32)[:, None], (1, n_active))
    active_rows = np.array([10, 10, 11, 11, 12, 12, 13, 13], dtype=np.int32)
    active_cols = np.array([20, 21, 20, 21, 20, 21, 20, 21], dtype=np.int32)
    rp_maps = s.compute_empirical_rps(ann_max, active_rows, active_cols, n_years, chunk_size=3)
    assert 10 in rp_maps
    assert rp_maps[10][10, 20] > 0


def test_stage13_validation_requires_streamed_event_parquet(
    tmp_path, monkeypatch
):
    import pandas as pd

    s = load_stage("13_generate_stochastic_catalog.py")
    cat_dir = tmp_path / "catalog"
    map_dir = tmp_path / "maps"
    pet_dir = tmp_path / "pet"
    cat_dir.mkdir()
    map_dir.mkdir()
    pet_dir.mkdir()
    monkeypatch.setattr(s, "CAT_DIR", cat_dir)
    monkeypatch.setattr(s, "MAP_DIR", map_dir)
    monkeypatch.setattr(s, "PET_DIR", pet_dir)
    monkeypatch.setattr(s, "RP_YEARS", [10])
    (map_dir / "rp_00010yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()

    assert s.validate_outputs() is False
    empty = cat_dir / "stochastic_event_summary.parquet"
    empty.touch()
    assert s.validate_outputs() is False
    pd.DataFrame(
        {
            "sim_year": [1],
            "event_idx": [0],
            "peak_hail_mm": [40.0],
        }
    ).to_parquet(cat_dir / "stochastic_event_summary.parquet", index=False)
    assert s.validate_outputs() is True

