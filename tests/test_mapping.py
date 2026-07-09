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


@pytest.mark.skipif(not mp.has_cartopy(), reason="cartopy not installed")
def test_save_conus_map_from_tif(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    from scripts._config import DX, LAT_MAX, LON_MIN, NCOLS, NROWS

    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[100:120, 200:220] = 50.0
    tif = tmp_path / "input.tif"
    with rasterio.open(
        tif,
        "w",
        driver="GTiff",
        height=NROWS,
        width=NCOLS,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON_MIN, LAT_MAX, DX, DX),
    ) as dst:
        dst.write(data, 1)

    out = tmp_path / "lambert_map.png"
    mp.save_conus_map_from_tif(tif, out, title="From TIF", cbar_label="mm")
    assert out.exists()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not mp.has_cartopy(), reason="cartopy not installed")
def test_plot_raster_uses_plate_carree_edge_extent():
    import matplotlib.pyplot as plt
    from matplotlib.image import AxesImage

    from scripts._io import latlon_to_grid

    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    lat, lon = 35.5, -97.5
    row, col = latlon_to_grid(lat, lon)
    data[row, col] = 80.0

    lon_e, lat_e = mp.lon_lat_edges()

    fig, ax = mp.create_conus_axes(figsize=(10, 5.5))
    try:
        artist = mp.plot_raster_on_axis(ax, data, cmap="YlOrRd", vmin=0, vmax=80)
        assert isinstance(artist, AxesImage)

        ax.scatter([lon], [lat], transform=mp.plate_carree(), c="blue", s=60, marker="x", zorder=10)
        fig.canvas.draw()
        marker_disp = ax.transData.transform(
            ax.projection.transform_point(lon, lat, mp.plate_carree())[:2]
        )
        cell_lon = (lon_e[col] + lon_e[col + 1]) / 2.0
        cell_lat = (lat_e[row] + lat_e[row + 1]) / 2.0
        cell_disp = ax.transData.transform(
            ax.projection.transform_point(cell_lon, cell_lat, mp.plate_carree())[:2]
        )
        assert np.allclose(marker_disp, cell_disp, atol=0.5)
    finally:
        plt.close(fig)
