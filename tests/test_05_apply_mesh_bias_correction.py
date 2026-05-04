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
