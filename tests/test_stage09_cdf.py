
def test_stage09_has_threshold_diagnostics(load_script):
    s = load_script("09_fit_cdf_regional.py")
    source = (s.Path(__file__).resolve() if False else None)  # keep import smoke lightweight
    assert hasattr(s, "compute_mrl_and_threshold")
    assert hasattr(s, "THRESHOLD_DIAGNOSTICS")


def test_stage09_return_periods_configured(load_script):
    s = load_script("09_fit_cdf_regional.py")
    assert s.RP_YEARS == sorted(s.RP_YEARS)
    assert 50000 in s.RP_YEARS
