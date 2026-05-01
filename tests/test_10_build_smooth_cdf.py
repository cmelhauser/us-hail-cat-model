from conftest import load_stage


def test_stage10_haversine_zero_and_positive():
    s = load_stage("10_build_smooth_cdf.py")
    assert s.haversine_km(40, -100, 40, -100) == 0
    assert s.haversine_km(40, -100, 41, -100) > 100


def test_stage10_return_period_value_positive_for_valid_fit():
    s = load_stage("10_build_smooth_cdf.py")
    val = s.return_period_value(100, mu=3.2, sigma=0.4, xi_gpd=0.1, sigma_gpd=10, thresh=50.8, p_occ=0.5)
    assert val >= 0
