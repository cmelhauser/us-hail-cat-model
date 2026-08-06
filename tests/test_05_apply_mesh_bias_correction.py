import numpy as np
from conftest import load_stage


def test_stage05_mesh75_correction_monotonic_and_zero_preserving():
    s = load_stage("05_apply_mesh_bias_correction.py")
    data = np.array([0, 10, 50, 100], dtype=np.float32)
    out = s.apply_mesh75_correction(data)
    assert out[0] == 0
    assert np.all(np.diff(out[1:]) > 0)


def test_stage05_environmental_filter_winter_subtropics():
    s = load_stage("05_apply_mesh_bias_correction.py")
    data = np.array([[4.0, 20.0, 30.0]], dtype=np.float32)
    lat = np.array([[29.0, 29.0, 29.0]], dtype=np.float32)
    out = s.apply_environmental_filter(data, day_of_year=10, lat_grid=lat)
    assert out.tolist() == [[0.0, 0.0, 30.0]]


def test_stage05_optional_filter_falls_back_without_model():
    s = load_stage("05_apply_mesh_bias_correction.py")
    s._filter_model = None
    data = np.array([[6.0]], dtype=np.float32)
    lat = np.array([[35.0]], dtype=np.float32)
    out = s.apply_probabilistic_environmental_filter(data, lat, month=5, day_of_year=150)
    assert float(out[0, 0]) == 6.0


def test_stage05_sanitizes_corrected_outputs_to_300mm_cap():
    s = load_stage("05_apply_mesh_bias_correction.py")
    repaired, n_bad = s.sanitize_hail_values(np.array([[300.0, 300.1, np.nan]], dtype=np.float32))
    assert s.QA_MAX_HAIL_MM == 300.0
    assert n_bad == 2
    assert repaired.tolist() == [[300.0, 0.0, 0.0]]


def test_stage05_cli_keeps_spc_out_of_hazard_path():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "05_apply_mesh_bias_correction.py"
    ).read_text()
    assert "--skip-ml" in source
    assert "--allow-spc-derived-adjustments" not in source
    assert "apply_artifact_classifier" not in source
    assert "PERSISTENCE_HISTORY_SIDECAR" in source


def test_stage05_skip_ml_bypasses_optional_filter(load_script, monkeypatch):
    s = load_script("05_apply_mesh_bias_correction.py")
    data = np.array([[40.0]], dtype=np.float32)
    lat = np.array([[35.0]], dtype=np.float32)
    monkeypatch.setattr(s, "_filter_model", object())
    out_filt = s.apply_probabilistic_filter(data, 150, lat, skip_ml=True)
    assert float(out_filt[0, 0]) == 40.0


def test_stage05_resume_loads_persistence_sidecar(load_script, tmp_path, monkeypatch):
    s = load_script("05_apply_mesh_bias_correction.py")
    s.reset_gridrad_history()
    in_path = tmp_path / "mesh_20150601.tif"
    out_path = tmp_path / "mesh_20150601_out.tif"
    frame = np.arange(12, dtype=np.float32).reshape(3, 4)
    sidecar = s.persistence_history_path(out_path)
    np.save(sidecar, frame)
    out_path.write_bytes(b"exists")
    monkeypatch.setattr(s, "is_gridrad_source", lambda _d: True)
    result = s.process_file(
        in_path,
        out_path,
        lat_grid=np.zeros((3, 4), dtype=np.float32),
        skip_ml=True,
        speckle_filter=True,
    )
    assert result == {"skipped": True}
    assert len(s._gridrad_history) == 1
    assert np.allclose(s._gridrad_history[0], frame)


