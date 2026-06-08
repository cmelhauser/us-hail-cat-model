"""Stage 04c: convective-day NetCDF staging filter."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def test_convective_window_coverage_ok_accepts_dense_severe_series():
    from scripts._io import convective_window_coverage_ok

    day = date(2016, 7, 21)
    start = datetime(2016, 7, 21, 12, 0, tzinfo=timezone.utc)
    times = [start + timedelta(minutes=5 * i) for i in range(288)]
    assert convective_window_coverage_ok(times, day, max_gap_minutes=15.0)


def test_convective_window_coverage_ok_rejects_large_gap():
    from scripts._io import convective_window_coverage_ok

    day = date(2016, 7, 21)
    times = [
        datetime(2016, 7, 21, 12, 0, tzinfo=timezone.utc),
        datetime(2016, 7, 21, 14, 0, tzinfo=timezone.utc),
        datetime(2016, 7, 21, 16, 0, tzinfo=timezone.utc),
        datetime(2016, 7, 21, 18, 0, tzinfo=timezone.utc),
        datetime(2016, 7, 21, 20, 0, tzinfo=timezone.utc),
        datetime(2016, 7, 21, 22, 0, tzinfo=timezone.utc),
    ]
    assert not convective_window_coverage_ok(times, day, max_gap_minutes=15.0)


def test_find_gridrad_files_filters_by_convective_window(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    g = tmp_path / "gridrad_severe"
    monkeypatch.setattr(s, "GRIDRAD_SEV", g)
    monkeypatch.setattr(s, "GRIDRAD_DIR", tmp_path / "gridrad")

    day = date(2016, 7, 21)
    stage = g / "by_convective_day" / "20160721"
    stage.mkdir(parents=True)
    (stage / "nexrad_3d_v4_2_20160721T110000Z.nc").write_text("x", encoding="utf-8")
    (stage / "nexrad_3d_v4_2_20160721T130000Z.nc").write_text("y", encoding="utf-8")
    (stage / "nexrad_3d_v4_2_20160722T110000Z.nc").write_text("z", encoding="utf-8")

    files, source = s.find_gridrad_files(day)
    assert source == "gridrad-severe-5min"
    assert [p.name for p in files] == [
        "nexrad_3d_v4_2_20160721T130000Z.nc",
        "nexrad_3d_v4_2_20160722T110000Z.nc",
    ]


def test_find_gridrad_files_severe_only_when_window_covered(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    sev = tmp_path / "gridrad_severe"
    hourly = tmp_path / "gridrad"
    monkeypatch.setattr(s, "GRIDRAD_SEV", sev)
    monkeypatch.setattr(s, "GRIDRAD_DIR", hourly)

    day = date(2016, 7, 21)
    sev_stage = sev / "by_convective_day" / "20160721"
    sev_stage.mkdir(parents=True)
    hr_stage = hourly / "by_convective_day" / "20160721"
    hr_stage.mkdir(parents=True)

    start = datetime(2016, 7, 21, 12, 0, tzinfo=timezone.utc)
    for i in range(288):
        t = start + timedelta(minutes=5 * i)
        ymd = t.strftime("%Y%m%d")
        hms = t.strftime("%H%M%S")
        (sev_stage / f"nexrad_3d_v4_2_{ymd}T{hms}Z.nc").write_text("s", encoding="utf-8")
    (hr_stage / "nexrad_3d_v4_2_20160721T150000Z.nc").write_text("h", encoding="utf-8")

    files, source = s.find_gridrad_files(day)
    assert source == "gridrad-severe-5min"
    assert len(files) == 288
    assert all("gridrad_severe" in str(p) for p in files)


def test_find_gridrad_files_hourly_fill_when_severe_sparse(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    sev = tmp_path / "gridrad_severe"
    hourly = tmp_path / "gridrad"
    monkeypatch.setattr(s, "GRIDRAD_SEV", sev)
    monkeypatch.setattr(s, "GRIDRAD_DIR", hourly)

    day = date(2016, 7, 21)
    sev_stage = sev / "by_convective_day" / "20160721"
    sev_stage.mkdir(parents=True)
    hr_stage = hourly / "by_convective_day" / "20160721"
    hr_stage.mkdir(parents=True)

    (sev_stage / "nexrad_3d_v4_2_20160721T130000Z.nc").write_text("s", encoding="utf-8")
    (hr_stage / "nexrad_3d_v4_2_20160721T150000Z.nc").write_text("h", encoding="utf-8")
    (hr_stage / "nexrad_3d_v4_2_20160721T160000Z.nc").write_text("h", encoding="utf-8")

    files, source = s.find_gridrad_files(day)
    assert source == "gridrad-severe-5min+hourly-fill"
    names = {p.name for p in files}
    assert "nexrad_3d_v4_2_20160721T130000Z.nc" in names
    assert "nexrad_3d_v4_2_20160721T150000Z.nc" in names
