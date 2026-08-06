from pathlib import Path

import numpy as np
import pytest
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


def test_stage11b_download_source_cached(tmp_path, monkeypatch):
    s = load_stage("11b_prepare_topography.py")
    source = tmp_path / "ETOPO_2022_v1_60s_N90W180_surface.tif"
    source.write_bytes(b"x" * s.MIN_SOURCE_BYTES)
    out = s.download_source(source)
    assert out == source


def test_stage11b_download_source_streams(tmp_path, monkeypatch):
    import requests

    s = load_stage("11b_prepare_topography.py")
    source = tmp_path / "ETOPO_2022_v1_60s_N90W180_surface.tif"
    chunks = [b"a" * (1024 * 1024), b"b" * (1024 * 1024)]
    total = sum(len(c) for c in chunks)
    payload = b"".join(chunks) + b"c" * max(0, s.MIN_SOURCE_BYTES - total)

    class FakeResp:
        headers = {"content-length": str(len(payload))}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            yield from [payload[i : i + 1024 * 1024] for i in range(0, len(payload), 1024 * 1024)]

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(requests, "get", lambda *_a, **_k: FakeResp())
    out = s.download_source(source, url="https://example.invalid/dem.tif")
    assert out.stat().st_size >= s.MIN_SOURCE_BYTES


def test_stage11b_download_source_too_small_raises(tmp_path, monkeypatch):
    import requests

    s = load_stage("11b_prepare_topography.py")
    source = tmp_path / "ETOPO_2022_v1_60s_N90W180_surface.tif"

    class FakeResp:
        headers = {}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            yield b"tiny"

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(requests, "get", lambda *_a, **_k: FakeResp())
    with pytest.raises(RuntimeError, match="unexpectedly small"):
        s.download_source(source, url="https://example.invalid/dem.tif")


def test_stage11b_validate_passes_on_good_dem(tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_stage("11b_prepare_topography.py")
    monkeypatch.setattr(s, "NROWS", 2)
    monkeypatch.setattr(s, "NCOLS", 2)
    monkeypatch.setattr(s, "DX", 1.0)
    monkeypatch.setattr(s, "LAT_MAX", 2.0)
    monkeypatch.setattr(s, "LON_MIN", 0.0)
    elev = tmp_path / "elevation_0.05deg.tif"
    with rasterio.open(
        elev,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs=s.CRS,
        transform=from_origin(0.0, 2.0, 1.0, 1.0),
    ) as dst:
        dst.write(np.full((2, 2), 3500.0, dtype=np.float32), 1)
    monkeypatch.setattr(s, "ELEVATION_TIF", elev)
    assert s.validate_outputs() is True


def test_stage11b_main_validate_only(tmp_path, monkeypatch):
    import sys

    s = load_stage("11b_prepare_topography.py")
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["11b_prepare_topography.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


def test_stage11b_main_full_pipeline(tmp_path, monkeypatch):
    import sys

    s = load_stage("11b_prepare_topography.py")
    source = tmp_path / "source.tif"
    source.write_bytes(b"x" * s.MIN_SOURCE_BYTES)
    elev = tmp_path / "elevation_0.05deg.tif"
    monkeypatch.setattr(s, "download_source", lambda *_a, **_k: source)
    monkeypatch.setattr(s, "build_model_grid_dem", lambda *_a, **_k: elev)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["11b_prepare_topography.py"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0
