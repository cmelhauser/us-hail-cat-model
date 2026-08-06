"""Tests for scripts/14_render_figures.py."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from conftest import load_stage
from scripts._config import DX, LAT_MAX, LON_MIN


@pytest.fixture
def s14():
    return load_stage("14_render_figures.py")


def _write_tif(path: Path, data: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON_MIN, LAT_MAX, DX, DX),
    ) as dst:
        dst.write(data.astype(np.float32), 1)


@pytest.fixture
def tiny_grid():
    return 12, 12


def _patch_map_save(monkeypatch, recorder: list | None = None):
    import _mapping

    def fake_save(tif_path, out_path, **kwargs):
        if recorder is not None:
            recorder.append((Path(tif_path).name, Path(out_path).name, kwargs))
        Path(out_path).write_bytes(b"png")

    monkeypatch.setattr(_mapping, "save_conus_map_from_tif", fake_save)
    return _mapping


def test_stage14_setup_matplotlib(s14):
    plt = s14.setup_matplotlib()
    assert plt.rcParams["figure.dpi"] == 150


def test_stage14_render_rp_map_branches(s14, tmp_path, tiny_grid, monkeypatch):
    nrows, ncols = tiny_grid
    tif = tmp_path / "rp.tif"
    data = np.zeros((nrows, ncols), dtype=np.float32)
    data[1:3, 1:3] = 50.0
    _write_tif(tif, data)

    saved: list = []
    monkeypatch.setattr(s14, "MASK_DIR", tmp_path / "missing_mask")
    _patch_map_save(monkeypatch, saved)

    out_hail = tmp_path / "hail.png"
    s14.render_rp_map(tif, out_hail, "Hail map", hail_size_map=True)
    assert out_hail.exists()
    assert saved[-1][2]["zero_to_nan"] is True

    delta_tif = tmp_path / "delta.tif"
    delta = np.array([[0, 5, -3, 0], [2, 0, 0, 1], [0, 0, 4, 0], [0, 0, 0, 0]], dtype=np.float32)
    _write_tif(delta_tif, delta)
    out_delta = tmp_path / "delta.png"
    s14.render_rp_map(delta_tif, out_delta, "Delta map", hail_size_map=False)
    assert out_delta.exists()
    assert saved[-1][2]["symmetric"] is True


def test_stage14_render_historical_and_stochastic_maps(s14, tmp_path, tiny_grid, monkeypatch):
    nrows, ncols = tiny_grid
    cdf_dir = tmp_path / "cdf"
    stoch_dir = tmp_path / "stochastic" / "maps"
    fig_hist = tmp_path / "historical"
    fig_stoch = tmp_path / "stochastic_figs"
    monkeypatch.setattr(s14, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s14, "STOCH_DIR", tmp_path / "stochastic")
    monkeypatch.setattr(s14, "FIG_HIST", fig_hist)
    monkeypatch.setattr(s14, "FIG_STOCH", fig_stoch)
    monkeypatch.setattr(s14, "RP_YEARS", [100])
    monkeypatch.setattr(s14, "MASK_DIR", tmp_path / "mask")

    data = np.full((nrows, ncols), 25.4, dtype=np.float32)
    _write_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", data)
    _write_tif(stoch_dir / "rp_00100yr_stochastic.tif", data)

    _patch_map_save(monkeypatch)

    s14.render_historical_maps()
    s14.render_stochastic_maps()
    assert (fig_hist / "rp_00100yr_analytical.png").exists()
    assert (fig_stoch / "rp_00100yr_stochastic.png").exists()


def test_stage14_render_ep_curves(s14, tmp_path, monkeypatch):
    pet_dir = tmp_path / "pet"
    pet_dir.mkdir()
    pd.DataFrame(
        {"peak_hail_in": [1.0, 2.0, 3.0], "return_period_yr": [10, 100, 1000]}
    ).to_csv(pet_dir / "pet_occurrence.csv", index=False)
    fig_stoch = tmp_path / "stochastic"
    monkeypatch.setattr(s14, "PET_DIR", pet_dir)
    monkeypatch.setattr(s14, "FIG_STOCH", fig_stoch)

    s14.render_ep_curves()
    assert (fig_stoch / "oep_curve.png").exists()

    monkeypatch.setattr(s14, "PET_DIR", tmp_path / "missing")
    s14.render_ep_curves()


def test_stage14_render_analytical_vs_stochastic(s14, tmp_path, tiny_grid, monkeypatch):
    nrows, ncols = tiny_grid
    cdf_dir = tmp_path / "cdf"
    stoch_maps = tmp_path / "stochastic" / "maps"
    fig_anal = tmp_path / "analysis"
    monkeypatch.setattr(s14, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s14, "STOCH_DIR", tmp_path / "stochastic")
    monkeypatch.setattr(s14, "FIG_ANAL", fig_anal)

    dense = np.full((nrows, ncols), 50.0, dtype=np.float32)
    for rp in (100, 500):
        _write_tif(cdf_dir / f"rp_{rp:05d}yr_hail_smooth.tif", dense)
        _write_tif(stoch_maps / f"rp_{rp:05d}yr_stochastic.tif", dense * 1.1)

    s14.render_analytical_vs_stochastic()
    assert (fig_anal / "analytical_vs_stochastic_rp.png").exists()

    monkeypatch.setattr(s14, "CDF_DIR", tmp_path / "empty")
    s14.render_analytical_vs_stochastic()


def test_stage14_render_delta_maps(s14, tmp_path, tiny_grid, monkeypatch):
    nrows, ncols = tiny_grid
    cdf_dir = tmp_path / "cdf"
    stoch_maps = tmp_path / "stochastic" / "maps"
    fig_anal = tmp_path / "analysis"
    monkeypatch.setattr(s14, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s14, "STOCH_DIR", tmp_path / "stochastic")
    monkeypatch.setattr(s14, "FIG_ANAL", fig_anal)
    monkeypatch.setattr(s14, "MASK_DIR", tmp_path / "mask")

    a = np.full((nrows, ncols), 40.0, dtype=np.float32)
    b = np.full((nrows, ncols), 45.0, dtype=np.float32)
    _write_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", a)
    _write_tif(stoch_maps / "rp_00100yr_stochastic.tif", b)

    _patch_map_save(monkeypatch)
    s14.render_delta_maps()
    assert (cdf_dir / "analytical_stochastic_delta_00100yr.tif").exists()
    assert (fig_anal / "analytical_stochastic_delta_00100yr.png").exists()

    calls = {"n": 0}

    def boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("render failed")
        Path(args[1]).write_bytes(b"png")

    monkeypatch.setattr(s14, "render_rp_map", boom)
    s14.render_delta_maps()


def test_stage14_render_event_summary(s14, tmp_path, monkeypatch):
    event_dir = tmp_path / "events"
    event_dir.mkdir()
    fig_hist = tmp_path / "historical"
    monkeypatch.setattr(s14, "EVENT_DIR", event_dir)
    monkeypatch.setattr(s14, "FIG_HIST", fig_hist)

    pd.DataFrame(
        {
            "start_date": pd.to_datetime(["2019-05-01", "2020-06-15", "2020-07-01"]),
            "event_id": [1, 2, 3],
        }
    ).to_csv(event_dir / "event_catalog.csv", index=False)

    s14.render_event_summary()
    assert (fig_hist / "annual_event_counts.png").exists()
    assert (fig_hist / "monthly_event_distribution.png").exists()

    monkeypatch.setattr(s14, "EVENT_DIR", tmp_path / "missing")
    s14.render_event_summary()


def test_stage14_render_analytical_vs_stochastic_single_panel(
    s14, tmp_path, tiny_grid, monkeypatch
):
    nrows, ncols = tiny_grid
    cdf_dir = tmp_path / "cdf"
    stoch_maps = tmp_path / "stochastic" / "maps"
    fig_anal = tmp_path / "analysis"
    monkeypatch.setattr(s14, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s14, "STOCH_DIR", tmp_path / "stochastic")
    monkeypatch.setattr(s14, "FIG_ANAL", fig_anal)

    dense = np.full((nrows, ncols), 50.0, dtype=np.float32)
    _write_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", dense)
    _write_tif(stoch_maps / "rp_00100yr_stochastic.tif", dense * 1.1)

    s14.render_analytical_vs_stochastic()
    assert (fig_anal / "analytical_vs_stochastic_rp.png").exists()


def test_stage14_render_rp_map_scripts_mapping_import(s14, tmp_path, monkeypatch):
    nrows, ncols = 3, 3
    tif = tmp_path / "rp.tif"
    _write_tif(tif, np.full((nrows, ncols), 25.4, dtype=np.float32))

    real_import = s14.__builtins__["__import__"] if isinstance(s14.__builtins__, dict) else __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "_mapping":
            raise ImportError("direct mapping unavailable")
        return real_import(name, globals, locals, fromlist, level)

    import builtins

    monkeypatch.setattr(builtins, "__import__", fake_import)
    saved: list = []
    import scripts._mapping as scripts_mapping

    def fake_save(tif_path, out_path, **kwargs):
        saved.append(out_path)
        Path(out_path).write_bytes(b"png")

    monkeypatch.setattr(scripts_mapping, "save_conus_map_from_tif", fake_save)
    monkeypatch.setattr(s14, "MASK_DIR", tmp_path / "mask")
    out = tmp_path / "out.png"
    s14.render_rp_map(tif, out, "Title")
    assert out.exists()


def test_stage14_validate_outputs(s14, tmp_path, monkeypatch):
    fig_hist = tmp_path / "historical"
    fig_stoch = tmp_path / "stochastic"
    fig_anal = tmp_path / "analysis"
    monkeypatch.setattr(s14, "FIG_HIST", fig_hist)
    monkeypatch.setattr(s14, "FIG_STOCH", fig_stoch)
    monkeypatch.setattr(s14, "FIG_ANAL", fig_anal)

    assert s14.validate_outputs() is False

    for d in (fig_hist, fig_stoch, fig_anal):
        d.mkdir(parents=True)
        (d / "x.png").write_bytes(b"png")
    assert s14.validate_outputs() is True


def test_stage14_main_maps_only_and_full(s14, tmp_path, tiny_grid, monkeypatch):
    nrows, ncols = tiny_grid
    cdf_dir = tmp_path / "cdf"
    stoch_root = tmp_path / "stochastic"
    stoch_maps = stoch_root / "maps"
    pet_dir = stoch_root / "pet"
    event_dir = tmp_path / "events"
    fig_hist = tmp_path / "historical"
    fig_stoch = tmp_path / "stochastic_figs"
    fig_anal = tmp_path / "analysis"

    for d in (cdf_dir, stoch_maps, pet_dir, event_dir, fig_hist, fig_stoch, fig_anal):
        d.mkdir(parents=True, exist_ok=True)

    dense = np.full((nrows, ncols), 50.0, dtype=np.float32)
    _write_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", dense)
    _write_tif(stoch_maps / "rp_00100yr_stochastic.tif", dense)
    _write_tif(cdf_dir / "rp_00500yr_hail_smooth.tif", dense)
    _write_tif(stoch_maps / "rp_00500yr_stochastic.tif", dense)
    _write_tif(cdf_dir / "rp_01000yr_hail_smooth.tif", dense)
    _write_tif(stoch_maps / "rp_01000yr_stochastic.tif", dense)
    _write_tif(cdf_dir / "rp_10000yr_hail_smooth.tif", dense)
    _write_tif(stoch_maps / "rp_10000yr_stochastic.tif", dense)

    pd.DataFrame(
        {"peak_hail_in": [1.0, 2.0], "return_period_yr": [10, 100]}
    ).to_csv(pet_dir / "pet_occurrence.csv", index=False)
    pd.DataFrame(
        {"start_date": pd.to_datetime(["2020-05-01"]), "event_id": [1]}
    ).to_csv(event_dir / "event_catalog.csv", index=False)

    monkeypatch.setattr(s14, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s14, "STOCH_DIR", stoch_root)
    monkeypatch.setattr(s14, "EVENT_DIR", event_dir)
    monkeypatch.setattr(s14, "PET_DIR", pet_dir)
    monkeypatch.setattr(s14, "FIG_HIST", fig_hist)
    monkeypatch.setattr(s14, "FIG_STOCH", fig_stoch)
    monkeypatch.setattr(s14, "FIG_ANAL", fig_anal)
    monkeypatch.setattr(s14, "MASK_DIR", tmp_path / "mask")
    monkeypatch.setattr(s14, "RP_YEARS", [100])

    _patch_map_save(monkeypatch)

    monkeypatch.setattr(sys, "argv", ["14_render_figures.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s14.main()
    assert exc.value.code == 1

    (fig_hist / "seed.png").write_bytes(b"png")
    (fig_stoch / "seed.png").write_bytes(b"png")
    (fig_anal / "seed.png").write_bytes(b"png")

    monkeypatch.setattr(sys, "argv", ["14_render_figures.py", "--maps-only"])
    with pytest.raises(SystemExit) as exc:
        s14.main()
    assert exc.value.code == 0

    monkeypatch.setattr(sys, "argv", ["14_render_figures.py"])
    with pytest.raises(SystemExit) as exc:
        s14.main()
    assert exc.value.code == 0
    assert (fig_stoch / "oep_curve.png").exists()
    assert (fig_anal / "analytical_vs_stochastic_rp.png").exists()
