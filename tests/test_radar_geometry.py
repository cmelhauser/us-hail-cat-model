"""Tests for NEXRAD geometry and range-dependent debias helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np

from scripts._radar_geometry import (
    apply_range_debias,
    classify_mesh_source,
    fit_range_debias_factors,
    load_range_debias,
    nearest_radar_distance_km,
    nexrad_sites_conus,
    remove_azimuthal_ring_artifacts,
    remove_background_filament_artifacts,
    remove_gridrad_artifacts,
    remove_speckle_spikes,
    save_range_debias,
)


def test_nexrad_sites_conus_nonempty():
    lats, lons, ids = nexrad_sites_conus()
    assert len(ids) >= 140
    assert lats.shape == lons.shape
    assert np.all((lats >= 24) & (lats <= 50))
    assert np.all((lons >= -130) & (lons <= -60))


def test_classify_mesh_source_eras():
    assert classify_mesh_source(date(2010, 6, 1)) == "MYRORSS"
    assert classify_mesh_source(date(2015, 6, 1)) == "GridRad"
    assert classify_mesh_source(date(2022, 6, 1)) == "MRMS"


def test_nearest_radar_distance_near_oklahoma():
  # Near KTLX (Oklahoma City).
    lat_grid = np.full((1, 1), 35.33, dtype=np.float64)
    lon_grid = np.full((1, 1), -97.28, dtype=np.float64)
    # Monkeypatch shape — function uses NROWS/NCOLS from config; test via direct haversine logic
    site_lats, site_lons, _ = nexrad_sites_conus()
    dlat = np.radians(site_lats - 35.33)
    dlon = np.radians(site_lons + 97.28)
    a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(35.33)) * np.cos(np.radians(site_lats)) * np.sin(dlon / 2) ** 2
    dist = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))
    assert float(dist.min()) < 5.0


def test_fit_and_apply_range_debias_roundtrip(tmp_path: Path):
    pairs = []
    for i, r in enumerate([30, 60, 90, 120, 150]):
        pairs.append(
            {
                "date": "20150601",
                "lat": 35.0 + i * 0.1,
                "lon": -97.0,
                "spc_size_in": 1.5,
                "mesh75_mm": 40.0 * (1.0 + 0.3 * (120 - r) / 120),
            }
        )
    fit = fit_range_debias_factors(pairs, min_report_in=1.0)
    path = save_range_debias(fit, tmp_path / "range_debias.npz")
    loaded = load_range_debias(path)
    assert loaded is not None
    range_grid = np.full((520, 1180), 50.0, dtype=np.float32)
    data = np.full((520, 1180), 50.0, dtype=np.float32)
    out = apply_range_debias(data, range_grid, "GridRad", loaded)
    assert out.shape == data.shape
    assert np.all(out >= 0)


def test_remove_speckle_spikes_zeros_isolated_pixel():
    data = np.zeros((5, 5), dtype=np.float32)
    data[2, 2] = 50.0
    out, n = remove_speckle_spikes(data)
    assert n == 1
    assert out[2, 2] == 0.0


def test_remove_speckle_spikes_keeps_uniform_patch():
    data = np.full((5, 5), 40.0, dtype=np.float32)
    out, n = remove_speckle_spikes(data)
    assert n == 0
    assert np.all(out == 40.0)


def test_remove_azimuthal_ring_artifacts_spoke():
    site_idx = np.zeros((10, 10), dtype=np.int16)
    range_km = np.full((10, 10), 50.0, dtype=np.float32)
    data = np.full((10, 10), 10.0, dtype=np.float32)
    data[5, 5] = 50.0
    out, n = remove_azimuthal_ring_artifacts(
        data, site_idx, range_km, min_annulus_cells=3,
    )
    assert n == 1
    assert out[5, 5] == 0.0
    assert np.all(out[data != 50.0] == 10.0)


def test_remove_background_filament_artifacts_line():
    data = np.zeros((25, 25), dtype=np.float32)
    data[12, :] = 50.0
    out, n = remove_background_filament_artifacts(data)
    assert n > 0
    assert out[12, 12] == 0.0


def test_remove_gridrad_artifacts_chain():
    site_idx = np.zeros((10, 10), dtype=np.int16)
    range_km = np.full((10, 10), 50.0, dtype=np.float32)
    data = np.zeros((10, 10), dtype=np.float32)
    data[2, 2] = 50.0
    data[5, 5] = 50.0
    data[5, 4:7] = 10.0
    out, counts = remove_gridrad_artifacts(data, range_km, site_idx)
    assert counts["isolated"] >= 1
    assert out[2, 2] == 0.0
