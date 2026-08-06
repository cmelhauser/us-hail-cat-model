"""Tests for scripts/07_build_hail_climo.py."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from conftest import load_stage


@pytest.fixture
def s07():
    return load_stage("07_build_hail_climo.py")


def _patch_write_geotiff(s07, monkeypatch):
    def write_array(data: np.ndarray, out_path: Path, **_kw) -> None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-100, 40, 0.05, 0.05),
        ) as dst:
            dst.write(data.astype(np.float32), 1)

    monkeypatch.setattr(s07, "write_geotiff", write_array)


def _write_mesh_tif(path: Path, value: float, shape: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.full(shape, value, dtype=np.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-100, 40, 0.05, 0.05),
    ) as dst:
        dst.write(data, 1)


def test_stage07_build_doy_index_skips_invalid_dates(s07, tmp_path, monkeypatch):
    d = tmp_path / "2020"
    d.mkdir()
    (d / "mesh_20201399.tif").write_text("placeholder")
    monkeypatch.setattr(s07, "IN_DIR", tmp_path)
    idx = s07.build_doy_index()
    assert idx == {}


def test_stage07_build_climatology_sequential_read_partial_failure(s07, tmp_path, monkeypatch):
    nrows, ncols = 2, 2
    monkeypatch.setattr(s07, "NROWS", nrows)
    monkeypatch.setattr(s07, "NCOLS", ncols)
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    monkeypatch.setattr(s07, "IN_DIR", in_dir)
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    _patch_write_geotiff(s07, monkeypatch)

    _write_mesh_tif(in_dir / "2015" / "mesh_20150701.tif", 10.0, (nrows, ncols))
    bad = in_dir / "2017" / "mesh_20170701.tif"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"broken")

    class BoomPool:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def map(self, *args, **kwargs):
            raise RuntimeError("pool failed")

    monkeypatch.setattr(s07, "ThreadPoolExecutor", BoomPool)
    s07.build_climatology()
    with rasterio.open(out_dir / "climo_182.tif") as src:
        assert float(src.read(1).mean()) == pytest.approx(10.0)


def test_stage07_make_seasonal_figure_import_error(s07, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib":
            raise ImportError("no matplotlib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    s07.make_seasonal_figure()


def test_stage07_validate_outputs_missing_dir(s07, tmp_path, monkeypatch):
    monkeypatch.setattr(s07, "OUT_DIR", tmp_path / "missing")
    assert s07.validate_outputs() is False


def test_stage07_validate_outputs_wrong_file_count(s07, tmp_path, monkeypatch):
    out_dir = tmp_path / "climo"
    out_dir.mkdir()
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    monkeypatch.setattr(s07, "NROWS", 2)
    monkeypatch.setattr(s07, "NCOLS", 2)
    _write_mesh_tif(out_dir / "climo_001.tif", 1.0, (2, 2))
    assert s07.validate_outputs() is False


def test_stage07_build_doy_index_parses_dates(s07, tmp_path, monkeypatch):
    d = tmp_path / "2020"
    d.mkdir()
    (d / "mesh_20200101.tif").write_text("placeholder")
    (d / "mesh_20201231.tif").write_text("placeholder")
    (d / "mesh_bad.tif").write_text("placeholder")
    monkeypatch.setattr(s07, "IN_DIR", tmp_path)
    idx = s07.build_doy_index()
    assert 1 in idx
    assert 366 in idx


def test_stage07_workers_default(s07):
    args = s07.build_arg_parser().parse_args([])
    assert args.workers == 4


def test_stage07_classify_mesh_era(s07):
    from datetime import date

    assert s07.classify_mesh_era(date(2010, 6, 1)) == "MYRORSS"
    assert s07.classify_mesh_era(date(2015, 6, 1)) == "GridRad"
    assert s07.classify_mesh_era(date(2021, 6, 1)) == "MRMS"
    assert s07.classify_mesh_era(s07.GRIDRAD_END) == "GridRad"
    assert s07.classify_mesh_era(s07.MRMS_START) == "MRMS"


def test_stage07_summarize_input_coverage(s07, tmp_path):
    from datetime import date

    paths = [
        tmp_path / "2010" / "mesh_20100601.tif",
        tmp_path / "2015" / "mesh_20150601.tif",
        tmp_path / "2021" / "mesh_20210601.tif",
        tmp_path / "bad" / "mesh_notadate.tif",
    ]
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    summary = s07.summarize_input_coverage(paths)
    assert summary["n_files"] == 4
    assert summary["eras"]["MYRORSS"] == 1
    assert summary["eras"]["GridRad"] == 1
    assert summary["eras"]["MRMS"] == 1
    assert min(summary["years"]) == 2010


def test_stage07_build_climatology_small_grid(s07, tmp_path, monkeypatch):
    nrows, ncols = 2, 2
    monkeypatch.setattr(s07, "NROWS", nrows)
    monkeypatch.setattr(s07, "NCOLS", ncols)
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    monkeypatch.setattr(s07, "IN_DIR", in_dir)
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    _patch_write_geotiff(s07, monkeypatch)

    _write_mesh_tif(in_dir / "2015" / "mesh_20150701.tif", 10.0, (nrows, ncols))
    _write_mesh_tif(in_dir / "2017" / "mesh_20170701.tif", 20.0, (nrows, ncols))
    _write_mesh_tif(in_dir / "2019" / "mesh_20190701.tif", 30.0, (nrows, ncols))
    _write_mesh_tif(in_dir / "2015" / "mesh_20150219.tif", 5.0, (nrows, ncols))

    s07.build_climatology._workers = 2  # type: ignore[attr-defined]
    s07.build_climatology()

    doy182 = out_dir / "climo_182.tif"
    assert doy182.exists()
    with rasterio.open(doy182) as src:
        assert src.height == nrows
        assert float(src.read(1).mean()) == pytest.approx(20.0)
    assert (out_dir / "annual_mean_mesh75.tif").exists()
    assert (out_dir / "annual_hail_days.tif").exists()
    assert len(list(out_dir.glob("climo_???.tif"))) == 366


def test_stage07_build_climatology_single_file_read_failure(s07, tmp_path, monkeypatch):
    nrows, ncols = 2, 2
    monkeypatch.setattr(s07, "NROWS", nrows)
    monkeypatch.setattr(s07, "NCOLS", ncols)
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    monkeypatch.setattr(s07, "IN_DIR", in_dir)
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    _patch_write_geotiff(s07, monkeypatch)

    bad = in_dir / "2015" / "mesh_20150701.tif"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"not-a-tiff")

    s07.build_climatology()
    with rasterio.open(out_dir / "climo_182.tif") as src:
        assert float(src.read(1).max()) == 0.0


def test_stage07_build_climatology_parallel_fallback(s07, tmp_path, monkeypatch):
    nrows, ncols = 2, 2
    monkeypatch.setattr(s07, "NROWS", nrows)
    monkeypatch.setattr(s07, "NCOLS", ncols)
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"

    _write_mesh_tif(in_dir / "2015" / "mesh_20150701.tif", 10.0, (nrows, ncols))
    _write_mesh_tif(in_dir / "2017" / "mesh_20170701.tif", 20.0, (nrows, ncols))

    class BoomPool:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def map(self, *args, **kwargs):
            raise RuntimeError("pool failed")

    monkeypatch.setattr(s07, "IN_DIR", in_dir)
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    _patch_write_geotiff(s07, monkeypatch)
    monkeypatch.setattr(s07, "ThreadPoolExecutor", BoomPool)
    s07.build_climatology._workers = 4  # type: ignore[attr-defined]
    s07.build_climatology()
    with rasterio.open(out_dir / "climo_182.tif") as src:
        assert float(src.read(1).mean()) == pytest.approx(15.0)


def test_stage07_make_seasonal_figure(s07, tmp_path, monkeypatch):
    nrows, ncols = 2, 2
    out_dir = tmp_path / "climo"
    fig_dir = tmp_path / "figures"
    out_dir.mkdir()
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    monkeypatch.setattr(s07, "FIG_DIR", fig_dir)

    for doy in (1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335):
        _write_mesh_tif(out_dir / f"climo_{doy:03d}.tif", float(doy), (nrows, ncols))

    s07.make_seasonal_figure()
    assert (fig_dir / "seasonal_hail_activity.png").exists()


def test_stage07_validate_outputs_branches(s07, tmp_path, monkeypatch):
    out_dir = tmp_path / "climo"
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    monkeypatch.setattr(s07, "NROWS", 2)
    monkeypatch.setattr(s07, "NCOLS", 2)

    assert s07.validate_outputs() is False

    out_dir.mkdir()
    for doy in range(1, 367):
        _write_mesh_tif(out_dir / f"climo_{doy:03d}.tif", 1.0, (2, 2))
    assert s07.validate_outputs() is True

    _write_mesh_tif(out_dir / "climo_001.tif", 1.0, (3, 3))
    assert s07.validate_outputs() is False

    for doy in range(1, 367):
        _write_mesh_tif(out_dir / f"climo_{doy:03d}.tif", 1.0, (2, 2))
    (out_dir / "climo_002.tif").write_bytes(b"broken")
    assert s07.validate_outputs() is False


def test_stage07_main_validate_and_full_run(s07, tmp_path, monkeypatch):
    nrows, ncols = 2, 2
    monkeypatch.setattr(s07, "NROWS", nrows)
    monkeypatch.setattr(s07, "NCOLS", ncols)
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    fig_dir = tmp_path / "figures"
    monkeypatch.setattr(s07, "IN_DIR", in_dir)
    monkeypatch.setattr(s07, "OUT_DIR", out_dir)
    monkeypatch.setattr(s07, "FIG_DIR", fig_dir)
    _patch_write_geotiff(s07, monkeypatch)

    with pytest.raises(SystemExit) as exc:
        s07.main(["--validate"])
    assert exc.value.code == 1

    _write_mesh_tif(in_dir / "2015" / "mesh_20150701.tif", 12.0, (nrows, ncols))
    with pytest.raises(SystemExit) as exc:
        s07.main(["--workers", "1"])
    assert exc.value.code == 0
    assert len(list(out_dir.glob("climo_???.tif"))) == 366
    assert (fig_dir / "seasonal_hail_activity.png").exists()
