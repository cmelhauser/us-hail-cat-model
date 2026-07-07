"""Tests for CONUS map helpers."""

from __future__ import annotations

import numpy as np
import pytest

from scripts._config import NROWS, NCOLS
from scripts import _mapping as mp


def test_lon_lat_edges_shape():
    lons, lats = mp.lon_lat_edges()
    assert lons.shape == (NCOLS + 1,)
    assert lats.shape == (NROWS + 1,)


def test_conus_extent_order():
    west, east, south, north = mp.CONUS_EXTENT_PC
    assert west < east
    assert south < north


@pytest.mark.skipif(not mp.has_cartopy(), reason="cartopy not installed")
def test_conus_projection_is_lambert():
    import cartopy.crs as ccrs

    proj = mp.conus_projection()
    assert isinstance(proj, ccrs.LambertConformal)


@pytest.mark.skipif(not mp.has_cartopy(), reason="cartopy not installed")
def test_save_conus_raster_map(tmp_path):
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[100:120, 200:220] = 40.0
    out = tmp_path / "test_map.png"
    mp.save_conus_raster_map(data, out, title="Test", cbar_label="mm")
    assert out.exists()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not mp.has_cartopy(), reason="cartopy not installed")
def test_create_conus_axes_has_projection():
    import matplotlib.pyplot as plt

    fig, ax = mp.create_conus_axes()
    try:
        import cartopy.crs as ccrs

        assert hasattr(ax, "projection")
        assert isinstance(ax.projection, ccrs.LambertConformal)
    finally:
        plt.close(fig)


@pytest.mark.skipif(not mp.has_cartopy(), reason="cartopy not installed")
def test_plot_raster_on_axis_symmetric():
    import matplotlib.pyplot as plt

    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[50, 50] = 10.0
    data[51, 51] = -8.0
    fig, ax = mp.create_conus_axes(figsize=(6, 4))
    try:
        m = mp.plot_raster_on_axis(ax, data, cmap="RdBu_r", symmetric=True)
        assert m is not None
    finally:
        plt.close(fig)
