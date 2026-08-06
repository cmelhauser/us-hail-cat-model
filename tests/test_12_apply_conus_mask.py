from pathlib import Path

import numpy as np
import pytest


def test_stage12_uniform_topo_when_dem_missing(load_script, tmp_path, monkeypatch):
    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "TOPO_DIR", tmp_path)
    monkeypatch.setattr(s, "write_geotiff", lambda data, path: path.write_bytes(b"ok"))
    out = s.build_topo_correction()
    assert out.shape == (s.NROWS, s.NCOLS)
    assert np.all(out == 1.0)


def test_stage12_validate_fails_when_mask_missing(load_script, tmp_path, monkeypatch):
    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "MASK_DIR", tmp_path)
    assert s.validate_outputs() is False


def test_stage12_workers_default(load_script):
    s = load_script("12_apply_conus_mask.py")
    args = s.build_arg_parser().parse_args([])
    assert args.workers == 4


def test_stage12_mask_rewrites_geotiff_atomically(load_script, tmp_path):
    import rasterio
    import stat
    from rasterio.transform import from_origin

    s = load_script("12_apply_conus_mask.py")
    path = tmp_path / "rp_00100yr_hail.tif"
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-100, 40, 0.05, 0.05),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.array([[10, 20], [30, 40]], dtype=np.float32), 1)
    path.chmod(0o640)

    s._mask_one(
        path,
        np.array([[False, True], [False, False]]),
        np.full((2, 2), 1.1, dtype=np.float32),
    )

    with rasterio.open(path) as src:
        np.testing.assert_allclose(
            src.read(1), [[11.0, 0.0], [33.0, 44.0]]
        )
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))


def test_stage12_atomic_rewrite_preserves_target_on_write_failure(
    load_script, tmp_path, monkeypatch
):
    import rasterio

    s = load_script("12_apply_conus_mask.py")
    path = tmp_path / "target.tif"
    path.write_bytes(b"original")

    def fail_open(*_args, **_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(rasterio, "open", fail_open)
    with pytest.raises(RuntimeError, match="write failed"):
        s._write_raster_atomic(path, np.zeros((1, 1), dtype=np.float32), {})

    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))


def test_stage12_build_conus_mask(load_script, tmp_path, monkeypatch):
    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "NROWS", 4)
    monkeypatch.setattr(s, "NCOLS", 4)
    monkeypatch.setattr(s, "MASK_DIR", tmp_path)
    monkeypatch.setattr(s, "write_geotiff", lambda data, path: Path(path).write_bytes(b"mask"))
    mask = s.build_conus_mask()
    assert mask.shape == (4, 4)
    assert mask.dtype == bool


def test_stage12_build_topo_with_dem(load_script, tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "NROWS", 2)
    monkeypatch.setattr(s, "NCOLS", 2)
    monkeypatch.setattr(s, "TOPO_DIR", tmp_path)
    dem = tmp_path / "elevation_0.05deg.tif"
    with rasterio.open(
        dem,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-100, 40, 0.05, 0.05),
    ) as dst:
        dst.write(np.array([[0.0, 1000.0], [2000.0, 3000.0]], dtype=np.float32), 1)
    written = []

    def capture(data, path):
        written.append(Path(path).name)
        Path(path).write_bytes(b"topo")

    monkeypatch.setattr(s, "write_geotiff", capture)
    corr = s.build_topo_correction()
    assert corr.shape == (2, 2)
    assert corr.max() > 1.0
    assert "topo_correction.tif" in written


def test_stage12_apply_mask_sequential_and_parallel(load_script, tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "NROWS", 2)
    monkeypatch.setattr(s, "NCOLS", 2)
    monkeypatch.setattr(s, "CDF_DIR", tmp_path / "cdf")
    monkeypatch.setattr(s, "OCC_DIR", tmp_path / "occ")
    monkeypatch.setattr(s, "STOCH_MAP_DIR", tmp_path / "stoch")
    for d in (s.CDF_DIR, s.OCC_DIR, s.STOCH_MAP_DIR):
        d.mkdir(parents=True)
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-100, 40, 0.05, 0.05),
    }
    rp = s.CDF_DIR / "rp_00100yr_hail_smooth.tif"
    occ = s.OCC_DIR / "p_occ_1p00in.tif"
    with rasterio.open(rp, "w", **profile) as dst:
        dst.write(np.ones((2, 2), dtype=np.float32), 1)
    with rasterio.open(occ, "w", **profile) as dst:
        dst.write(np.ones((2, 2), dtype=np.float32), 1)

    conus = np.array([[True, False], [True, True]])
    topo = np.ones((2, 2), dtype=np.float32)
    s.apply_mask_to_rasters(conus, topo, workers=1)
    s.apply_mask_to_rasters(conus, topo, workers=4)


def test_stage12_validate_passes(load_script, tmp_path, monkeypatch):
    s = load_script("12_apply_conus_mask.py")
    mask = tmp_path / "conus_mask.tif"
    mask.write_bytes(b"ok")
    monkeypatch.setattr(s, "MASK_DIR", tmp_path)
    assert s.validate_outputs() is True


def test_stage12_main_validate_and_run(load_script, tmp_path, monkeypatch):
    import sys

    s = load_script("12_apply_conus_mask.py")
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["12_apply_conus_mask.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0

    monkeypatch.setattr(s, "build_conus_mask", lambda: np.ones((2, 2), dtype=bool))
    monkeypatch.setattr(s, "build_topo_correction", lambda: np.ones((2, 2), dtype=np.float32))
    monkeypatch.setattr(s, "apply_mask_to_rasters", lambda *_a, **_k: None)
    monkeypatch.setattr(sys, "argv", ["12_apply_conus_mask.py", "--workers", "2"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0