def test_stage05_saves_persistence_sidecar_when_filtering(
    load_script, tmp_path, monkeypatch
):
    import rasterio
    from rasterio.transform import from_origin

    import _radar_geometry as rg

    s = load_script("05_apply_mesh_bias_correction.py")
    s.reset_gridrad_history()
    profile = {
        "driver": "GTiff",
        "height": 4,
        "width": 4,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-100, 40, 0.05, 0.05),
    }
    in_path = tmp_path / "mesh_20150615.tif"
    out_path = tmp_path / "out" / "mesh_20150615.tif"
    data = np.full((4, 4), 35.0, dtype=np.float32)
    with rasterio.open(in_path, "w", **profile) as dst:
        dst.write(data, 1)

    monkeypatch.setattr(s, "is_gridrad_source", lambda _d: True)
    monkeypatch.setattr(
        s, "apply_optional_cqm", lambda arr, *_a, **_k: arr.astype(np.float32)
    )
    monkeypatch.setattr(s, "apply_probabilistic_filter", lambda arr, *_a, **_k: arr)
    monkeypatch.setattr(s, "_range_km_grid", np.ones((4, 4), dtype=np.float32) * 50.0)
    monkeypatch.setattr(s, "_site_idx_grid", np.zeros((4, 4), dtype=np.int16))

    def fake_remove(arr, *_a, **_k):
        return arr.copy(), {"speckle": 0}

    monkeypatch.setattr(rg, "remove_gridrad_artifacts", fake_remove)
    monkeypatch.setattr(rg, "PERSISTENCE_MIN_HISTORY_DAYS", 99)

    result = s.process_file(
        in_path,
        out_path,
        lat_grid=np.full((4, 4), 35.0, dtype=np.float32),
        skip_ml=True,
        speckle_filter=True,
    )
    assert "skipped" not in result
    sidecar = s.persistence_history_path(out_path)
    assert sidecar.is_file()
    assert len(s._gridrad_history) == 1
    assert np.allclose(np.load(sidecar, allow_pickle=False), data)


def test_stage05_reconstructs_prefilter_history_when_sidecar_missing(
    load_script, tmp_path, monkeypatch
):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("05_apply_mesh_bias_correction.py")
    in_path = tmp_path / "mesh_20150615.tif"
    out_path = tmp_path / "out.tif"
    data = np.full((2, 2), 20.0, dtype=np.float32)
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-100, 40, 0.05, 0.05),
    }
    with rasterio.open(in_path, "w", **profile) as dst:
        dst.write(data, 1)
    monkeypatch.setattr(
        s,
        "apply_optional_cqm",
        lambda arr, *_a, **_k: arr.astype(np.float32) + 7.0,
    )

    frame = s.load_persistence_history_frame(
        out_path,
        in_path,
        np.full((2, 2), 35.0, dtype=np.float32),
        skip_ml=True,
    )

    assert np.allclose(frame, data + 7.0)


def test_stage05_corrupt_sidecar_reconstructs_and_atomic_save_cleans_temp(
    load_script, tmp_path, monkeypatch
):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("05_apply_mesh_bias_correction.py")
    in_path = tmp_path / "mesh_20150615.tif"
    out_path = tmp_path / "out.tif"
    sidecar = s.persistence_history_path(out_path)
    sidecar.write_bytes(b"corrupt")
    profile = {
        "driver": "GTiff",
        "height": 1,
        "width": 1,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-100, 40, 0.05, 0.05),
    }
    with rasterio.open(in_path, "w", **profile) as dst:
        dst.write(np.array([[20.0]], dtype=np.float32), 1)
    monkeypatch.setattr(s, "apply_optional_cqm", lambda arr, *_a, **_k: arr + 3.0)

    frame = s.load_persistence_history_frame(
        out_path,
        in_path,
        np.array([[35.0]], dtype=np.float32),
        skip_ml=True,
    )
    assert np.allclose(frame, [[23.0]])

    def fail_replace(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr(s.os, "replace", fail_replace)
    with np.testing.assert_raises_regex(OSError, "replace failed"):
        s.save_persistence_history_frame(out_path, np.array([[23.0]], dtype=np.float32))
    assert sidecar.read_bytes() == b"corrupt"
    assert not list(tmp_path.glob(f".{sidecar.name}.*.tmp"))


def _mesh_profile(height: int, width: int) -> dict:
    from rasterio.transform import from_origin

    return {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-100, 40, 0.05, 0.05),
    }


def _write_mesh(path, data: np.ndarray) -> None:
    import rasterio

    h, w = data.shape
    with rasterio.open(path, "w", **_mesh_profile(h, w)) as dst:
        dst.write(data.astype(np.float32), 1)


def _stage05_small_grid(monkeypatch, s, tmp_path, *, nrows=4, ncols=4):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    cal_dir = tmp_path / "cal"
    in_dir.mkdir()
    out_dir.mkdir()
    cal_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)
    monkeypatch.setattr(s, "OUT_DIR", out_dir)
    monkeypatch.setattr(s, "CAL_DIR", cal_dir)
    monkeypatch.setattr(s, "QQ_FILE", cal_dir / "gridrad_quantile_map.npz")
    monkeypatch.setattr(s, "CQM_FILE", cal_dir / "gridrad_cqm_model.pkl")
    monkeypatch.setattr(s, "FILTER_FILE", cal_dir / "hail_filter_model.pkl")
    monkeypatch.setattr(s, "DIAG_FILE", cal_dir / "calibration_diagnostics.csv")
    monkeypatch.setattr(s, "LOG_ROOT", tmp_path / "logs")
    monkeypatch.setattr(s, "OUT_NROWS", nrows)
    monkeypatch.setattr(s, "OUT_NCOLS", ncols)
    monkeypatch.setattr(s, "MIN_PAIRS", 8)
    s._gridrad_days = None
    s._qq_gridrad = s._qq_myrorss = s._qq_type = None
    s._cqm_model = s._filter_model = None
    s._range_km_grid = s._site_idx_grid = None
    return in_dir, out_dir, cal_dir


