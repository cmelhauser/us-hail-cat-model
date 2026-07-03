"""Unit tests for shared raster and manifest helpers in scripts/_io.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio

from scripts._config import LAT_MAX, LON_MIN, NCOLS, NROWS
from scripts._io import (
    haversine_km,
    latlon_to_grid,
    sanitize_hail_values,
    summarize_mesh_output_raster,
    write_geotiff,
)


def test_write_geotiff_roundtrip_with_tags(tmp_path: Path):
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[10, 20] = 42.5
    out = tmp_path / "mesh_test.tif"
    write_geotiff(data, out, tags={"MAX_MESH75_MM": "42.5", "ACTIVE_CELLS": "1"})
    assert out.exists()
    with rasterio.open(out) as src:
        assert src.crs.to_epsg() == 4326
        assert float(src.read(1)[10, 20]) == pytest.approx(42.5)
        assert src.tags().get("MAX_MESH75_MM") == "42.5"


def test_summarize_mesh_output_raster_active_and_empty(tmp_path: Path):
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[5, 5] = 55.0
    data[5, 6] = 400.0  # above QA cap — excluded from active set
    path = tmp_path / "mesh.tif"
    write_geotiff(data, path)
    active, peak = summarize_mesh_output_raster(path)
    assert active == 1
    assert peak == 55.0

    empty = tmp_path / "empty.tif"
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), empty)
    assert summarize_mesh_output_raster(empty) == (0, 0.0)


def test_sanitize_hail_values_resets_bad_pixels():
    arr = np.array([[-1.0, 50.0, 301.0, np.nan]], dtype=np.float32)
    cleaned, n_bad = sanitize_hail_values(arr, max_hail_mm=300.0, nodata=0.0)
    assert n_bad == 3
    assert cleaned.tolist() == [[0.0, 50.0, 0.0, 0.0]]


def test_latlon_to_grid_and_haversine():
    row, col = latlon_to_grid(LAT_MAX - 0.025, LON_MIN + 0.025)
    assert row == 0
    assert col == 0
    dist = haversine_km(40.0, -100.0, 40.0, -99.0)
    assert 80.0 < dist < 90.0
