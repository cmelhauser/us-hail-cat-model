"""Stage 04c: merge-safe gridrad_days.txt helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def test_merge_gridrad_days_labels_union(load_script, tmp_path: Path) -> None:
    s = load_script("04c_fill_gridrad_gap.py")
    path = tmp_path / "gridrad_days.txt"
    path.write_text("20150520\n", encoding="utf-8")
    n = s.merge_gridrad_days_labels(path, ["20150521", "20150520"])
    assert n == 2
    assert path.read_text(encoding="utf-8").strip().splitlines() == [
        "20150520",
        "20150521",
    ]


def test_rebuild_gridrad_days_from_geotiffs(load_script, tmp_path: Path, monkeypatch) -> None:
    s = load_script("04c_fill_gridrad_gap.py")
    out = tmp_path / "mesh"
    monkeypatch.setattr(s, "OUT_DIR", out)
    day = date(2015, 5, 20)
    tif = out / "2015" / "mesh_20150520.tif"
    tif.parent.mkdir(parents=True)
    tif.write_bytes(b"fake")
    # Stale label inside window without a GeoTIFF should be dropped.
    days_file = out / "gridrad_days.txt"
    days_file.write_text("20150519\n20150521\n", encoding="utf-8")
    labels = s.rebuild_gridrad_days_from_geotiffs(out, date(2015, 5, 19), date(2015, 5, 21))
    assert labels == ["20150520"]
    assert days_file.read_text(encoding="utf-8").strip() == "20150520"
