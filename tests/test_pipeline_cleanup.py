"""Tests for stage output cleanup helpers."""

from __future__ import annotations

from pathlib import Path

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
