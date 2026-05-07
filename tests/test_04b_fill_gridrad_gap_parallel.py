from __future__ import annotations

from datetime import date

def test_stage04b_workers_flag_default(load_script):
    s = load_script("04b_fill_gridrad_gap.py")
    p = s.build_arg_parser()
    assert p.parse_args([]).workers == 4
    assert p.parse_args(["--workers", "1"]).workers == 1


def test_stage04b_process_day_worker_wraps_exceptions(load_script, monkeypatch):
    s = load_script("04b_fill_gridrad_gap.py")

    def boom(_day):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(s, "process_day", boom)
    ymd, result = s._process_day_worker(date(2015, 5, 1))
    assert ymd == "20150501"
    assert "error" in result