def test_stage05_load_gridrad_days_and_collect_pixels(load_script, tmp_path, monkeypatch):
    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir, _, _ = _stage05_small_grid(monkeypatch, s, tmp_path)
    (in_dir / "gridrad_days.txt").write_text("20150615\n20150616\n")
    assert s.load_gridrad_days() == {"20150615", "20150616"}
    assert s.is_gridrad_source("20150615") is True
    assert s.is_gridrad_source("19990101") is False

    good = in_dir / "mesh_good.tif"
    _write_mesh(good, np.full((2, 2), 40.0, dtype=np.float32))
    assert len(s._collect_active_pixels(good, as_mesh75=False)) == 4
    assert len(s._collect_active_pixels(good, as_mesh75=True)) == 4
    bad = in_dir / "mesh_bad.tif"
    bad.write_bytes(b"not-a-tiff")
    assert s._collect_active_pixels(bad, as_mesh75=False) == []


def test_stage05_calibration_branches(load_script, tmp_path, monkeypatch):
    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir, _, cal_dir = _stage05_small_grid(monkeypatch, s, tmp_path)

    s.build_cross_calibration()
    assert s.QQ_FILE.exists()
    data = np.load(s.QQ_FILE, allow_pickle=True)
    assert str(data["correction_type"]) == "identity"

    (in_dir / "gridrad_days.txt").write_text("20120601\n")
    ydir = in_dir / "2012"
    ydir.mkdir()
    for tag in ("20120601", "20120602"):
        _write_mesh(ydir / f"mesh_{tag}.tif", np.full((4, 4), 60.0, dtype=np.float32))
    my_dir = in_dir / "2010"
    my_dir.mkdir()
    for tag in ("20100601", "20100602"):
        _write_mesh(my_dir / f"mesh_{tag}.tif", np.full((4, 4), 55.0, dtype=np.float32))

    s._gridrad_days = None
    s.build_cross_calibration()
    assert (cal_dir / "calibration_diagnostics.csv").exists()

    s._gridrad_days = None
    monkeypatch.setattr(s, "MIN_PAIRS", 99999)
    s.build_cross_calibration()
    pooled = np.load(s.QQ_FILE, allow_pickle=True)
    assert str(pooled["correction_type"]) in {"era_pooled_quantile_mapping", "identity"}


def test_stage05_gridrad_calibration_and_optional_models(load_script, tmp_path, monkeypatch):
    import pickle

    s = load_script("05_apply_mesh_bias_correction.py")
    _, _, cal_dir = _stage05_small_grid(monkeypatch, s, tmp_path)
    gr_q = np.linspace(0, 100, s.N_PERCENTILES + 1)
    my_q = gr_q * 1.2
    np.savez(
        s.QQ_FILE,
        percentiles=s.PERCENTILES,
        gridrad_quantiles=gr_q,
        myrorss_quantiles=my_q,
        correction_type="quantile_mapping",
    )
    s._qq_gridrad = s._qq_myrorss = s._qq_type = None
    out = s.apply_gridrad_calibration(np.array([[0.0, 50.0, 100.0]], dtype=np.float32))
    assert out[0, 0] == 0.0
    assert out[0, 1] > 50.0

    class MockCQM:
        def predict(self, feats):
            return feats[:, 0] * 1.05

    class MockFilter:
        def predict_proba(self, feats):
            n = feats.shape[0]
            return np.column_stack([np.zeros(n), np.full(n, 0.8)])

    s._cqm_model = MockCQM()
    s._filter_model = MockFilter()

    lat = np.full((2, 2), 35.0, dtype=np.float32)
    data = np.full((2, 2), 40.0, dtype=np.float32)
    cqm_out = s.apply_optional_cqm(data, lat, day_of_year=150, skip_ml=False)
    assert float(cqm_out.max()) > 40.0
    filt_out = s.apply_probabilistic_filter(data, 150, lat, skip_ml=False)
    assert float(filt_out.max()) < 40.0

    feats = s._feature_matrix(data, lat, day_of_year=200)
    assert feats.shape == (4, 5)

    class BrokenCQM:
        def predict(self, _feats):
            raise RuntimeError("boom")

    class BrokenFilter:
        def predict(self, _feats):
            raise RuntimeError("boom")

    s._cqm_model = BrokenCQM()
    s._filter_model = BrokenFilter()
    assert np.allclose(s.apply_optional_cqm(data, lat, 150), s.apply_gridrad_calibration(data))
    assert np.allclose(
        s.apply_probabilistic_filter(data, 150, lat),
        s.apply_environmental_filter(data, 150, lat),
    )

    s._cqm_model = object()
    broken_pkl = cal_dir / "broken.pkl"
    broken_pkl.write_bytes(b"not-pickle")
    monkeypatch.setattr(s, "CQM_FILE", broken_pkl)
    assert s._load_pickle_model(broken_pkl) is None


