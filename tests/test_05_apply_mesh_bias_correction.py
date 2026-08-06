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
