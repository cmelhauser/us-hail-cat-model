from pathlib import Path


def test_mesh75_correction_monotonic(load_script):
    import numpy as np
    s = load_script("05_apply_mesh_bias_correction.py")
    data = np.array([[0, 10, 20, 40]], dtype=np.float32)
    out = s.apply_mesh75_correction(data)
    assert out[0, 0] == 0
    assert np.all(np.diff(out[0, 1:]) > 0)


def test_environmental_filter_floor_and_winter(load_script):
    import numpy as np
    s = load_script("05_apply_mesh_bias_correction.py")
    data = np.array([[4, 10, 30]], dtype=np.float32)
    lat = np.array([[29, 29, 29]], dtype=np.float32)
    out = s.apply_environmental_filter(data, day_of_year=10, lat_grid=lat)
    assert out[0, 0] == 0
    assert out[0, 1] == 0
    assert out[0, 2] == 30


def test_stage05_accepts_v21_cli_flags():
    script = Path(__file__).resolve().parents[1] / "scripts" / "05_apply_mesh_bias_correction.py"
    source = script.read_text()
    assert "--skip-ml" in source
    assert "--retrain-models" in source
