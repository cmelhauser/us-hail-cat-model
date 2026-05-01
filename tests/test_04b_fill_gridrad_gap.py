import numpy as np
from conftest import load_stage


def test_stage04b_shi_column_increases_with_reflectivity():
    s = load_stage("04b_fill_gridrad_gap.py")
    heights = np.array([1, 2, 3, 4, 5, 6, 7], dtype=float)
    low = np.array([30, 35, 40, 42, 45, 45, 45], dtype=float)
    high = low + 10
    assert s.compute_shi_column(high, heights, 2.0, 5.0) > s.compute_shi_column(low, heights, 2.0, 5.0)


def test_stage04b_climo_freezing_levels_are_ordered():
    s = load_stage("04b_fill_gridrad_gap.py")
    h0, hm20 = s._get_freezing_levels_climo(35.0, 5)
    assert 0.5 < h0 < hm20 < 12.0
