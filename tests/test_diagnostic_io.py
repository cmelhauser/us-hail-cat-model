"""Tests for scripts/diagnostics/_diagnostic_io.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.diagnostics._diagnostic_io import (
    count_mesh_tifs,
    exit_if_missing,
    require_mesh_tifs,
    require_path,
    warn_skip,
)


def test_count_mesh_tifs_empty_dir(tmp_path: Path):
    assert count_mesh_tifs(tmp_path) == 0


def test_count_mesh_tifs_matches_pattern(tmp_path: Path):
    (tmp_path / "mesh_20200101.tif").write_bytes(b"x")
    (tmp_path / "not_mesh.tif").write_bytes(b"x")
    assert count_mesh_tifs(tmp_path) == 1


def test_require_path_missing_file(tmp_path: Path, capsys):
    ok = require_path(tmp_path / "missing.csv", "test_step", kind="file")
    assert ok is False
    assert "WARNING: SKIP test_step" in capsys.readouterr().out


def test_require_path_existing_dir(tmp_path: Path):
    assert require_path(tmp_path, "dir_step", kind="dir") is True


def test_require_mesh_tifs_warns(tmp_path: Path, capsys):
    ok = require_mesh_tifs(tmp_path, "mesh_scan", min_count=1)
    assert ok is False
    assert "WARNING: SKIP mesh_scan" in capsys.readouterr().out


def test_require_mesh_tifs_ok(tmp_path: Path):
    (tmp_path / "mesh_20200101.tif").write_bytes(b"x")
    assert require_mesh_tifs(tmp_path, "mesh_scan", min_count=1) is True


def test_warn_skip_prints(capsys):
    warn_skip("my_check", "no data")
    assert "WARNING: SKIP my_check — no data" in capsys.readouterr().out


def test_exit_if_missing_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        exit_if_missing(False, "step", "reason")
    assert exc.value.code == 0
    assert "WARNING: SKIP step" in capsys.readouterr().out


def test_require_path_generic_kind(tmp_path: Path, capsys):
    ok = require_path(tmp_path / "any", "generic", kind="path")
    assert ok is False
    assert "required path not found" in capsys.readouterr().out


def test_count_mesh_tifs_non_dir(tmp_path: Path):
    assert count_mesh_tifs(tmp_path / "not-a-dir") == 0


def test_require_path_kind_path(tmp_path: Path):
    f = tmp_path / "exists.txt"
    f.write_text("ok")
    assert require_path(f, "path_step", kind="path") is True


def test_count_mesh_tifs_not_a_directory(tmp_path: Path):
    f = tmp_path / "file_not_dir"
    f.write_text("x")
    assert count_mesh_tifs(f) == 0


def test_require_path_generic_kind_existing_dir(tmp_path: Path):
    assert require_path(tmp_path, "any", kind="path") is True


def test_count_mesh_tifs_missing_dir(tmp_path: Path):
    assert count_mesh_tifs(tmp_path / "nope") == 0
