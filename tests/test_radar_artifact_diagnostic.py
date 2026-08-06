"""Smoke tests for radar artifact diagnostic helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts._config import NROWS, NCOLS
from scripts.diagnostics.radar_artifact_diagnostic import (
    _mean_annual_max_from_year_peaks,
    accumulate_era_stats,
    iter_mesh_tifs,
    local_median_8,
    parse_args,
    plot_debias_factors,
    plot_mean_annual_by_source,
    plot_range_distance_map,
    plot_spc_ratio_vs_range,
    plot_speckle_by_source,
    range_binned_cell_stats,
    save_mean_annual_max_maps_per_source,
    spc_bias_by_range,
    write_readme,
)
from tests._diagnostics_fixtures import make_spc_pairs_csv, seed_mesh_days, write_mesh_tif


def _patch_small_grid(monkeypatch, nrows: int = 8, ncols: int = 8):
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    monkeypatch.setattr(rad, "NROWS", nrows)
    monkeypatch.setattr(rad, "NCOLS", ncols)
    range_km = np.linspace(0, 250, nrows * ncols, dtype=np.float32).reshape(nrows, ncols)
    monkeypatch.setattr(rad, "ensure_range_km_grid", lambda *_args, **_kwargs: range_km)
    return rad, range_km


def test_local_median_8_peak_isolated():
    data = np.zeros((5, 5), dtype=np.float32)
    data[2, 2] = 100.0
    med = local_median_8(data)
    assert med[2, 2] < 10.0


def test_mean_annual_max_from_year_peaks():
    a = np.zeros((4, 4), dtype=np.float32)
    a[1, 1] = 40.0
    b = np.zeros((4, 4), dtype=np.float32)
    b[1, 1] = 20.0
    out = _mean_annual_max_from_year_peaks({2020: a, 2021: b})
    assert out[1, 1] == 30.0


def test_range_binned_cell_stats_bins():
    mean_annual = np.zeros((10, 10), dtype=np.float32)
    mean_annual[2:4, 2:4] = 50.0
    range_km = np.full((10, 10), 60.0, dtype=np.float32)
    edges = np.array([0, 50, 100, 200], dtype=np.float32)
    df = range_binned_cell_stats(mean_annual, range_km, edges)
    assert len(df) == 3
    assert df.loc[1, "mean_annual_max_mm"] == 50.0


@pytest.mark.skipif(
    __import__("scripts._mapping", fromlist=["has_cartopy"]).has_cartopy() is False,
    reason="cartopy not installed",
)
def test_plot_range_distance_map_writes_png(tmp_path):
    range_km = np.linspace(0, 300, NROWS * NCOLS, dtype=np.float32).reshape(NROWS, NCOLS)
    path = plot_range_distance_map(range_km, tmp_path)
    assert path.exists()
    assert path.name == "map_nearest_radar_distance_km.png"
    assert path.stat().st_size > 1000


def test_parse_args_defaults():
    import sys

    import scripts.diagnostics.radar_artifact_diagnostic as rad

    old = sys.argv
    try:
        sys.argv = ["radar_artifact_diagnostic.py"]
        args = rad.parse_args()
        assert args.every_n_days == 1
        assert args.no_fit_debias is False
    finally:
        sys.argv = old


def test_iter_mesh_tifs_date_bounds(tmp_path: Path):
    seed_mesh_days(tmp_path, [date(2010, 6, 1), date(2015, 6, 1)])
    all_days = list(iter_mesh_tifs(tmp_path, None, None))
    assert len(all_days) == 2
    bounded = list(iter_mesh_tifs(tmp_path, date(2014, 1, 1), date(2016, 1, 1)))
    assert len(bounded) == 1


def test_accumulate_era_stats_smoke(tmp_path: Path, monkeypatch):
    rad, _ = _patch_small_grid(monkeypatch)
    seed_mesh_days(
        tmp_path,
        [date(2010, 6, 1), date(2010, 6, 2), date(2015, 6, 1), date(2021, 6, 1)],
        peak=50.0,
        nrows=8,
        ncols=8,
    )
    stats = accumulate_era_stats(tmp_path, None, None, every_n=1)
    assert stats is not None
    assert stats["n_files"] == 4
    assert "MYRORSS" in stats["mean_annual_max"]


def test_spc_bias_by_range(tmp_path: Path):
    pairs = tmp_path / "pairs.csv"
    make_spc_pairs_csv(pairs, n=80)
    edges = np.array([0, 50, 100, 200], dtype=np.float32)
    df = spc_bias_by_range(pairs, edges)
    assert not df.empty


def test_plot_helpers_write_pngs(tmp_path: Path, monkeypatch):
    _patch_small_grid(monkeypatch)
    mean_maps = {
        s: np.linspace(0, 40, 64, dtype=np.float32).reshape(8, 8) for s in ("MYRORSS", "GridRad", "MRMS")
    }
    speckle = {s: np.full((8, 8), 0.1, dtype=np.float32) for s in mean_maps}
    plot_mean_annual_by_source(mean_maps, tmp_path)
    plot_speckle_by_source(speckle, tmp_path)
    save_mean_annual_max_maps_per_source(mean_maps, tmp_path, skip_geotiff=True)
    assert (tmp_path / "map_mean_annual_max_by_source.png").exists()

    spc_df = pd.DataFrame(
        {
            "source": ["MYRORSS", "GridRad"],
            "range_bin_center_km": [50.0, 100.0],
            "median_mesh_report_ratio": [1.1, 0.9],
        }
    )
    assert plot_spc_ratio_vs_range(spc_df, tmp_path) is not None
    assert plot_spc_ratio_vs_range(pd.DataFrame(), tmp_path) is None

    fit = {
        "range_bin_centers_km": [50.0, 125.0],
        "factors": {s: [1.0, 0.95] for s in ("MYRORSS", "GridRad", "MRMS")},
    }
    plot_debias_factors(fit, tmp_path)
    write_readme(tmp_path, {"n_files": 3, "years": {"MYRORSS": 2}})


def test_main_end_to_end(tmp_path: Path, monkeypatch):
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    mesh = tmp_path / "mesh"
    out = tmp_path / "out"
    pairs = tmp_path / "pairs.csv"
    seed_mesh_days(mesh, [date(2010, 6, 1), date(2015, 6, 1), date(2021, 6, 1)], nrows=8, ncols=8)
    make_spc_pairs_csv(pairs, n=60)
    _patch_small_grid(monkeypatch)
    monkeypatch.setattr(rad, "RANGE_DEBIAS_NPZ", tmp_path / "range_debias.npz")
    monkeypatch.setattr(rad.sys, "argv", [
        "radar_artifact_diagnostic.py",
        "--mesh-dir", str(mesh),
        "--out-dir", str(out),
        "--pairs-csv", str(pairs),
        "--skip-geotiff",
    ])
    rad.main()
    assert (out / "README.md").exists()
    assert (out / "range_binned_annual_max_by_source.csv").exists()


def test_main_skips_when_no_mesh(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    monkeypatch.setattr(rad.sys, "argv", [
        "radar_artifact_diagnostic.py",
        "--mesh-dir", str(tmp_path / "empty"),
        "--out-dir", str(tmp_path / "out"),
    ])
    with pytest.raises(SystemExit):
        rad.main()
    assert "WARNING: SKIP radar_artifact_diagnostic" in capsys.readouterr().out


def test_accumulate_every_n_and_progress(tmp_path, monkeypatch, capsys):
    rad, _ = _patch_small_grid(monkeypatch)
    days = [date(2010, 6, d) for d in range(1, 6)]
    seed_mesh_days(tmp_path, days, peak=50.0, nrows=8, ncols=8)
    stats = accumulate_era_stats(tmp_path, None, None, every_n=2)
    assert stats is not None
    assert stats["n_files"] == 3


def test_save_mean_annual_with_geotiff(tmp_path, monkeypatch):
    _patch_small_grid(monkeypatch)
    mean_maps = {s: np.full((8, 8), 30.0, dtype=np.float32) for s in ("MYRORSS", "GridRad", "MRMS")}
    paths = save_mean_annual_max_maps_per_source(mean_maps, tmp_path, skip_geotiff=False)
    assert any(p.suffix == ".tif" for p in paths)
