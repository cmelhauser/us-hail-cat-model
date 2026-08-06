import json

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


def _full_catalog_row(sim_year: int) -> dict:
    return {
        "sim_year": sim_year,
        "event_idx": 0,
        "template_id": 1,
        "doy": 150,
        "scale_factor": 1.0,
        "peak_hail_mm": 40.0,
        "n_cells": 3,
    }


def test_stage13_production_validation_rejects_smoke_and_accepts_full(
    tmp_path, monkeypatch
):
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
    monkeypatch.setattr(s, "CATALOG_MANIFEST", cat_dir / "stochastic_catalog_manifest.json")
    monkeypatch.setattr(s, "RP_YEARS", [10])
    (map_dir / "rp_00010yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()

    # Missing manifest / empty catalog fail.
    assert s.validate_outputs() is False

    # One-row catalog with fake production manifest still fails year coverage.
    pd.DataFrame([_full_catalog_row(0)]).to_parquet(
        cat_dir / "stochastic_event_summary.parquet", index=False
    )
    s.write_catalog_manifest(
        n_years=s.N_SIM_YEARS,
        seed=s.RNG_SEED,
        model_version=s.MODEL_VERSION,
        status="complete",
        n_events=1,
    )
    assert s.validate_outputs() is False

    # Declared 1,000-year smoke metadata fails production n_years gate.
    s.write_catalog_manifest(
        n_years=1000,
        seed=s.RNG_SEED,
        model_version=s.MODEL_VERSION,
        status="complete",
        n_events=2,
    )
    pd.DataFrame([_full_catalog_row(0), _full_catalog_row(999)]).to_parquet(
        cat_dir / "stochastic_event_summary.parquet", index=False
    )
    assert s.validate_outputs() is False

    # Declared full catalog with near-end year coverage passes.
    s.write_catalog_manifest(
        n_years=s.N_SIM_YEARS,
        seed=s.RNG_SEED,
        model_version=s.MODEL_VERSION,
        status="complete",
        n_events=2,
    )
    pd.DataFrame(
        [_full_catalog_row(0), _full_catalog_row(s.N_SIM_YEARS - 1)]
    ).to_parquet(cat_dir / "stochastic_event_summary.parquet", index=False)
    assert s.validate_outputs() is True
    manifest = json.loads(s.CATALOG_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["n_years"] == s.N_SIM_YEARS
    assert manifest["status"] == "complete"


def _seed_historical_events(event_dir, n_events: int = 5):
    import pandas as pd

    event_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    arrays = {"n_events": np.array([n_events]), "event_ids": np.arange(n_events, dtype=np.int32)}
    for eid in range(n_events):
        start = pd.Timestamp(f"2015-06-{eid + 1:02d}")
        rows.append(
            {
                "event_id": eid,
                "start_date": start,
                "end_date": start,
                "duration_days": 1,
                "peak_hail_mm": 40.0 + eid,
                "doy": int(start.dayofyear),
            }
        )
        arrays[f"rows_{eid}"] = np.array([10 + eid], dtype=np.int16)
        arrays[f"cols_{eid}"] = np.array([20], dtype=np.int16)
        arrays[f"vals_{eid}"] = np.array([40.0 + eid], dtype=np.float32)
    pd.DataFrame(rows).to_csv(event_dir / "event_catalog.csv", index=False)
    np.savez(event_dir / "event_peaks.npz", **arrays)


def _stage13_paths(monkeypatch, s, tmp_path):
    event_dir = tmp_path / "events"
    out_dir = tmp_path / "stoch"
    cat_dir = out_dir / "catalog"
    map_dir = out_dir / "maps"
    pet_dir = out_dir / "pet"
    mask_dir = tmp_path / "mask"
    for d in (cat_dir, map_dir, pet_dir, mask_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(s, "EVENT_DIR", event_dir)
    monkeypatch.setattr(s, "OUT_DIR", out_dir)
    monkeypatch.setattr(s, "CAT_DIR", cat_dir)
    monkeypatch.setattr(s, "MAP_DIR", map_dir)
    monkeypatch.setattr(s, "PET_DIR", pet_dir)
    monkeypatch.setattr(s, "MASK_DIR", mask_dir)
    monkeypatch.setattr(s, "CATALOG_MANIFEST", cat_dir / "stochastic_catalog_manifest.json")
    return event_dir, out_dir, cat_dir, map_dir, pet_dir, mask_dir


def test_stage13_load_calibrate_and_shape_perturb(load_script, tmp_path, monkeypatch):
    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, *_rest = _stage13_paths(monkeypatch, s, tmp_path)
    _seed_historical_events(event_dir, n_events=12)

    event_df, sparse_events = s.load_historical_events()
    assert len(sparse_events) == 12
    sigma = s.calibrate_sigma(event_df, sparse_events)
    assert 0.10 <= sigma <= 0.40
    cdf = s.build_doy_distribution(event_df)
    assert cdf.size == 366

    rng = np.random.default_rng(0)
    rows = np.array([1, 2], dtype=np.int32)
    cols = np.array([1, 2], dtype=np.int32)
    vals = np.array([40.0, 50.0], dtype=np.float32)
    r0, c0, v0, tag0 = s.sparse_shape_perturb(rows, cols, vals, rng)
    assert tag0 == "none"

    class AlwaysPerturb:
        def random(self):
            return 0.0

        def integers(self, low, high):
            return low

    r1, c1, v1, tag1 = s.sparse_shape_perturb(rows, cols, vals, AlwaysPerturb())
    assert tag1 == "neighbor_shell"
    assert len(r1) >= len(rows)

    n_cells, peak = s.update_sparse_max(
        np.zeros(3, dtype=np.float32),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.float32),
        {},
    )
    assert n_cells == 0 and peak == 0.0


def test_stage13_simulate_catalog_streaming_and_pet(load_script, tmp_path, monkeypatch):
    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, out_dir, cat_dir, _map_dir, pet_dir, _mask_dir = _stage13_paths(
        monkeypatch, s, tmp_path
    )
    _seed_historical_events(event_dir, n_events=4)
    event_df, sparse_events = s.load_historical_events()
    sigma = s.calibrate_sigma(event_df, sparse_events)
    doy_cdf = s.build_doy_distribution(event_df)

    (
        ann_max,
        active_rows,
        active_cols,
        ann_occ_peak,
        ann_occ_cells,
        ann_agg_cells,
        ann_n_events,
        stoch_df,
        mmap_path,
    ) = s.simulate_catalog(
        event_df, sparse_events, sigma, doy_cdf, n_years=3, catalog_path=None, work_dir=out_dir
    )
    assert ann_max.shape == (3, len(active_rows))
    assert not stoch_df.empty
    assert mmap_path is None

    stream_path = cat_dir / "streamed.parquet"
    monkeypatch.setattr(s, "_should_stream_events", lambda *_a, **_k: True)
    s.simulate_catalog(
        event_df, sparse_events, sigma, doy_cdf, n_years=2, catalog_path=stream_path, work_dir=out_dir
    )
    assert stream_path.exists()

    occ_pet, agg_pet = s.build_pet(ann_occ_peak, ann_occ_cells, ann_agg_cells, ann_n_events, 3)
    assert not occ_pet.empty
    assert not agg_pet.empty
    occ_pet.to_csv(pet_dir / "pet_occurrence.csv", index=False)
    agg_pet.to_csv(pet_dir / "pet_aggregate.csv", index=False)


def test_stage13_conus_mask_and_validate_errors(load_script, tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("13_generate_stochastic_catalog.py")
    _event_dir, _out_dir, cat_dir, map_dir, pet_dir, mask_dir = _stage13_paths(
        monkeypatch, s, tmp_path
    )

    assert s.load_conus_mask() is None

    with rasterio.open(
        mask_dir / "conus_mask.tif",
        "w",
        driver="GTiff",
        height=s.NROWS,
        width=s.NCOLS,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(-125, 50, 0.05, 0.05),
    ) as dst:
        dst.write(np.ones((s.NROWS, s.NCOLS), dtype=np.uint8), 1)
    assert s.load_conus_mask() is not None

    for rp in s.RP_YEARS:
        (map_dir / f"rp_{rp:05d}yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()
    assert s.validate_outputs() is False

    s.write_catalog_manifest(
        n_years=s.N_SIM_YEARS,
        seed=s.RNG_SEED,
        model_version=s.MODEL_VERSION,
        status="complete",
        n_events=1,
    )
    assert s.validate_outputs() is False

    bad_manifest = cat_dir / "stochastic_catalog_manifest.json"
    bad_manifest.write_text('{"n_years": 1000, "status": "complete", "seed": 1, "model_version": "x"}')
    assert s.validate_outputs() is False


def test_stage13_main_smoke_run(load_script, tmp_path, monkeypatch):
    import sys

    import pytest
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, _out_dir, cat_dir, map_dir, pet_dir, mask_dir = _stage13_paths(
        monkeypatch, s, tmp_path
    )
    _seed_historical_events(event_dir, n_events=6)

    written = []

    def capture_write(arr, path, **_kw):
        written.append(path.name)
        path.write_bytes(b"tif")

    monkeypatch.setattr(s, "write_geotiff", capture_write)
    monkeypatch.setattr(sys, "argv", ["13_generate_stochastic_catalog.py", "--n-years", "3"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0
    assert (cat_dir / "stochastic_event_summary.parquet").exists()
    assert (cat_dir / "stochastic_catalog_manifest.json").exists()
    assert (pet_dir / "pet_occurrence.csv").exists()
    assert any(name.startswith("rp_") for name in written)

    monkeypatch.setattr(sys, "argv", ["13_generate_stochastic_catalog.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 1


def test_stage13_remaining_branches(load_script, tmp_path, monkeypatch):
    import sys

    import pytest
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, out_dir, cat_dir, map_dir, pet_dir, mask_dir = _stage13_paths(
        monkeypatch, s, tmp_path
    )
    _seed_historical_events(event_dir, n_events=3)
    event_df, sparse_events = s.load_historical_events()
    event_df = event_df.copy()
    event_df["peak"] = np.nan
    sigma = s.calibrate_sigma(event_df, sparse_events)
    assert sigma == 0.15

    writer = s.StochasticEventWriter(cat_dir / "empty_flush.parquet", batch_size=10)
    writer.flush()
    writer.close()

    monkeypatch.setattr(s, "ANN_MAX_INMEM_BYTES", 1)
    ann_max, mmap_path = s._open_ann_max_store(4, 4, out_dir / "_work")
    assert mmap_path is not None
    mmap_path.unlink(missing_ok=True)

    with rasterio.open(
        mask_dir / "conus_mask.tif",
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(-125, 50, 0.05, 0.05),
    ) as dst:
        dst.write(np.ones((2, 2), dtype=np.uint8), 1)
    assert s.load_conus_mask() is None

    for rp in s.RP_YEARS:
        (map_dir / f"rp_{rp:05d}yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()
    s.write_catalog_manifest(
        n_years=s.N_SIM_YEARS,
        seed=s.RNG_SEED,
        model_version="not-a-match",
        status="complete",
        n_events=1,
    )
    assert s.validate_outputs() is False


def test_stage13_validate_parquet_schema_errors(load_script, tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    s = load_script("13_generate_stochastic_catalog.py")
    cat_dir = tmp_path / "catalog"
    map_dir = tmp_path / "maps"
    pet_dir = tmp_path / "pet"
    cat_dir.mkdir()
    map_dir.mkdir()
    pet_dir.mkdir()
    monkeypatch.setattr(s, "CAT_DIR", cat_dir)
    monkeypatch.setattr(s, "MAP_DIR", map_dir)
    monkeypatch.setattr(s, "PET_DIR", pet_dir)
    monkeypatch.setattr(s, "CATALOG_MANIFEST", cat_dir / "stochastic_catalog_manifest.json")
    monkeypatch.setattr(s, "RP_YEARS", [10])

    for rp in s.RP_YEARS:
        (map_dir / f"rp_{rp:05d}yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()

    bad_cols = cat_dir / "stochastic_event_summary.parquet"
    pq.write_table(pa.table({"sim_year": [0, 1]}), bad_cols)
    s.write_catalog_manifest(
        n_years=s.N_SIM_YEARS, seed=s.RNG_SEED, model_version=s.MODEL_VERSION,
        status="complete", n_events=2,
    )
    assert s.validate_outputs() is False

    unreadable = cat_dir / "stochastic_event_summary.parquet"
    unreadable.write_bytes(b"not-parquet")
    assert s.validate_outputs() is False


def test_stage13_main_validate_cli(load_script, tmp_path, monkeypatch):
    import sys

    import pytest

    s = load_script("13_generate_stochastic_catalog.py")
    cat_dir = tmp_path / "catalog"
    map_dir = tmp_path / "maps"
    pet_dir = tmp_path / "pet"
    cat_dir.mkdir()
    map_dir.mkdir()
    pet_dir.mkdir()
    monkeypatch.setattr(s, "CAT_DIR", cat_dir)
    monkeypatch.setattr(s, "MAP_DIR", map_dir)
    monkeypatch.setattr(s, "PET_DIR", pet_dir)
    monkeypatch.setattr(s, "CATALOG_MANIFEST", cat_dir / "stochastic_catalog_manifest.json")
    monkeypatch.setattr(s, "validate_outputs", lambda: False)
    monkeypatch.setattr(sys, "argv", ["13_generate_stochastic_catalog.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 1
