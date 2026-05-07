from pathlib import Path


def test_stage07_build_doy_index_parses_dates(load_script, tmp_path, monkeypatch):
    s = load_script("07_build_hail_climo.py")
    d = tmp_path / "2020"
    d.mkdir()
    (d / "mesh_20200101.tif").write_text("placeholder")
    (d / "mesh_20201231.tif").write_text("placeholder")
    monkeypatch.setattr(s, "IN_DIR", tmp_path)
    idx = s.build_doy_index()
    assert 1 in idx
    assert 366 in idx


def test_stage07_workers_default(load_script):
    s = load_script("07_build_hail_climo.py")
    args = s.build_arg_parser().parse_args([])
    assert args.workers == 4
