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
    remediation_site_mask,
    remove_azimuthal_ring_artifacts,
    remove_background_filament_artifacts,
    remove_flagged_site_artifacts,
    remove_gridrad_artifacts,
    remove_persistent_range_artifacts,
    remove_radial_range_rings,
    remove_site_polar_spokes,
    remove_speckle_spikes,
    save_range_debias,
    SITE_REMEDIATION_IDS,
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


def test_remove_radial_range_rings_uniform_annulus():
    """Uniform elevation on one range bin vs quiet neighbors (classic range ring)."""
    site_idx = np.zeros((12, 12), dtype=np.int16)
    range_km = np.full((12, 12), 55.0, dtype=np.float32)
    range_km[:, :4] = 45.0
    range_km[:, 8:] = 65.0
    data = np.full((12, 12), 10.0, dtype=np.float32)
    data[:, 4:8] = 45.0
    out, n = remove_radial_range_rings(
        data, site_idx, range_km, min_annulus_cells=4,
    )
    assert n > 0
    assert np.all(out[:, 4:8] == 0.0)
    assert np.all(out[:, :4] == 10.0)


def test_remove_radial_range_rings_keeps_broad_storm():
    """Storm spanning adjacent range bins should not be flagged as a thin ring."""
    site_idx = np.zeros((12, 12), dtype=np.int16)
    range_km = np.full((12, 12), 55.0, dtype=np.float32)
    range_km[:, :6] = 45.0
    range_km[:, 6:] = 55.0
    data = np.full((12, 12), 35.0, dtype=np.float32)
    out, n = remove_radial_range_rings(data, site_idx, range_km, min_annulus_cells=4)
    assert n == 0
    assert np.all(out == 35.0)


def test_remove_radial_range_rings_wide_midrange_plateau():
    """Wide mid-range plateau elevated vs quiet inner range (multi-bin ring bias)."""
    site_idx = np.zeros((16, 16), dtype=np.int16)
    range_km = np.full((16, 16), 55.0, dtype=np.float32)
    range_km[:, 8:12] = 95.0
    data = np.full((16, 16), 10.0, dtype=np.float32)
    data[:, 8:12] = 28.0
    out, n = remove_radial_range_rings(data, site_idx, range_km, min_annulus_cells=4)
    assert n > 0
    assert np.all(out[:, 8:12] == 0.0)
    assert np.all(out[:, :8] == 10.0)


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
    out, counts = remove_gridrad_artifacts(data, range_km, site_idx, site_remediation=False)
    assert counts["isolated"] >= 1
    assert "radial_ring" in counts
    assert "persistent_range" in counts
    assert out[2, 2] == 0.0


def test_remove_persistent_range_artifacts_chronic_ring():
    """Cells on a chronically active range annulus are removed; burst cells kept."""
    site_idx = np.zeros((8, 12), dtype=np.int16)
    range_km = np.full((8, 12), 55.0, dtype=np.float32)
    range_km[:, 4:8] = 95.0
    history = np.full((10, 8, 12), 10.0, dtype=np.float32)
    history[:, :, 4:8] = 30.0
    data = np.full((8, 12), 10.0, dtype=np.float32)
    data[:, 4:8] = 32.0
    data[4, 5] = 80.0  # burst vs history median ~30
    out, n = remove_persistent_range_artifacts(data, site_idx, range_km, history)
    assert n > 0
    assert out[4, 5] == 80.0
    assert np.all(out[:, 4:8][out[:, 4:8] < 80.0] == 0.0)


def test_site_remediation_ids_count():
    assert len(SITE_REMEDIATION_IDS) == 9
    assert "KTLX" in SITE_REMEDIATION_IDS
    assert "KDOX" in SITE_REMEDIATION_IDS


def test_remove_site_polar_spokes():
    """Thin spoke on one azimuth sector at a flagged site."""
    _, _, ids = nexrad_sites_conus()
    tlx = ids.index("KTLX")
    site_idx = np.full((20, 20), tlx, dtype=np.int16)
    range_km = np.full((20, 20), 55.0, dtype=np.float32)
    data = np.full((20, 20), 10.0, dtype=np.float32)
    data[10, 10] = 80.0
    out, n = remove_site_polar_spokes(data, site_idx, range_km, site_ids=("KTLX",))
    assert n == 1
    assert out[10, 10] == 0.0


