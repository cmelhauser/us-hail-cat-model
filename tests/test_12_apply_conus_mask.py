import numpy as np
from conftest import load_stage


def test_stage12_uniform_topo_when_dem_missing(tmp_path, monkeypatch):
    s = load_stage("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "TOPO_DIR", tmp_path)
    monkeypatch.setattr(s, "write_geotiff", lambda data, path: path.write_bytes(b"ok"))
    out = s.build_topo_correction()
    assert out.shape == (s.NROWS, s.NCOLS)
    assert np.all(out == 1.0)


def test_stage12_validate_fails_when_mask_missing(tmp_path, monkeypatch):
    s = load_stage("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "MASK_DIR", tmp_path)
    assert s.validate_outputs() is False
