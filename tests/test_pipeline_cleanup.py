"""Tests for stage output cleanup helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts._pipeline_cleanup import clean_from_stage, paths_from_stage


def test_paths_from_stage_05_includes_corrected_and_diagnostics():
    paths = paths_from_stage("05")
    assert any(p.name == "mesh_0.05deg_corrected" for p in paths)
    assert any(p.name == "radar_artifacts" for p in paths)
    assert any(p.name == "stochastic" for p in paths)


def test_paths_from_stage_06_excludes_corrected():
    paths = paths_from_stage("06", include_diagnostics=False)
    assert not any(p.name == "mesh_0.05deg_corrected" for p in paths)
    assert any(p.name == "validation" for p in paths)


def test_clean_from_stage_removes_tmp_dir(tmp_path, monkeypatch):
    import scripts._pipeline_cleanup as pc

    fake = tmp_path / "mesh_0.05deg_corrected"
    fake.mkdir()
    (fake / "mesh_19980101.tif").write_text("x")
    monkeypatch.setitem(pc.STAGE_OUTPUT_PATHS, "05", (fake,))
    monkeypatch.setattr(pc, "STAGE05_PLUS_DIAGNOSTICS", ())

    removed = clean_from_stage("05", include_diagnostics=False)
    assert fake in removed
    assert not fake.exists()


def test_paths_from_stage_unknown_raises():
    with pytest.raises(ValueError, match="Unknown stage"):
        paths_from_stage("nope")


def test_gridrad_gap_mesh_paths(tmp_path, monkeypatch):
    import scripts._pipeline_cleanup as pc
    from datetime import date

    mesh_dir = tmp_path / "mesh"
    day = pc.GRIDRAD_GAP_START
    path = mesh_dir / str(day.year) / f"mesh_{day.strftime('%Y%m%d')}.tif"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")
    paths = pc.gridrad_gap_mesh_paths(mesh_dir)
    assert path in paths


def test_clean_from_stage_dry_run(tmp_path, monkeypatch):
    import scripts._pipeline_cleanup as pc

    fake = tmp_path / "out.tif"
    fake.write_text("x")
    monkeypatch.setitem(pc.STAGE_OUTPUT_PATHS, "14", (fake,))
    monkeypatch.setattr(pc, "STAGE05_PLUS_DIAGNOSTICS", ())
    removed = clean_from_stage("14", dry_run=True, include_diagnostics=False)
    assert fake in removed
    assert fake.exists()


def test_clean_from_stage_04c_includes_diagnostics(tmp_path, monkeypatch):
    import scripts._pipeline_cleanup as pc

    diag = tmp_path / "radar_artifacts"
    diag.mkdir()
    monkeypatch.setitem(pc.STAGE_OUTPUT_PATHS, "04c", ())
    monkeypatch.setattr(pc, "STAGE05_PLUS_DIAGNOSTICS", (diag,))
    monkeypatch.setattr(pc, "gridrad_gap_mesh_paths", lambda mesh_dir=None: [])
    paths = pc.paths_from_stage("04c", include_diagnostics=True)
    assert diag in paths


def test_gridrad_gap_mesh_paths_finds_existing(tmp_path, monkeypatch):
    import scripts._pipeline_cleanup as pc
    from datetime import date

    monkeypatch.setattr(pc, "GRIDRAD_GAP_START", date(2015, 6, 1))
    monkeypatch.setattr(pc, "GRIDRAD_GAP_END", date(2015, 6, 2))
    day_dir = tmp_path / "2015"
    day_dir.mkdir()
    tif = day_dir / "mesh_20150601.tif"
    tif.write_bytes(b"x")
    found = pc.gridrad_gap_mesh_paths(tmp_path)
    assert tif in found


def test_paths_from_stage_04c_includes_gap_mesh(tmp_path, monkeypatch):
    import scripts._pipeline_cleanup as pc

    tif = tmp_path / "mesh_20150601.tif"
    tif.write_bytes(b"x")
    monkeypatch.setattr(pc, "gridrad_gap_mesh_paths", lambda mesh_dir=None: [tif])
    paths = paths_from_stage("04c", include_diagnostics=False)
    assert tif in paths


def test_paths_from_stage_unknown_numeric_raises():
    import pytest

    with pytest.raises(ValueError, match="Unknown stage"):
        paths_from_stage("99")


def test_clean_from_stage_dry_run_and_file(tmp_path, monkeypatch):
    import scripts._pipeline_cleanup as pc

    d = tmp_path / "outdir"
    d.mkdir()
    f = tmp_path / "file.tif"
    f.write_bytes(b"x")
    monkeypatch.setitem(pc.STAGE_OUTPUT_PATHS, "14", (d, f))
    monkeypatch.setattr(pc, "STAGE_ORDER", ["14"])
    dry = clean_from_stage("14", dry_run=True, include_diagnostics=False)
    assert d in dry and f in dry
    assert d.exists() and f.exists()
    removed = clean_from_stage("14", dry_run=False, include_diagnostics=False)
    assert d in removed and f in removed
    assert not d.exists() and not f.exists()
