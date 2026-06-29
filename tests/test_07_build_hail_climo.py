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


def test_stage07_classify_mesh_era(load_script):
    s = load_script("07_build_hail_climo.py")
    from datetime import date

    assert s.classify_mesh_era(date(2010, 6, 1)) == "MYRORSS"
    assert s.classify_mesh_era(date(2015, 6, 1)) == "GridRad"
    assert s.classify_mesh_era(date(2021, 6, 1)) == "MRMS"


def test_stage07_summarize_input_coverage(load_script, tmp_path):
    s = load_script("07_build_hail_climo.py")
    from datetime import date

    paths = [
        tmp_path / "2010" / "mesh_20100601.tif",
        tmp_path / "2015" / "mesh_20150601.tif",
        tmp_path / "2021" / "mesh_20210601.tif",
    ]
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    summary = s.summarize_input_coverage(paths)
    assert summary["n_files"] == 3
    assert summary["eras"]["MYRORSS"] == 1
    assert summary["eras"]["GridRad"] == 1
    assert summary["eras"]["MRMS"] == 1
