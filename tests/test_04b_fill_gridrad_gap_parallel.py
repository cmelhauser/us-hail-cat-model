from __future__ import annotations

from datetime import date

def test_stage04b_workers_flag_default(load_script):
    s = load_script("04c_fill_gridrad_gap.py")
    p = s.build_arg_parser()
    assert p.parse_args([]).workers == 1
    assert p.parse_args([]).download_workers == 1
    assert p.parse_args(["--workers", "4"]).workers == 4


def test_stage04b_process_day_worker_wraps_exceptions(load_script, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")

    def boom(_day):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(s, "process_day", boom)
    ymd, result = s._process_day_worker(date(2015, 5, 1))
    assert ymd == "20150501"
    assert "error" in result


def test_delete_gridrad_inputs_for_day_removes_directories(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    g = tmp_path / "gridrad"
    sev = tmp_path / "gridrad_severe"
    monkeypatch.setattr(s, "GRIDRAD_DIR", g)
    monkeypatch.setattr(s, "GRIDRAD_SEV", sev)
    day = date(2015, 5, 1)
    d1 = g / "2015" / "20150501"
    d2 = sev / "2015" / "20150501"
    d1.mkdir(parents=True)
    (d1 / "stub.nc").write_text("x", encoding="utf-8")
    d2.mkdir(parents=True)
    (d2 / "stub2.nc").write_text("y", encoding="utf-8")
    s.delete_gridrad_inputs_for_day(day)
    assert not d1.exists()
    assert not d2.exists()


def test_run_one_day_download_then_process_skips_download_when_tif_exists(
    load_script, tmp_path, monkeypatch,
):
    s = load_script("04c_fill_gridrad_gap.py")
    day = date(2015, 5, 1)
    ymd = day.strftime("%Y%m%d")
    out = tmp_path / "2015" / f"mesh_{ymd}.tif"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"0")

    monkeypatch.setattr(s, "OUT_DIR", tmp_path)

    def no_04b():
        raise AssertionError("_load_04b_module should not run when output exists")

    monkeypatch.setattr(s, "_load_04b_module", no_04b)

    def fake_process(d):
        assert d == day
        return {"skipped": True}

    monkeypatch.setattr(s, "process_day", fake_process)
    y, r = s._run_one_day_download_then_process((day, True, 4))
    assert y == ymd
    assert r.get("skipped") is True


def test_run_one_day_download_then_process_no_download_when_flag_false(
    load_script, tmp_path, monkeypatch,
):
    s = load_script("04c_fill_gridrad_gap.py")
    day = date(2015, 5, 1)
    ymd = day.strftime("%Y%m%d")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)

    def no_04b():
        raise AssertionError("_load_04b_module should not run when with_04b is false")

    monkeypatch.setattr(s, "_load_04b_module", no_04b)

    def fake_process(d):
        assert d == day
        return {"files": 0, "no_data": True}

    monkeypatch.setattr(s, "process_day", fake_process)
    y, r = s._run_one_day_download_then_process((day, False, 4))
    assert y == ymd
    assert r.get("no_data") is True

