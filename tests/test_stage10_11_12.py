
def test_stage10_config_and_function_exists(load_script):
    s = load_script("10_build_smooth_cdf.py")
    assert s.POOL_RADIUS_KM > s.DECAY_KM
    assert hasattr(s, "return_period_value")


def test_stage11_thresholds_are_sorted(load_script):
    s = load_script("11_build_occurrence_probs.py")
    mm = [t * s.MM_PER_IN for t in s.THRESHOLDS_IN]
    assert mm == sorted(mm)


def test_stage12_topo_factor_bounds(load_script):
    import numpy as np
    s = load_script("12_apply_conus_mask.py")
    elev = np.array([[0, 1000, 3000]], dtype=np.float32)
    fl = np.array([[4, 4, 4]], dtype=np.float32)
    factor = s.compute_topo_factor(elev, fl)
    assert factor.min() >= 1.0
    assert factor.max() <= 1.25
    assert factor[0,2] > factor[0,1] > factor[0,0]
