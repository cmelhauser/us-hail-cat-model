

def test_stage04b_climo_freezing_levels_bounds(load_script):
    import numpy as np
    s = load_script("04b_fill_gridrad_gap.py")
    h0, hm20 = s._get_freezing_levels_climo(35.0, 5)
    assert 0.5 <= h0 <= 7.0
    assert hm20 > h0


def test_compute_shi_column_positive_when_reflectivity_above_threshold(load_script):
    import numpy as np
    s = load_script("04b_fill_gridrad_gap.py")
    z = np.array([30, 45, 50, 35], dtype=float)
    h = np.array([1, 3, 5, 7], dtype=float)
    shi = s.compute_shi_column(z, h, 2.0, 6.0)
    assert shi > 0