def test_stage05_process_file_myrorss_and_geometry(load_script, tmp_path, monkeypatch):
    import _radar_geometry as rg

    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir, out_dir, _ = _stage05_small_grid(monkeypatch, s, tmp_path)
    in_path = in_dir / "2021" / "mesh_20210601.tif"
    in_path.parent.mkdir(parents=True)
    data = np.array([[0.0, 20.0], [30.0, 400.0]], dtype=np.float32)
    _write_mesh(in_path, data)
    out_path = out_dir / "2021" / "mesh_20210601.tif"
    lat = np.full((2, 2), 35.0, dtype=np.float32)

    monkeypatch.setattr(s, "is_gridrad_source", lambda _d: False)
    s.init_artifact_grids(speckle_filter=False)
    result = s.process_file(in_path, out_path, lat, skip_ml=True, speckle_filter=False)
    assert result["source"] == "MYRORSS/MRMS"
    assert out_path.is_file()
    assert result["peak_out_mm"] <= 300.0

    monkeypatch.setattr(
        rg,
        "ensure_range_km_grid",
        lambda: np.ones((2, 2), dtype=np.float32) * 40.0,
    )
    monkeypatch.setattr(
        rg,
        "ensure_nearest_site_index_grid",
        lambda: np.zeros((2, 2), dtype=np.int16),
    )
    s._range_km_grid = s._site_idx_grid = None
    s.ensure_geometry_grids()
    assert s._range_km_grid.shape == (2, 2)


def test_stage05_process_file_gridrad_with_history(load_script, tmp_path, monkeypatch):
    import _radar_geometry as rg

    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir, out_dir, _ = _stage05_small_grid(monkeypatch, s, tmp_path)
    in_path = in_dir / "mesh_20150615.tif"
    _write_mesh(in_path, np.full((2, 2), 45.0, dtype=np.float32))
    out_path = out_dir / "mesh_20150615.tif"
    lat = np.full((2, 2), 35.0, dtype=np.float32)

    monkeypatch.setattr(s, "is_gridrad_source", lambda _d: True)
    monkeypatch.setattr(s, "_range_km_grid", np.ones((2, 2), dtype=np.float32) * 50.0)
    monkeypatch.setattr(s, "_site_idx_grid", np.zeros((2, 2), dtype=np.int16))
    monkeypatch.setattr(rg, "PERSISTENCE_MIN_HISTORY_DAYS", 1)
    monkeypatch.setattr(rg, "PERSISTENCE_HISTORY_MAX_DAYS", 2)

    def fake_remove(arr, *_a, **_k):
        cleaned = arr.copy()
        cleaned[0, 0] = 0.0
        return cleaned, {"speckle": 1}

    monkeypatch.setattr(rg, "remove_gridrad_artifacts", fake_remove)
    s.reset_gridrad_history()
    s.append_gridrad_history(np.full((2, 2), 1.0, dtype=np.float32))

    result = s.process_file(in_path, out_path, lat, skip_ml=True, speckle_filter=True)
    assert result["source"] == "GridRad"
    assert result["speckle_removed"] >= 1
    assert len(s._gridrad_history) <= 2


