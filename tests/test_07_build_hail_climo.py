from pathlib import Path
from conftest import load_stage


def test_stage07_build_doy_index_parses_dates(tmp_path, monkeypatch):
    s = load_stage("07_build_hail_climo.py")
    d = tmp_path / "2020"
    d.mkdir()
    (d / "mesh_20200101.tif").write_text("placeholder")
    (d / "mesh_20201231.tif").write_text("placeholder")
    monkeypatch.setattr(s, "IN_DIR", tmp_path)
    idx = s.build_doy_index()
    assert 1 in idx
    assert 366 in idx
