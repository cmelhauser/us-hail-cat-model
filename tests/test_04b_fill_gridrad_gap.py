import numpy as np
from conftest import load_stage


def test_stage04b_shi_column_increases_with_reflectivity():
    s = load_stage("04c_fill_gridrad_gap.py")
    heights = np.array([1, 2, 3, 4, 5, 6, 7], dtype=float)
    low = np.array([30, 35, 40, 42, 45, 45, 45], dtype=float)
    high = low + 10
    assert s.compute_shi_column(high, heights, 2.0, 5.0) > s.compute_shi_column(low, heights, 2.0, 5.0)


def test_stage04b_shi_uses_single_temperature_weight():
    s = load_stage("04c_fill_gridrad_gap.py")
    z = np.array([50.0])
    height = np.array([3.5])
    h0, hm20 = 2.0, 5.0
    weight = 0.5
    expected = 0.1 * weight * s.E_COEFF * (10.0 ** (s.E_EXPONENT * 50.0)) * 1000.0
    assert np.isclose(s.compute_shi_column(z, height, h0, hm20), expected)


def test_stage04b_shi_uses_actual_vertical_spacing():
    s = load_stage("04c_fill_gridrad_gap.py")
    z = np.full(3, 50.0)
    uniform = s.compute_shi_column(z, np.array([4.0, 5.0, 6.0]), 2.0, 3.0)
    nonuniform = s.compute_shi_column(z, np.array([4.0, 5.0, 7.0]), 2.0, 3.0)
    assert nonuniform > uniform


def test_stage04b_climo_freezing_levels_are_ordered():
    s = load_stage("04c_fill_gridrad_gap.py")
    h0, hm20 = s._get_freezing_levels_climo(35.0, 5)
    assert 0.5 < h0 < hm20 < 12.0


def test_stage04b_uses_shared_300mm_qa_cap():
    s = load_stage("04c_fill_gridrad_gap.py")
    repaired, n_bad = s.sanitize_hail_values(np.array([[0.0, 299.0, 301.0]], dtype=np.float32))
    assert s.QA_MAX_HAIL_MM == 300.0
    assert n_bad == 1
    assert repaired.tolist() == [[0.0, 299.0, 0.0]]


def test_stage04c_loads_sparse_reflectivity_weight():
    s = load_stage("04c_fill_gridrad_gap.py")

    class Dataset:
        variables = {
            "wReflectivity": np.array([1.75], dtype=np.float32),
            "index": np.array([3], dtype=np.int64),
            "Altitude": np.array([1.0, 2.0], dtype=np.float32),
            "Latitude": np.array([35.0], dtype=np.float32),
            "Longitude": np.array([-97.0, -96.0], dtype=np.float32),
        }

    weight = s._load_indexed_3d(Dataset(), "wReflectivity")
    assert weight.shape == (2, 1, 2)
    assert weight[1, 0, 1] == 1.75
