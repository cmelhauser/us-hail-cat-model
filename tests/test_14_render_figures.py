from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from conftest import load_stage
from scripts._config import DX, LAT_MAX, LON_MIN, NCOLS, NROWS


def test_stage14_validate_outputs_detects_missing_figures(tmp_path, monkeypatch):
    s = load_stage("14_render_figures.py")
    monkeypatch.setattr(s, "FIG_HIST", tmp_path / "historical")
    monkeypatch.setattr(s, "FIG_STOCH", tmp_path / "stochastic")
    monkeypatch.setattr(s, "FIG_ANAL", tmp_path / "analysis")
    assert s.validate_outputs() is False


@pytest.mark.skipif(
    __import__("scripts._mapping", fromlist=["has_cartopy"]).has_cartopy() is False,
    reason="cartopy not installed",
)
def test_render_rp_map_writes_lambert_png(tmp_path, monkeypatch):
    s = load_stage("14_render_figures.py")
    monkeypatch.setattr(s, "MASK_DIR", tmp_path / "missing_mask")

    tif = tmp_path / "rp.tif"
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[200:220, 400:420] = 50.0
    transform = from_origin(LON_MIN, LAT_MAX, DX, DX)
    profile = {
        "driver": "GTiff",
        "height": NROWS,
        "width": NCOLS,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    with rasterio.open(tif, "w", **profile) as dst:
        dst.write(data, 1)

    out = tmp_path / "rp.png"
    s.render_rp_map(tif, out, "Test RP map")
    assert out.exists()
    assert out.stat().st_size > 1000
