from pathlib import Path

import numpy as np
from conftest import load_stage


def test_stage11b_sanitizes_elevation():
    s = load_stage("11b_prepare_topography.py")
    raw = np.array([[-10.0, 0.0, 100.0, np.nan, np.inf]], dtype=np.float32)
    out = s.sanitize_elevation_m(raw)
    assert np.isfinite(out).all()
    assert out.min() >= 0.0
    assert out[0, 2] == 100.0


def test_stage11b_build_model_grid_dem_from_synthetic_source(tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_stage("11b_prepare_topography.py")
    monkeypatch.setattr(s, "NROWS", 2)
    monkeypatch.setattr(s, "NCOLS", 2)
    monkeypatch.setattr(s, "DX", 1.0)
    monkeypatch.setattr(s, "LAT_MAX", 2.0)
    monkeypatch.setattr(s, "LON_MIN", 0.0)

    source = tmp_path / "source.tif"
    source_profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": 2,
        "height": 2,
        "count": 1,
        "crs": "EPSG:4326",
        "transform": from_origin(0.0, 2.0, 1.0, 1.0),
        "nodata": None,
    }
    with rasterio.open(source, "w", **source_profile) as dst:
        dst.write(np.array([[100.0, 200.0], [-50.0, 400.0]], dtype=np.float32), 1)

    out = tmp_path / "elevation_0.05deg.tif"
    s.build_model_grid_dem(source, out)

    with rasterio.open(out) as src:
        data = src.read(1)
        tags = src.tags()

    assert data.shape == (2, 2)
    assert data.min() >= 0.0
    assert data.max() == 400.0
    assert "ETOPO 2022" in tags["source"]
    assert tags["doi"] == s.ETOPO_2022_DOI


def test_stage11b_validate_fails_when_missing(tmp_path, monkeypatch):
    s = load_stage("11b_prepare_topography.py")
    monkeypatch.setattr(s, "ELEVATION_TIF", Path(tmp_path) / "missing.tif")
    assert s.validate_outputs() is False
