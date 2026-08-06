"""Extended tests for scripts/10_build_smooth_cdf.py."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from conftest import load_stage


@pytest.fixture
def s10():
    return load_stage("10_build_smooth_cdf.py")


def test_stage10_haversine_zero_and_positive(s10):
    assert s10.haversine_km(40, -100, 40, -100) == 0
    assert s10.haversine_km(40, -100, 41, -100) > 100


def test_stage10_return_period_value_branches(s10):
    val = s10.return_period_value(100, mu=3.2, sigma=0.4, xi_gpd=0.1, sigma_gpd=10, thresh=50.8, p_occ=0.5)
    assert val >= 0
    assert s10.return_period_value(100, 3.2, 0.4, 0.1, 10, 50.8, 0.0) == 0.0
    assert s10.return_period_value(100, 3.2, 0.4, 0.1, 10, 50.8, 0.001) == 0.0
    assert s10.return_period_value(100, 3.2, 0.4, 0.0, 10, 50.8, 0.5) >= 50.8


def test_build_annual_max(tmp_path, s10, monkeypatch):
    monkeypatch.setattr(s10, "NROWS", 2)
    monkeypatch.setattr(s10, "NCOLS", 2)
    mesh_dir = tmp_path / "mesh"
    ydir = mesh_dir / "2015"
    ydir.mkdir(parents=True)
    for tag, val in (("20150601", 30.0), ("20150701", 40.0)):
        path = ydir / f"mesh_{tag}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-100, 40, 0.05, 0.05),
        ) as dst:
            dst.write(np.full((2, 2), val, dtype=np.float32), 1)
    monkeypatch.setattr(s10, "MESH_DIR", mesh_dir)
    annual_max, years = s10.build_annual_max()
    assert years == [2015]
    assert float(annual_max.max()) == 40.0


def test_validate_only_missing_files(s10, tmp_path, monkeypatch):
    monkeypatch.setattr(s10, "CDF_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s10.main()
    assert exc.value.code == 1


def test_validate_only_passes(s10, tmp_path, monkeypatch):
    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    for rp in s10.RP_YEARS:
        (cdf_dir / f"rp_{rp:05d}yr_hail_smooth.tif").write_bytes(b"x")
    monkeypatch.setattr(s10, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s10.main()
    assert exc.value.code == 0


def test_main_small_grid(tmp_path, s10, monkeypatch):
    nrows, ncols = 3, 3
    monkeypatch.setattr(s10, "NROWS", nrows)
    monkeypatch.setattr(s10, "NCOLS", ncols)
    monkeypatch.setattr(s10, "LAT_MAX", 40.0)
    monkeypatch.setattr(s10, "LON_MIN", -100.0)
    monkeypatch.setattr(s10, "DX", 0.05)
    monkeypatch.setattr(s10, "POOL_RADIUS_KM", 200.0)
    monkeypatch.setattr(s10, "DECAY_KM", 75.0)
    monkeypatch.setattr(s10, "MIN_OBS", 3)
    monkeypatch.setattr(s10, "RP_YEARS", [10, 100])

    mesh_dir = tmp_path / "mesh"
    for year, val in ((2015, 60.0), (2016, 70.0), (2017, 55.0), (2018, 80.0)):
        ydir = mesh_dir / str(year)
        ydir.mkdir(parents=True)
        data = np.zeros((nrows, ncols), dtype=np.float32)
        data[1, 1] = val
        data[1, 2] = val * 0.8
        path = ydir / f"mesh_{year}0601.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=nrows,
            width=ncols,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-100, 40, 0.05, 0.05),
        ) as dst:
            dst.write(data, 1)

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    region_map = np.full((nrows, ncols), -1, dtype=np.int16)  # hit xi_gpd=0.0 branch
    region_map[1, 1] = 0
    region_xi = np.array([0.1], dtype=np.float32)
    np.savez(cdf_dir / "cdf_parameters.npz", region_map=region_map, region_xi=region_xi)

    written = []

    def capture_write(arr, out_path, **_kw):
        written.append(Path(out_path).name)
        Path(out_path).write_bytes(b"tif")

    monkeypatch.setattr(s10, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s10, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s10, "write_geotiff", capture_write)
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py"])
    s10.main()
    assert any("rp_00010yr" in n for n in written)
    assert any("p_occurrence_smooth" in n for n in written)


def test_main_validate_via_cli(s10, tmp_path, monkeypatch):
    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    for rp in s10.RP_YEARS:
        (cdf_dir / f"rp_{rp:05d}yr_hail_smooth.tif").write_bytes(b"x")
    monkeypatch.setattr(s10, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s10.main()
    assert exc.value.code == 0


def test_main_fit_progress_and_gpd_branches(s10, tmp_path, monkeypatch):
    nrows, ncols = 4, 4
    monkeypatch.setattr(s10, "NROWS", nrows)
    monkeypatch.setattr(s10, "NCOLS", ncols)
    monkeypatch.setattr(s10, "LAT_MAX", 40.0)
    monkeypatch.setattr(s10, "LON_MIN", -100.0)
    monkeypatch.setattr(s10, "DX", 0.05)
    monkeypatch.setattr(s10, "POOL_RADIUS_KM", 500.0)
    monkeypatch.setattr(s10, "DECAY_KM", 75.0)
    monkeypatch.setattr(s10, "RP_YEARS", [10, 100])
    monkeypatch.setattr(s10, "MIN_OBS", 2)

    mesh_dir = tmp_path / "mesh"
    for year, peak in ((2014, 55.0), (2015, 65.0), (2016, 75.0)):
        ydir = mesh_dir / str(year)
        ydir.mkdir(parents=True)
        data = np.zeros((nrows, ncols), dtype=np.float32)
        data[1, 1] = peak
        data[2, 2] = peak * 0.9
        path = ydir / f"mesh_{year}0601.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=nrows,
            width=ncols,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-100, 40, 0.05, 0.05),
        ) as dst:
            dst.write(data, 1)

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    region_map = np.full((nrows, ncols), -1, dtype=np.int16)
    region_map[1, 1] = 0
    region_map[2, 2] = 5
    region_xi = np.array([0.1], dtype=np.float32)
    np.savez(cdf_dir / "cdf_parameters.npz", region_map=region_map, region_xi=region_xi)

    written = []

    def capture_write(arr, out_path, **_kw):
        written.append(Path(out_path).name)
        Path(out_path).write_bytes(b"tif")

    monkeypatch.setattr(s10, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s10, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s10, "write_geotiff", capture_write)
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py"])
    s10.main()
    assert any("rp_00010yr" in n for n in written)


def test_return_period_body_branch(s10):
    # cond_ne <= p_below_u → lognormal body (line ~101)
    val = s10.return_period_value(
        2, mu=3.5, sigma=0.3, xi_gpd=0.1, sigma_gpd=10.0, thresh=50.8, p_occ=0.9
    )
    assert val is not None and val > 0


def test_main_distance_and_min_obs_skips(tmp_path, s10, monkeypatch):
    """Cover lines 191 (distance skip) and 205 (MIN_OBS continue)."""
    nrows, ncols = 4, 4
    monkeypatch.setattr(s10, "NROWS", nrows)
    monkeypatch.setattr(s10, "NCOLS", ncols)
    monkeypatch.setattr(s10, "LAT_MAX", 40.0)
    monkeypatch.setattr(s10, "LON_MIN", -100.0)
    monkeypatch.setattr(s10, "DX", 1.0)  # large cell spacing
    monkeypatch.setattr(s10, "POOL_RADIUS_KM", 0.01)  # nothing within radius except self
    monkeypatch.setattr(s10, "DECAY_KM", 75.0)
    monkeypatch.setattr(s10, "MIN_OBS", 50)
    monkeypatch.setattr(s10, "RP_YEARS", [10])

    mesh_dir = tmp_path / "mesh"
    ydir = mesh_dir / "2015"
    ydir.mkdir(parents=True)
    data = np.full((nrows, ncols), 40.0, dtype=np.float32)
    with rasterio.open(
        ydir / "mesh_20150601.tif",
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-100, 40, 1.0, 1.0),
    ) as dst:
        dst.write(data, 1)

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    np.savez(
        cdf_dir / "cdf_parameters.npz",
        region_map=np.zeros((nrows, ncols), dtype=np.int16),
        region_xi=np.array([0.1], dtype=np.float32),
    )
    monkeypatch.setattr(s10, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s10, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s10, "write_geotiff", lambda *a, **k: Path(a[1]).write_bytes(b"x"))
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py"])
    s10.main()


def test_main_gpd_fallback_and_progress_const(tmp_path, s10, monkeypatch):
    """Cover GPD else-branch (223) and progress log (235-238) via const rewrite."""
    nrows, ncols = 3, 3
    monkeypatch.setattr(s10, "NROWS", nrows)
    monkeypatch.setattr(s10, "NCOLS", ncols)
    monkeypatch.setattr(s10, "LAT_MAX", 40.0)
    monkeypatch.setattr(s10, "LON_MIN", -100.0)
    monkeypatch.setattr(s10, "DX", 0.05)
    monkeypatch.setattr(s10, "POOL_RADIUS_KM", 500.0)
    monkeypatch.setattr(s10, "DECAY_KM", 75.0)
    monkeypatch.setattr(s10, "MIN_OBS", 2)
    monkeypatch.setattr(s10, "GPD_THRESH_MM", 1000.0)  # no exceedances → line 223
    monkeypatch.setattr(s10, "RP_YEARS", [10])

    mesh_dir = tmp_path / "mesh"
    for year in (2015, 2016, 2017):
        ydir = mesh_dir / str(year)
        ydir.mkdir(parents=True)
        data = np.full((nrows, ncols), 40.0, dtype=np.float32)
        with rasterio.open(
            ydir / f"mesh_{year}0601.tif",
            "w",
            driver="GTiff",
            height=nrows,
            width=ncols,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-100, 40, 0.05, 0.05),
        ) as dst:
            dst.write(data, 1)

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    np.savez(
        cdf_dir / "cdf_parameters.npz",
        region_map=np.zeros((nrows, ncols), dtype=np.int16),
        region_xi=np.array([0.1], dtype=np.float32),
    )
    monkeypatch.setattr(s10, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s10, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s10, "write_geotiff", lambda *a, **k: Path(a[1]).write_bytes(b"x"))
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py"])

    # Rewrite progress modulus 2000 → 1 so the ETA log fires quickly.
    code = s10.main.__code__
    new_consts = tuple(1 if c == 2000 else c for c in code.co_consts)
    s10.main.__code__ = code.replace(co_consts=new_consts)
    s10.main()
