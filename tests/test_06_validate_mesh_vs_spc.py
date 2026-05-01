from conftest import load_stage


def test_stage06_latlon_to_grid_inside_and_outside():
    s = load_stage("06_validate_mesh_vs_spc.py")
    row, col = s.latlon_to_grid(40.0, -100.0)
    assert 0 <= row < s.NROWS
    assert 0 <= col < s.NCOLS
    assert s.latlon_to_grid(10.0, -100.0) == (-1, -1)


def test_stage06_calibration_reports_bias():
    s = load_stage("06_validate_mesh_vs_spc.py")
    pairs = [
        {"spc_size_in": 1.0, "mesh75_in": 1.2, "mesh75_mm": 30.48},
        {"spc_size_in": 1.25, "mesh75_in": 1.0, "mesh75_mm": 25.4},
    ]
    cal = s.compute_calibration(pairs)
    severe_bin = [r for r in cal if r.get("bin") == '1.00-1.50"'][0]
    assert severe_bin["n"] == 2
    assert "bias_in" in severe_bin
