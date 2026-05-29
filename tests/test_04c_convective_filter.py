"""Stage 04c: convective-day NetCDF staging filter."""

from __future__ import annotations

from datetime import date
from pathlib import Path


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
