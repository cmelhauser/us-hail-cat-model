from conftest import load_stage


def test_stage04a_pressure_levels_span_melting_layer():
    s = load_stage("04a_download_era5_isotherms.py")
    levels = [int(x) for x in s.PRESSURE_LEVELS]
    assert min(levels) <= 200
    assert max(levels) >= 1000
    assert len(levels) >= 20