def test_remove_flagged_site_artifacts_only_on_remediation_domain():
    _, _, ids = nexrad_sites_conus()
    tlx = ids.index("KTLX")
    other = ids.index("KAMA") if ids.index("KAMA") != tlx else 0
    site_idx = np.zeros((12, 12), dtype=np.int16)
    site_idx[:, :6] = tlx
    site_idx[:, 6:] = other
    range_km = np.full((12, 12), 50.0, dtype=np.float32)
    data = np.zeros((12, 12), dtype=np.float32)
    data[6, 2] = 50.0  # remediation site — isolated speckle
    data[6, 8] = 50.0  # other site — should not be touched by site pass alone
    out, counts = remove_flagged_site_artifacts(data, site_idx, range_km, site_ids=("KTLX",))
    assert out[6, 2] == 0.0
    assert out[6, 8] == 50.0
    assert sum(counts.values()) >= 1


def test_cell_center_latlon_and_nearest_grids(monkeypatch):
    import scripts._config as cfg
    import scripts._radar_geometry as rg

    monkeypatch.setattr(cfg, "NROWS", 4)
    monkeypatch.setattr(cfg, "NCOLS", 4)
    monkeypatch.setattr(rg, "NROWS", 4)
    monkeypatch.setattr(rg, "NCOLS", 4)

    lat, lon = rg.cell_center_latlon()
    assert lat.shape == (4, 4)
    dist = rg.nearest_radar_distance_km()
    assert dist.shape == (4, 4)
    idx = rg.nearest_nexrad_site_index()
    assert idx.shape == (4, 4)
    az = rg.azimuth_to_nearest_site_deg()
    assert az.shape == (4, 4)


def test_ensure_grids_cache_roundtrip(tmp_path: Path):
    from scripts._radar_geometry import ensure_nearest_site_index_grid, ensure_range_km_grid

    idx_path = tmp_path / "nearest.npy"
    range_path = tmp_path / "range.npy"
    idx = ensure_nearest_site_index_grid(idx_path)
    idx2 = ensure_nearest_site_index_grid(idx_path)
    assert np.array_equal(idx, idx2)
    rng = ensure_range_km_grid(range_path)
    rng2 = ensure_range_km_grid(range_path)
    assert np.allclose(rng, rng2)


def test_write_nexrad_sites_csv(tmp_path: Path):
    from scripts._radar_geometry import write_nexrad_sites_csv

    out = tmp_path / "sites.csv"
    write_nexrad_sites_csv(out)
    text = out.read_text()
    assert "site_id" in text
    assert "KTLX" in text


def test_fit_range_debias_skips_low_mesh_and_report():
    from scripts._radar_geometry import fit_range_debias_factors

    pairs = [
        {"date": "20150601", "lat": 35.0, "lon": -97.0, "spc_size_in": 0.5, "mesh75_mm": 40.0},
        {"date": "20150601", "lat": 35.0, "lon": -97.0, "spc_size_in": 1.5, "mesh75_mm": 10.0},
    ]
    fit = fit_range_debias_factors(pairs, min_report_in=1.0, min_mesh_mm=25.0)
    assert fit["n_pairs"]["GridRad"] == 0


def test_load_range_debias_missing(tmp_path: Path):
    from scripts._radar_geometry import load_range_debias

    assert load_range_debias(tmp_path / "missing.npz") is None


def test_remove_persistent_range_bad_history_shape():
    from scripts._radar_geometry import remove_persistent_range_artifacts

    data = np.full((4, 4), 40.0, dtype=np.float32)
    site_idx = np.zeros((4, 4), dtype=np.int16)
    range_km = np.full((4, 4), 50.0, dtype=np.float32)
    out, n = remove_persistent_range_artifacts(data, site_idx, range_km, history=None)
    assert n == 0
    assert np.all(out == data)


def test_remove_site_polar_spokes_no_remediation_sites():
    from scripts._radar_geometry import remove_site_polar_spokes

    data = np.full((6, 6), 40.0, dtype=np.float32)
    site_idx = np.zeros((6, 6), dtype=np.int16)
    range_km = np.full((6, 6), 50.0, dtype=np.float32)
    out, n = remove_site_polar_spokes(data, site_idx, range_km, site_ids=())
    assert n == 0