def test_stage05_validate_outputs_and_main(load_script, tmp_path, monkeypatch):
    import sys

    import pytest
    import rasterio

    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir, out_dir, _ = _stage05_small_grid(monkeypatch, s, tmp_path, nrows=2, ncols=2)
    monkeypatch.setattr(s, "STAGE05_PID", tmp_path / "stage05.pid")

    _write_mesh(in_dir / "mesh_20210601.tif", np.full((2, 2), 35.0, dtype=np.float32))
    monkeypatch.setattr(sys, "argv", ["05_apply_mesh_bias_correction.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 1

    for idx in range(3):
        tag = f"2021060{idx + 1}"
        data = np.full((2, 2), 35.0 + idx, dtype=np.float32)
        _write_mesh(in_dir / f"mesh_{tag}.tif", data)
        _write_mesh(out_dir / f"mesh_{tag}.tif", data)

    assert s.validate_outputs() is True

    bad = out_dir / "mesh_20210701.tif"
    _write_mesh(bad, np.array([[301.0, 0.0], [0.0, 0.0]], dtype=np.float32))
    assert s.validate_outputs() is False
    bad.unlink()

    wrong = out_dir / "mesh_20210702.tif"
    profile = _mesh_profile(2, 3)
    with rasterio.open(wrong, "w", **profile) as dst:
        dst.write(np.full((2, 3), 20.0, dtype=np.float32), 1)
    assert s.validate_outputs() is False
    wrong.unlink()

    monkeypatch.setattr(sys, "argv", ["05_apply_mesh_bias_correction.py", "--skip-ml", "--skip-calibration"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0

    monkeypatch.setattr(sys, "argv", ["05_apply_mesh_bias_correction.py", "--year", "2021", "--skip-calibration", "--skip-ml", "--no-speckle-filter"])
    ydir = in_dir / "2021"
    ydir.mkdir(exist_ok=True)
    _write_mesh(ydir / "mesh_20210610.tif", np.full((2, 2), 25.0, dtype=np.float32))
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


class _PickleCQM:
    def predict(self, feats):
        return feats[:, 0] * 1.02


def test_stage05_remaining_branches(load_script, tmp_path, monkeypatch):
    import pickle
    import sys

    import pytest

    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir, out_dir, cal_dir = _stage05_small_grid(monkeypatch, s, tmp_path, nrows=2, ncols=2)
    (in_dir / "gridrad_days.txt").write_text("20100601\n20100602\n20100603\n")
    ydir = in_dir / "2010"
    ydir.mkdir()
    for tag in ("20100601", "20100602", "20100603", "20100604", "20100605", "20100606"):
        _write_mesh(ydir / f"mesh_{tag}.tif", np.full((2, 2), 70.0, dtype=np.float32))
    s._gridrad_days = None
    s.build_cross_calibration()
    pooled = np.load(s.QQ_FILE, allow_pickle=True)
    assert str(pooled["correction_type"]) == "quantile_mapping"

    with open(cal_dir / "gridrad_cqm_model.pkl", "wb") as handle:
        pickle.dump(_PickleCQM(), handle)
    s._cqm_model = None
    lat = np.full((2, 2), 35.0, dtype=np.float32)
    out = s.apply_optional_cqm(np.full((2, 2), 40.0, dtype=np.float32), lat, 150, skip_ml=False)
    assert float(out.max()) > 40.0

    in_path = in_dir / "mesh_20150615.tif"
    out_path = out_dir / "mesh_20150615.tif"
    _write_mesh(in_path, np.full((2, 2), 55.0, dtype=np.float32))
    np.save(s.persistence_history_path(out_path), np.zeros((3, 3), dtype=np.float32))
    monkeypatch.setattr(s, "is_gridrad_source", lambda _d: True)
    frame = s.load_persistence_history_frame(out_path, in_path, lat, skip_ml=True)
    assert frame is not None
    assert frame.shape == (2, 2)

    broken = in_dir / "mesh_broken.tif"
    broken.write_bytes(b"bad")
    assert s.load_persistence_history_frame(out_path, broken, lat, skip_ml=True) is None

    monkeypatch.setattr(s, "OUT_DIR", tmp_path / "missing_out")
    assert s.validate_outputs() is False

    out_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(s, "OUT_DIR", out_dir)
    peak_data = np.full((2, 2), 80.0, dtype=np.float32)
    _write_mesh(out_dir / "mesh_20210601.tif", peak_data)
    _write_mesh(in_dir / "mesh_20210601.tif", peak_data)
    monkeypatch.setattr(
        s,
        "apply_probabilistic_filter",
        lambda arr, *_a, **_k: np.full_like(arr, np.nan),
    )
    monkeypatch.setattr(s, "is_gridrad_source", lambda _d: False)
    s.process_file(in_dir / "mesh_20210601.tif", out_dir / "mesh_20210601.tif", lat, skip_ml=True)

    monkeypatch.setattr(sys, "argv", ["05_apply_mesh_bias_correction.py", "--retrain-models"])
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "train_artifact_classifier.py").write_text("import sys\nsys.exit(0)\n")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0
