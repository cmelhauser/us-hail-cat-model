"""
_mapping.py — Lambert Conformal CONUS maps with admin boundaries.

Shared helpers for Stage 14 and diagnostic scripts. Raster data are plotted in
EPSG:4326 (cell edges from ``_config`` grid constants) on a Lambert Conformal
Conic projection. Boundaries: **admin_0** country outlines (Natural Earth) and
**admin_1** US state lines (``cartopy.feature.STATES``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

try:
    from _config import DX, LAT_MAX, LON_MIN, NCOLS, NROWS
except ImportError:  # pragma: no cover
    from scripts._config import DX, LAT_MAX, LON_MIN, NCOLS, NROWS

# [west, east, south, north] in Plate Carrée degrees
CONUS_EXTENT_PC: tuple[float, float, float, float] = (-125.0, -66.0, 24.0, 50.0)


def has_cartopy() -> bool:
    try:
        import cartopy  # noqa: F401

        return True
    except ImportError:
        return False


def conus_projection():
    """Lambert Conformal Conic tuned for the CONUS domain."""
    import cartopy.crs as ccrs

    return ccrs.LambertConformal(
        central_longitude=-96.0,
        central_latitude=39.0,
        standard_parallels=(33.0, 45.0),
    )


def plate_carree():
    import cartopy.crs as ccrs

    return ccrs.PlateCarree()


def lon_lat_edges() -> tuple[np.ndarray, np.ndarray]:
    """Cell-edge longitude and latitude vectors (length NCOLS+1, NROWS+1)."""
    lon_edges = LON_MIN + np.arange(NCOLS + 1, dtype=np.float64) * DX
    lat_edges = LAT_MAX - np.arange(NROWS + 1, dtype=np.float64) * DX
    return lon_edges, lat_edges


def lon_lat_centers() -> tuple[np.ndarray, np.ndarray]:
    """Cell-center longitude and latitude vectors."""
    lon_edges, lat_edges = lon_lat_edges()
    lons = (lon_edges[:-1] + lon_edges[1:]) / 2.0
    lats = (lat_edges[:-1] + lat_edges[1:]) / 2.0
    return lons, lats


def add_admin_boundaries(ax, *, zorder_countries: int = 4, zorder_states: int = 5) -> None:
    """Draw admin_0 country lines and United States admin_1 state lines."""
    import cartopy.feature as cfeature

    countries = cfeature.NaturalEarthFeature(
        "cultural",
        "admin_0_boundary_lines_land",
        "10m",
        facecolor="none",
        edgecolor="#333333",
        linewidth=0.6,
    )
    ax.add_feature(countries, zorder=zorder_countries)

    # United States state lines (admin_1). cartopy STATES is US-only.
    ax.add_feature(
        cfeature.STATES.with_scale("10m"),
        linewidth=0.35,
        edgecolor="#888888",
        zorder=zorder_states,
    )


def style_conus_axis(ax, *, draw_boundaries: bool = True) -> None:
    """Set CONUS extent and optional admin boundaries on a geo axis."""
    ax.set_extent(CONUS_EXTENT_PC, crs=plate_carree())
    if draw_boundaries:
        add_admin_boundaries(ax)


def create_conus_axes(
    nrows: int = 1,
    ncols: int = 1,
    *,
    figsize: tuple[float, float] | None = None,
    sharex: bool = False,
    sharey: bool = False,
    draw_boundaries: bool = True,
):
    """
    Create a figure with Lambert Conformal geo axes.

    Returns ``(fig, axes)`` where ``axes`` is a single Axes or ndarray.
    Falls back to plain matplotlib axes when cartopy is unavailable.
    """
    import matplotlib.pyplot as plt

    if figsize is None:
        width = 4.5 * ncols + 1.0
        height = 4.0 * nrows + 0.5
        figsize = (width, height)

    if has_cartopy():
        projection = conus_projection()
        fig, axes = plt.subplots(
            nrows,
            ncols,
            figsize=figsize,
            sharex=sharex,
            sharey=sharey,
            subplot_kw={"projection": projection},
        )
        flat = np.atleast_1d(axes).ravel()
        for ax in flat:
            style_conus_axis(ax, draw_boundaries=draw_boundaries)
        return fig, axes

    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=figsize,
        sharex=sharex,
        sharey=sharey,
    )
    return fig, axes


def plot_raster_on_axis(
    ax,
    data: np.ndarray,
    *,
    cmap: str = "YlOrRd",
    vmin: float | None = None,
    vmax: float | None = None,
    symmetric: bool = False,
) -> Any:
    """
    Plot an (NROWS, NCOLS) raster on ``ax``.

    Uses ``imshow`` with Plate Carrée cell-edge extent on Lambert geo axes when
    cartopy is available; otherwise plain ``imshow`` with geographic extent.
    """
    arr = np.asarray(data, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if symmetric:
        lim = float(np.nanpercentile(np.abs(finite), 99)) if finite.size else 1.0
        vmin = -lim if vmin is None else vmin
        vmax = lim if vmax is None else vmax
    else:
        if vmin is None:
            vmin = 0.0
        if vmax is None and finite.size:
            pos = finite[finite > 0] if float(np.nanmin(finite)) >= 0 else finite
            vmax = float(np.nanpercentile(pos, 99)) if pos.size else 1.0
        elif vmax is None:
            vmax = 1.0

    lon_edges, lat_edges = lon_lat_edges()
    extent = [lon_edges[0], lon_edges[-1], lat_edges[-1], lat_edges[0]]

    if has_cartopy() and hasattr(ax, "projection"):
        import cartopy.crs as ccrs

        return ax.imshow(
            arr,
            origin="upper",
            extent=extent,
            transform=ccrs.PlateCarree(),
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            interpolation="nearest",
            rasterized=True,
        )

    return ax.imshow(
        arr,
        origin="upper",
        extent=extent,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        aspect="auto",
        interpolation="nearest",
    )


def save_conus_raster_map(
    data: np.ndarray,
    out_path: Path | str,
    *,
    title: str = "",
    cbar_label: str = "",
    cmap: str = "YlOrRd",
    vmin: float | None = None,
    vmax: float | None = None,
    symmetric: bool = False,
    figsize: tuple[float, float] = (10.0, 5.5),
    dpi: int = 150,
) -> Path:
    """Render a single-panel CONUS raster map and save to ``out_path``."""
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = create_conus_axes(figsize=figsize)
    if not isinstance(ax, np.ndarray):
        geo_ax = ax
    else:
        geo_ax = ax.ravel()[0]

    mappable = plot_raster_on_axis(
        geo_ax,
        data,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        symmetric=symmetric,
    )
    if title:
        geo_ax.set_title(title)
    if cbar_label:
        fig.colorbar(mappable, ax=geo_ax, label=cbar_label, shrink=0.8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_path


def default_conus_mask_path() -> Path:
    """Default Stage 12 CONUS land mask GeoTIFF."""
    try:
        from _config import DATA_ROOT
    except ImportError:  # pragma: no cover
        from scripts._config import DATA_ROOT

    return DATA_ROOT / "analysis" / "conus_mask" / "conus_mask.tif"


def apply_conus_mask_to_raster(
    data: np.ndarray,
    mask_path: Path | str | None = None,
) -> np.ndarray:
    """Zero cells outside the CONUS land mask when the mask GeoTIFF exists."""
    import rasterio

    arr = np.asarray(data, dtype=np.float32)
    mask_file = Path(mask_path) if mask_path is not None else default_conus_mask_path()
    if not mask_file.is_file():
        return arr
    with rasterio.open(mask_file) as msrc:
        mask = msrc.read(1) > 0
    if mask.shape != arr.shape:
        return arr
    return np.where(mask, arr, 0.0).astype(np.float32)


def load_conus_raster_for_map(
    tif_path: Path | str,
    *,
    mask_path: Path | str | None = None,
    scale: float = 1.0,
    zero_to_nan: bool = False,
) -> np.ndarray:
    """Load a model-grid GeoTIFF and optionally apply the CONUS mask."""
    import rasterio

    tif_path = Path(tif_path)
    with rasterio.open(tif_path) as src:
        data = src.read(1).astype(np.float32)

    data = apply_conus_mask_to_raster(data, mask_path)

    if scale != 1.0:
        data = data * np.float32(scale)

    if zero_to_nan:
        data = data.astype(np.float32, copy=False)
        data[data <= 0] = np.nan

    return data


def save_conus_map_from_tif(
    tif_path: Path | str,
    out_path: Path | str,
    *,
    title: str = "",
    cbar_label: str = "",
    cmap: str = "YlOrRd",
    vmin: float | None = None,
    vmax: float | None = None,
    symmetric: bool = False,
    mask_path: Path | str | None = None,
    scale: float = 1.0,
    zero_to_nan: bool = False,
    figsize: tuple[float, float] = (10.0, 5.5),
    dpi: int = 150,
) -> Path:
    """Render a model-grid GeoTIFF to a Lambert Conformal CONUS map PNG."""
    data = load_conus_raster_for_map(
        tif_path,
        mask_path=mask_path,
        scale=scale,
        zero_to_nan=zero_to_nan,
    )
    return save_conus_raster_map(
        data,
        out_path,
        title=title,
        cbar_label=cbar_label,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        symmetric=symmetric,
        figsize=figsize,
        dpi=dpi,
    )
