import numpy as np


def test_stage12_uniform_topo_when_dem_missing(load_script, tmp_path, monkeypatch):
    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "TOPO_DIR", tmp_path)
    monkeypatch.setattr(s, "write_geotiff", lambda data, path: path.write_bytes(b"ok"))
    out = s.build_topo_correction()
    assert out.shape == (s.NROWS, s.NCOLS)
    assert np.all(out == 1.0)


def test_stage12_validate_fails_when_mask_missing(load_script, tmp_path, monkeypatch):
    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "MASK_DIR", tmp_path)
    assert s.validate_outputs() is False


def test_stage12_workers_default(load_script):
    s = load_script("12_apply_conus_mask.py")
    args = s.build_arg_parser().parse_args([])
    assert args.workers == 4
