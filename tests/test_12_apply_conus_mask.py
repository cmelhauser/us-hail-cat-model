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
