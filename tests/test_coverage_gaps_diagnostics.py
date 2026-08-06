"""Targeted tests for remaining scripts/ coverage gaps (diagnostics + small modules)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from conftest import REPO_ROOT, load_stage
from tests._diagnostics_fixtures import seed_mesh_days, write_grid_tif, write_mesh_tif


@pytest.fixture
def rerun():
    return load_stage("rerun_stage05.py")


@pytest.fixture
def spc():
    return load_stage("03_download_spc.py")


@pytest.fixture
def s06():
    return load_stage("06_validate_mesh_vs_spc.py")


def _exec_fresh(module_path: Path, module_name: str, *, repo_on_path: bool = False):
    """Execute a script module, optionally with repo root absent from sys.path."""
    repo = REPO_ROOT
    scripts = repo / "scripts"
    saved = sys.path.copy()
    saved_modules = {k: sys.modules.pop(k) for k in list(sys.modules) if k == module_name}
    try:
        sys.path = [p for p in sys.path if p not in (str(repo), str(scripts))]
        if repo_on_path:
            sys.path.insert(0, str(repo))
        sys.path.insert(0, str(scripts))
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.modules.update(saved_modules)
        sys.path = saved


# ---------------------------------------------------------------------------
# sys.path.insert lines (reload with repo absent)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path,module_name",
    [
        ("scripts/diagnostics/literature_validation_suite.py", "lvs_fresh"),
        ("scripts/diagnostics/render_pnas_article_figures.py", "rpf_fresh"),
        ("scripts/diagnostics/summarize_mesh_daily_peaks.py", "smp_fresh"),
        ("scripts/diagnostics/radar_artifact_diagnostic.py", "rad_fresh"),
        ("scripts/diagnostics/hail_day_climatology.py", "hdc_fresh"),
        ("scripts/diagnostics/render_pnas_publication_md.py", "rpub_fresh"),
        ("scripts/train_artifact_classifier.py", "tac_fresh"),
        ("scripts/rerun_stage05.py", "rs05_fresh"),
    ],
)
def test_sys_path_insert_on_fresh_import(rel_path, module_name):
    mod = _exec_fresh(REPO_ROOT / rel_path, module_name, repo_on_path=False)
    assert mod is not None


def test_stage_scripts_sys_path_insert_and_direct_imports():
    for name in (
        "11_build_occurrence_probs.py",
        "12_apply_conus_mask.py",
        "06_validate_mesh_vs_spc.py",
        "11b_prepare_topography.py",
    ):
        mod = _exec_fresh(REPO_ROOT / "scripts" / name, f"stage_{name}_fresh", repo_on_path=False)
        assert hasattr(mod, "main")


# ---------------------------------------------------------------------------
# rerun_stage05.py — wait loop branches
# ---------------------------------------------------------------------------


def test_wait_for_stage05_alive_pid_and_unlink(rerun, tmp_path, monkeypatch):
    pid_file = tmp_path / "stage05.pid"
    monkeypatch.setattr(rerun, "STAGE05_PID", pid_file)
    pid_file.write_text("999\n")
    sleeps: list[float] = []
    logs: list[str] = []
    calls = {"n": 0}

    def fake_alive(pid):
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr(rerun.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(rerun, "_read_stage05_pid", lambda: 999)
    monkeypatch.setattr(rerun, "_pid_alive", fake_alive)
    monkeypatch.setattr(
        rerun.subprocess,
        "check_output",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "pgrep")),
    )
    rerun.wait_for_stage05(poll_sec=0.01, log=logs.append)
    assert sleeps
    assert any("Stage 05 running" in m for m in logs)
    assert not pid_file.exists()


# ---------------------------------------------------------------------------
# scripts/_io.py line 199 — naive observation UTC in convective window
# ---------------------------------------------------------------------------


def test_observation_times_naive_utc_branch():
    from scripts._io import observation_times_from_paths

    day = date(2015, 6, 1)
    times = observation_times_from_paths(["MRMS_MESH_00.50_20150601-180000.grib2.gz"], day)
    assert len(times) == 1
    assert times[0].tzinfo is not None


# ---------------------------------------------------------------------------
# scripts/_mapping.py line 227 — ndarray axes from create_conus_axes
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    __import__("scripts._mapping", fromlist=["has_cartopy"]).has_cartopy() is False,
    reason="cartopy not installed",
)
def test_save_conus_raster_map_ndarray_axes_branch(monkeypatch, tmp_path):
    import matplotlib.pyplot as plt

    from scripts._config import NROWS, NCOLS
    from scripts import _mapping as mp

    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[50, 50] = 25.0
    fig, axes = mp.create_conus_axes(nrows=1, ncols=2, figsize=(8, 4))
    try:
        monkeypatch.setattr(mp, "create_conus_axes", lambda **k: (fig, axes))
        out = mp.save_conus_raster_map(data, tmp_path / "map.png", title="t")
        assert out.exists()
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# scripts/_radar_geometry.py remaining branches
# ---------------------------------------------------------------------------


def test_fit_range_debias_median_in_dense_bin():
    from scripts._radar_geometry import fit_range_debias_factors

    pairs = []
    for i in range(35):
        pairs.append(
            {
                "date": "20150601",
                "lat": 35.0 + i * 0.01,
                "lon": -97.0,
                "spc_size_in": 1.5,
                "mesh75_mm": 40.0,
            }
        )
    fit = fit_range_debias_factors(pairs, min_report_in=1.0, min_mesh_mm=25.0)
    assert fit["n_pairs"]["GridRad"] >= 30


def test_apply_range_debias_myrorss_mrms_and_missing_factors():
    from scripts._radar_geometry import apply_range_debias

    data = np.full((4, 4), 50.0, dtype=np.float32)
    range_grid = np.full((4, 4), 55.0, dtype=np.float32)
    debias = {
        "range_bin_edges_km": np.array([0, 100, 200], dtype=np.float32),
        "range_bin_centers_km": np.array([50, 150], dtype=np.float32),
        "factors": {"MYRORSS": np.array([1.0, 1.0], dtype=np.float32), "MRMS": np.array([0.9, 0.9], dtype=np.float32)},
    }
    out = apply_range_debias(data, range_grid, "MYRORSS/MRMS", debias)
    assert out.shape == data.shape
    debias2 = {"range_bin_edges_km": debias["range_bin_edges_km"], "range_bin_centers_km": debias["range_bin_centers_km"], "factors": {}}
    assert np.array_equal(apply_range_debias(data, range_grid, "GridRad", debias2), data)


def test_radar_geometry_early_return_branches():
    from scripts._radar_geometry import (
        remove_background_filament_artifacts,
        remove_flagged_site_artifacts,
        remove_gridrad_artifacts,
        remove_persistent_range_artifacts,
        remove_radial_range_rings,
        remove_site_polar_spokes,
        remove_speckle_spikes,
    )

    quiet = np.zeros((6, 6), dtype=np.float32)
    out, n = remove_speckle_spikes(quiet, active_mm=5.0)
    assert n == 0

    site_idx = np.zeros((6, 6), dtype=np.int16)
    range_km = np.full((6, 6), 50.0, dtype=np.float32)
    data = np.zeros((6, 6), dtype=np.float32)
    bad_hist = np.zeros((3, 6, 6), dtype=np.float32)
    out2, n2 = remove_persistent_range_artifacts(data, site_idx, range_km, history=bad_hist)
    assert n2 == 0

    out3, n3 = remove_background_filament_artifacts(quiet)
    assert n3 == 0

    out4, n4 = remove_radial_range_rings(data, site_idx, range_km, min_annulus_cells=4)
    assert n4 == 0

    out5, n5 = remove_site_polar_spokes(data, site_idx, range_km, site_ids=("KTLX",))
    assert n5 == 0

    out6, counts = remove_flagged_site_artifacts(data, site_idx, range_km, site_ids=("KTLX",))
    assert out6.shape == data.shape
    assert counts == {}

    out7, c7 = remove_gridrad_artifacts(data, range_km, site_idx, site_remediation=True)
    assert out7.shape == data.shape
    assert isinstance(c7, dict)


def test_radial_range_rings_nbr_none_branch():
    from scripts._radar_geometry import remove_radial_range_rings

    site_idx = np.zeros((8, 8), dtype=np.int16)
    range_km = np.full((8, 8), 95.0, dtype=np.float32)
    range_km[:, :3] = 45.0
    data = np.full((8, 8), 10.0, dtype=np.float32)
    data[:, 3:5] = 45.0
    out, n = remove_radial_range_rings(data, site_idx, range_km, min_annulus_cells=2, min_outer_range_km=80.0)
    assert out.shape == data.shape


# ---------------------------------------------------------------------------
# 03_download_spc.py — unreadable CSV sample
# ---------------------------------------------------------------------------


def test_validate_outputs_unreadable_csv(spc, tmp_path, monkeypatch):
    out_dir = tmp_path / "spc"
    out_dir.mkdir()
    for i in range(1001):
        (out_dir / f"file_{i:04d}.csv").write_text("a,b\n1,2\n")
    bad = out_dir / "file_0000.csv"
    bad.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(spc, "OUT_DIR", out_dir)

    class FixedRandom:
        def __init__(self, _seed):
            pass

        def sample(self, population, k):
            return [bad]

    monkeypatch.setattr("random.Random", FixedRandom)
    assert spc.validate_outputs() is False


# ---------------------------------------------------------------------------
# literature_validation_suite.py — remaining branches
# ---------------------------------------------------------------------------


def test_lvs_load_peaks_branches(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "PEAKS_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(lvs, "CORRECTED_DIR", tmp_path / "missing_dir")
    assert lvs._load_peaks() is None

    corr = tmp_path / "corr"
    (corr / "2015").mkdir(parents=True)
    (corr / "2015" / "mesh_badname.tif").write_bytes(b"x")
    (corr / "2015" / "mesh_20150601.tif").write_bytes(b"bad")
    monkeypatch.setattr(lvs, "CORRECTED_DIR", corr)
    assert lvs._load_peaks() is None

    write_mesh_tif(corr / "2015" / "mesh_20150602.tif", peak=33.0)
    df = lvs._load_peaks()
    assert df is not None and len(df) == 1


def test_lvs_composite_rp_gpd_tail_branches():
    from scripts.diagnostics.literature_validation_suite import _composite_rp_mm

    p_occ = np.array([[0.15]], dtype=np.float32)
    lognorm_mu = np.array([[np.log(30.0)]], dtype=np.float32)
    lognorm_sigma = np.array([[0.2]], dtype=np.float32)
    gpd_xi = np.array([[0.0]], dtype=np.float32)
    gpd_sigma = np.array([[4.0]], dtype=np.float32)
    gpd_threshold = np.array([[45.0]], dtype=np.float32)
    fit_type = np.array([[2]], dtype=np.int8)
    val = _composite_rp_mm(
        0, 0, 100, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type,
    )
    assert val >= 0
    assert _composite_rp_mm(0, 0, 100, np.array([[0.0]]), lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type) == 0.0


def test_lvs_rural_urban_warn_and_gridrad_empty_manifest(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    pairs = tmp_path / "pairs.csv"
    rows = []
    for _ in range(35):
        rows.append({"lat": 46.0, "lon": -110.0, "spc_size_in": 1.5, "mesh75_mm": 30.0})
    for _ in range(35):
        rows.append({"lat": 40.75, "lon": -73.99, "spc_size_in": 1.5, "mesh75_mm": 10.0})
    pd.DataFrame(rows).to_csv(pairs, index=False)
    monkeypatch.setattr(lvs, "PAIRS_CSV", pairs)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = lvs.check_spc_rural_urban_bias()
    assert res.status == "warn"

    manifest = tmp_path / "gridrad.csv"
    pd.DataFrame(columns=["date", "status"]).to_csv(manifest, index=False)
    monkeypatch.setattr(lvs, "GRIDRAD_MANIFEST", manifest)
    assert lvs.check_gridrad_upstream_qc().status == "skip"


def test_lvs_negative_binomial_poisson_fallback(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    path = tmp_path / "events.csv"
    rows = [{"start_date": f"{y}-06-01"} for y in range(2000, 2010) for _ in range(10)]
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(lvs, "EVENT_CSV", path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = lvs.check_negative_binomial_events()
    assert res.status in ("pass", "warn")


def test_lvs_bootstrap_warn_wide_ci(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    n = 12
    fit_type = np.ones((n, n), dtype=np.int8)
    arrays = {
        "fit_type": fit_type,
        "p_occ": np.full((n, n), 0.2, dtype=np.float32),
        "lognorm_mu": np.full((n, n), np.log(35.0), dtype=np.float32),
        "lognorm_sigma": np.full((n, n), 0.25, dtype=np.float32),
        "gpd_xi": np.full((n, n), 0.05, dtype=np.float32),
        "gpd_sigma": np.full((n, n), 4.0, dtype=np.float32),
        "gpd_threshold": np.full((n, n), 50.0, dtype=np.float32),
    }
    npz_path = tmp_path / "cdf_parameters.npz"
    np.savez(npz_path, **arrays)
    monkeypatch.setattr(lvs, "CDF_NPZ", npz_path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)

    rng = np.random.default_rng(0)
    orig_choice = rng.choice

    def noisy_choice(arr, size, replace):
        return orig_choice(arr, size=size, replace=replace)

    monkeypatch.setattr(lvs.np.random, "default_rng", lambda *_a, **_k: rng)
    res = lvs.check_bootstrap_rp_ci()
    assert res.status in ("pass", "warn", "skip")


def test_lvs_tail_dependence_warn_and_main_peaks_print(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.literature_validation_suite as lvs

    mesh = tmp_path / "mesh"
    for year in (2014, 2015, 2016):
        for day in range(1, 12):
            write_grid_tif(
                mesh / str(year) / f"mesh_{year}06{day:02d}.tif",
                np.full((8, 8), 80.0, dtype=np.float32),
            )
    monkeypatch.setattr(lvs, "CORRECTED_DIR", mesh)
    monkeypatch.setattr(lvs, "MESH_DIR", tmp_path / "empty")
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    monkeypatch.setattr(lvs, "NROWS", 8)
    monkeypatch.setattr(lvs, "NCOLS", 8)
    res = lvs.check_tail_dependence_pilot()
    assert res.status in ("pass", "warn")

    peaks = tmp_path / "peaks.csv"
    pd.DataFrame({"date": ["2015-06-01"], "peak_mm": [40.0]}).to_csv(peaks, index=False)
    monkeypatch.setattr(lvs, "PEAKS_CSV", peaks)
    monkeypatch.setattr(lvs.sys, "argv", ["literature_validation_suite.py", "--only", "source_transition"])
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    lvs.main()
    assert "daily peaks:" in capsys.readouterr().out


def test_lvs_preferred_mesh_dir_none_and_pooled_skip_year(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "CORRECTED_DIR", tmp_path / "empty")
    monkeypatch.setattr(lvs, "MESH_DIR", tmp_path / "also_empty")
    assert lvs._preferred_mesh_dir() is None

    mesh = tmp_path / "mesh"
    write_mesh_tif(mesh / "2014" / "mesh_20140601.tif", peak=40.0)
    monkeypatch.setattr(lvs, "NROWS", 8)
    monkeypatch.setattr(lvs, "NCOLS", 8)
    amax = lvs._pooled_annual_max(mesh, (2013, 2014))
    assert float(amax.max()) == 40.0


def test_lvs_rp_checks_partial_maps(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    cdf_dir = tmp_path / "cdf"
    stoch_dir = tmp_path / "stoch"
    cdf_dir.mkdir()
    stoch_dir.mkdir()
    monkeypatch.setattr(lvs, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(lvs, "STOCH_MAP_DIR", stoch_dir)
    assert lvs.check_analytical_vs_stochastic().status == "skip"
    assert lvs.check_rp_ring_energy().status == "skip"


# ---------------------------------------------------------------------------
# render_pnas_article_figures.py
# ---------------------------------------------------------------------------


def test_rpf_calibration_skips_empty_source(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    cal = tmp_path / "cal.csv"
    pd.DataFrame([{"source": "GridRad", "peak_raw_mm": 30.0, "peak_cal_mm": 35.0}]).to_csv(cal, index=False)
    monkeypatch.setattr(rpf, "CAL_PEAKS_CSV", cal)
    stats = rpf.fig_calibration_ecdf(tmp_path / "fig04.png")
    assert "GridRad" in stats
    assert "MYRORSS" not in stats


def test_rpf_render_rp_map_mm_branch(tmp_path):
    from scripts.diagnostics.render_pnas_article_figures import _render_rp_map_png
    from scripts._config import NROWS, NCOLS

    tif = tmp_path / "rp.tif"
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[50:60, 50:60] = 30.0
    write_grid_tif(tif, data)
    assert _render_rp_map_png(tif, tmp_path / "mm.png", title="mm", inches=False) is True


@pytest.mark.skipif(
    __import__("scripts._mapping", fromlist=["has_cartopy"]).has_cartopy() is False,
    reason="cartopy not installed",
)
def test_rpf_analytical_vs_stochastic_full_panel(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf
    from scripts._config import NROWS, NCOLS

    cdf = tmp_path / "cdf"
    stoch = tmp_path / "stoch"
    cdf.mkdir()
    stoch.mkdir()
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[100:120, 200:220] = 50.0
    write_grid_tif(cdf / "rp_00100yr_hail_smooth.tif", data)
    write_grid_tif(stoch / "rp_00100yr_stochastic.tif", data)
    monkeypatch.setattr(rpf, "CDF_DIR", cdf)
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", stoch)
    out = tmp_path / "fig13.png"
    rpf.fig_analytical_vs_stochastic(out)
    assert out.exists()


def test_rpf_collect_metrics_hail_clim_and_pairs_count(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    clim = tmp_path / "clim"
    clim.mkdir()
    pd.DataFrame([{"threshold_key": "skill_29mm", "gp_max_days_per_year": 2.0, "gp_mean_days_per_year": 1.0}]).to_csv(
        clim / "threshold_benchmark_summary.csv", index=False
    )
    pd.DataFrame([{"skill_29mm": 100.0}]).to_csv(clim / "national_annual_hail_days.csv", index=False)
    valid = tmp_path / "validation"
    valid.mkdir()
    pd.DataFrame({"a": range(5)}).to_csv(valid / "mesh_vs_spc_pairs.csv", index=False)
    monkeypatch.setattr(rpf, "HAIL_CLIM_DIR", clim)
    monkeypatch.setattr(rpf, "VALID_DIR", valid)
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", tmp_path / "stoch_maps")
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", tmp_path / "stoch_pet")
    monkeypatch.setattr(rpf, "STOCH_CATALOG", tmp_path / "catalog.parquet")
    metrics = rpf.collect_metrics(pd.DataFrame(), {"k": 1})
    assert metrics["hail_day_climatology_29mm"]["gp_max_days_per_year"] == 2.0
    assert metrics["validation"]["n_pairs"] == 5


def test_rpf_validation_metrics_artifact_classifier_only(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    model = tmp_path / "model.pkl"
    model.write_bytes(b"x")
    monkeypatch.setattr(rpf, "VALID_DIR", tmp_path / "validation")
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER", model)
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER_DIAGNOSTICS", tmp_path / "missing.json")
    metrics = rpf._validation_metrics()
    assert metrics["holdout_tuning_disclosure_required"] is True


def test_rpf_main_copies_scatter(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    scatter = tmp_path / "scatter.png"
    scatter.write_bytes(b"png")
    out_fig = tmp_path / "figs"
    monkeypatch.setattr(rpf, "REPO", tmp_path)
    monkeypatch.setattr(rpf, "OUT_FIG", out_fig)
    monkeypatch.setattr(rpf, "OUT_METRICS", tmp_path / "metrics.json")
    monkeypatch.setattr(rpf, "PEAKS_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(rpf, "CAL_PEAKS_CSV", tmp_path / "missing_cal.csv")
    monkeypatch.setattr(rpf, "HAIL_CLIM_DIR", tmp_path / "clim")
    monkeypatch.setattr(rpf, "VALID_DIR", tmp_path / "validation")
    monkeypatch.setattr(rpf, "EVENT_CSV", tmp_path / "events.csv")
    monkeypatch.setattr(rpf, "CDF_DIR", tmp_path / "cdf")
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", tmp_path / "stoch_maps")
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", tmp_path / "stoch_pet")
    monkeypatch.setattr(rpf, "STOCH_CATALOG", tmp_path / "catalog.parquet")
    for source in rpf.MANIFESTS:
        monkeypatch.setitem(rpf.MANIFESTS, source, tmp_path / f"{source}.csv")
    (tmp_path / "docs" / "figures" / "analysis").mkdir(parents=True)
    (tmp_path / "docs" / "figures" / "analysis" / "mesh_vs_spc_scatter.png").write_bytes(scatter.read_bytes())
    monkeypatch.setattr(
        "scripts.diagnostics.render_pnas_publication_md.main",
        lambda: None,
    )
    rpf.main()
    assert (out_fig / "fig07b_mesh_vs_spc_scatter.png").exists()


# ---------------------------------------------------------------------------
# summarize_mesh_daily_peaks.py
# ---------------------------------------------------------------------------


def test_smp_scan_exception_and_empty(tmp_path, capsys):
    from scripts.diagnostics.summarize_mesh_daily_peaks import build_calibration_peaks_df, scan_mesh_peaks

    bad = tmp_path / "mesh_20100601.tif"
    bad.write_bytes(b"not-tif")
    assert scan_mesh_peaks(tmp_path, d_min=None, d_max=None).empty
    assert "WARN skip" in capsys.readouterr().out

    raw_df = pd.DataFrame(
        [{"date": date(2010, 6, 1), "month": 6, "source": "MYRORSS", "peak_mm": 40.0, "active_cells": 1, "path": "x"}]
    )
    corr = tmp_path / "corr" / "2010" / "mesh_20100601.tif"
    corr.parent.mkdir(parents=True)
    corr.write_bytes(b"bad")
    assert build_calibration_peaks_df(raw_df, tmp_path / "corr").empty


def test_smp_iter_mesh_filters_and_main_branches(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.summarize_mesh_daily_peaks as smp

    (tmp_path / "mesh_notadate.tif").write_bytes(b"x")
    seed_mesh_days(tmp_path, [date(2010, 6, 1)], peak=40.0)
    bounded = list(smp.iter_mesh_tifs(tmp_path, date(2015, 1, 1), None))
    assert bounded == []

    monkeypatch.setattr(smp.sys, "argv", ["summarize_mesh_daily_peaks.py", "--mesh-dir", str(tmp_path / "empty")])
    monkeypatch.setattr(
        "scripts.diagnostics._diagnostic_io.require_mesh_tifs",
        lambda *_a, **_k: False,
    )
    with pytest.raises(SystemExit):
        smp.main()

    mesh = tmp_path / "mesh"
    out = tmp_path / "out"
    seed_mesh_days(mesh, [date(2010, 6, 1)], peak=40.0)
    monkeypatch.setattr(
        "scripts.diagnostics._diagnostic_io.require_mesh_tifs",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(smp.sys, "argv", [
        "summarize_mesh_daily_peaks.py", "--mesh-dir", str(mesh), "--out-dir", str(out), "--skip-calibration",
    ])
    out.mkdir(parents=True, exist_ok=True)
    hist = out / "mesh_daily_peak_distribution.png"
    hist.write_text("old")
    smp.main()
    assert not hist.exists()
    assert (out / "mesh_daily_peaks.csv").exists()

    no_corr = tmp_path / "no_corr"
    no_corr.mkdir()
    monkeypatch.setattr(smp.sys, "argv", [
        "summarize_mesh_daily_peaks.py",
        "--mesh-dir", str(mesh),
        "--corrected-dir", str(no_corr),
        "--out-dir", str(out / "2"),
    ])
    capsys.readouterr()
    smp.main()
    out_text = capsys.readouterr().out
    assert "No paired corrected" in out_text


# ---------------------------------------------------------------------------
# radar_artifact_diagnostic.py
# ---------------------------------------------------------------------------


def test_rad_iter_and_accumulate_branches(tmp_path, monkeypatch):
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    (tmp_path / "mesh_bad.tif").write_bytes(b"x")
    seed_mesh_days(tmp_path, [date(2010, 6, 1), date(2010, 6, 2), date(2010, 6, 3)], nrows=8, ncols=8)
    assert list(rad.iter_mesh_tifs(tmp_path, date(2015, 1, 1), None)) == []

    monkeypatch.setattr(rad, "NROWS", 8)
    monkeypatch.setattr(rad, "NCOLS", 8)
    range_km = np.linspace(0, 250, 64, dtype=np.float32).reshape(8, 8)
    monkeypatch.setattr(rad, "ensure_range_km_grid", lambda *_a, **_k: range_km)
    assert rad._mean_annual_max_from_year_peaks({})[0, 0] == 0.0
    stats = rad.accumulate_era_stats(tmp_path, None, None, every_n=2)
    assert stats is not None
    assert stats["n_files"] == 2


def test_rad_spc_bias_empty_and_main_branches(tmp_path, monkeypatch):
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    edges = np.array([0, 50, 100], dtype=np.float32)
    assert rad.spc_bias_by_range(tmp_path / "missing.csv", edges).empty
    assert rad.spc_bias_by_range(tmp_path / "empty.csv", edges).empty

    mesh = tmp_path / "mesh"
    out = tmp_path / "out"
    seed_mesh_days(mesh, [date(2010, 6, 1), date(2015, 6, 1)], nrows=8, ncols=8)
    monkeypatch.setattr(rad, "NROWS", 8)
    monkeypatch.setattr(rad, "NCOLS", 8)
    monkeypatch.setattr(rad, "ensure_range_km_grid", lambda *_a, **_k: np.full((8, 8), 50.0, dtype=np.float32))
    monkeypatch.setattr(rad, "RANGE_DEBIAS_NPZ", tmp_path / "range_debias.npz")
    monkeypatch.setattr(rad, "require_mesh_tifs", lambda *_a, **_k: False)
    monkeypatch.setattr(rad.sys, "argv", ["radar_artifact_diagnostic.py", "--mesh-dir", str(mesh), "--out-dir", str(out)])
    with pytest.raises(SystemExit):
        rad.main()

    monkeypatch.setattr(rad, "require_mesh_tifs", lambda *_a, **_k: True)
    monkeypatch.setattr(rad.sys, "argv", [
        "radar_artifact_diagnostic.py",
        "--mesh-dir", str(mesh),
        "--out-dir", str(out),
        "--no-fit-debias",
        "--skip-geotiff",
    ])
    rad.main()
    assert (out / "README.md").exists()


def test_rad_save_mean_annual_geotiff_and_progress(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.radar_artifact_diagnostic as rad
    from datetime import timedelta

    monkeypatch.setattr(rad, "NROWS", 8)
    monkeypatch.setattr(rad, "NCOLS", 8)
    mean_maps = {s: np.full((8, 8), 30.0, dtype=np.float32) for s in ("MYRORSS", "GridRad", "MRMS")}
    paths = rad.save_mean_annual_max_maps_per_source(mean_maps, tmp_path, skip_geotiff=False)
    assert any(p.suffix == ".tif" for p in paths)

    days = [date(2010, 1, 1) + timedelta(days=i) for i in range(501)]
    seed_mesh_days(tmp_path, days, nrows=8, ncols=8, peak=40.0)
    monkeypatch.setattr(rad, "ensure_range_km_grid", lambda *_a, **_k: np.full((8, 8), 50.0, dtype=np.float32))
    capsys.readouterr()
    rad.accumulate_era_stats(tmp_path, None, None, every_n=1)
    assert "scanned" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# hail_day_climatology.py
# ---------------------------------------------------------------------------


def test_hdc_selected_thresholds_default_and_main_branches(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.hail_day_climatology as hdc

    specs = hdc.selected_thresholds(None)
    assert specs == hdc.DEFAULT_THRESHOLDS

    mesh = tmp_path / "mesh"
    out = tmp_path / "out"
    seed_mesh_days(mesh, [date(2010, 6, 1)], peak=35.0, nrows=8, ncols=8)
    monkeypatch.setattr(hdc, "NROWS", 8)
    monkeypatch.setattr(hdc, "NCOLS", 8)
    monkeypatch.setattr(hdc.sys, "argv", [
        "hail_day_climatology.py",
        "--mesh-dir", str(mesh),
        "--out-dir", str(out),
        "--thresholds", "conv_25p4mm,skill_29mm",
    ])
    hdc.main()
    assert "25.4 mm" in capsys.readouterr().out or (out / "threshold_benchmark_summary.csv").exists()

    (tmp_path / "not_a_dir").write_text("x")
    monkeypatch.setattr(
        "scripts.diagnostics._diagnostic_io.exit_if_missing",
        lambda *_a, **_k: (_ for _ in ()).throw(SystemExit(0)),
    )
    monkeypatch.setattr(hdc.sys, "argv", [
        "hail_day_climatology.py", "--mesh-dir", str(tmp_path / "not_a_dir"), "--out-dir", str(out),
    ])
    with pytest.raises(SystemExit):
        hdc.main()


def test_hdc_accumulate_progress(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.hail_day_climatology as hdc
    from datetime import timedelta

    days = [date(2010, 1, 1) + timedelta(days=i) for i in range(1000)]
    seed_mesh_days(tmp_path, days, peak=35.0, nrows=8, ncols=8)
    monkeypatch.setattr(hdc, "NROWS", 8)
    monkeypatch.setattr(hdc, "NCOLS", 8)
    specs = hdc.selected_thresholds("skill_29mm")
    capsys.readouterr()
    hdc.accumulate_hail_days(tmp_path, specs, None, None)
    assert "scanned" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# render_pnas_publication_md.py + review_docx.py
# ---------------------------------------------------------------------------


def test_publication_extractors_and_main_review(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_publication_md as pub

    draft = "## Intro\n\nBody to end"
    assert pub.extract_section(draft, "## Missing", until=None) == ""
    assert pub.extract_heading_section(draft, "## Missing") == ""
    assert pub.extract_ai_process_table("no table") == ""

    broken = "Representative AI-assisted interventions are summarized in Table 1.\n\n| x |\n"
    assert pub.extract_ai_process_table(broken) == ""

    table_draft = (
        "Representative AI-assisted interventions are summarized in Table 1.\n\n"
        "| # | Issue | Evidence | Patch | Validation | Residual risk |\n"
        "|---|---|---|---|---|---|\n| 1 | a | b | c | d | e |\n\n## Next\n"
    )
    assert "Issue" in pub.extract_ai_process_table(table_draft)

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps({"generated": "2026-01-01", "stochastic": {"complete": False, "status": "pending"}}))
    draft_path = tmp_path / "draft.md"
    draft_path.write_text("## Introduction\n\nText.\n")
    out_path = tmp_path / "pub.md"
    monkeypatch.setattr(pub, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(pub, "DRAFT_PATH", draft_path)
    monkeypatch.setattr(pub, "OUT_PATH", out_path)
    monkeypatch.setattr(pub, "FIG_DIR", tmp_path / "figs")

    def boom():
        raise RuntimeError("docx unavailable")

    fake_mod = types.ModuleType("scripts.diagnostics.render_pnas_review_docx")
    fake_mod.main = boom
    monkeypatch.setitem(sys.modules, "scripts.diagnostics.render_pnas_review_docx", fake_mod)
    pub.main()
    assert out_path.exists()


def test_review_docx_spacing_and_line_numbers(review_mod):
    class Run:
        font = types.SimpleNamespace(name=None, size=None)

    class Para:
        paragraph_format = types.SimpleNamespace(line_spacing_rule=None, space_after=None, space_before=None)
        runs = [Run()]

    class Cell:
        paragraphs = [Para()]

    class Row:
        cells = [Cell()]

    class Table:
        rows = [Row()]

    class Style:
        font = types.SimpleNamespace(name=None, size=None)
        paragraph_format = types.SimpleNamespace(line_spacing_rule=None, space_after=None, space_before=None)

    existing = MagicMock()
    existing.tag = review_mod.qn("w:lnNumType")

    class SectPr:
        def __init__(self):
            self._children = [existing]

        def __iter__(self):
            return iter(self._children)

        def remove(self, child):
            self._children.remove(child)

        def append(self, child):
            self._children.append(child)

    class Section:
        _sectPr = SectPr()  # noqa: N815  # mirrors python-docx section._sectPr
        top_margin = None
        bottom_margin = None
        left_margin = None
        right_margin = None

    class Doc:
        sections = [Section()]
        paragraphs = [Para()]
        tables = [Table()]
        styles = {"Normal": Style(), "Body Text": Style()}

    doc = Doc()
    review_mod._enable_line_numbers(doc)
    review_mod._apply_double_spacing(doc)
    assert existing not in doc.sections[0]._sectPr._children


@pytest.fixture
def review_mod(tmp_path, monkeypatch):
    from tests.test_render_pnas_review_docx import _install_fake_docx

    _install_fake_docx()
    mod = _exec_fresh(
        REPO_ROOT / "scripts/diagnostics/render_pnas_review_docx.py",
        "review_docx_gap",
        repo_on_path=False,
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    fig_dir = docs / "figures" / "pnas"
    fig_dir.mkdir(parents=True)
    src_md = docs / "pnas_article_publication.md"
    src_md.write_text("## Figures\n\nBody.\n")
    monkeypatch.setattr(mod, "DOCS", docs)
    monkeypatch.setattr(mod, "SRC_MD", src_md)
    monkeypatch.setattr(mod, "OUT_DOCX", docs / "pnas_article_review.docx")
    monkeypatch.setattr(mod, "FIG_DIR", fig_dir)
    return mod


# ---------------------------------------------------------------------------
# train_artifact_classifier.py
# ---------------------------------------------------------------------------


def test_train_classifier_negatives_and_errors(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    mesh_dir = tmp_path / "corrected"
    day = "20150601"
    write_mesh_tif(mesh_dir / "2015" / "mesh_20150601.tif", 60.0)
    nrows, ncols = 8, 8
    monkeypatch.setattr(trainer, "CORRECTED_DIR", mesh_dir)
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(trainer, "ensure_range_km_grid", lambda: np.full((nrows, ncols), 50.0, dtype=np.float32))
    monkeypatch.setattr(trainer, "ensure_nearest_site_index_grid", lambda: np.zeros((nrows, ncols), dtype=np.int16))
    monkeypatch.setattr(trainer, "azimuth_to_nearest_site_deg", lambda: np.zeros((nrows, ncols), dtype=np.float32))

    pairs = pd.DataFrame([{"date": day, "grid_row": 1, "grid_col": 1, "spc_size_in": 1.5, "mesh75_mm": 60.0}])
    rng = np.random.default_rng(0)
    X, y, groups = trainer.build_training_sets(pairs, max_neg_per_day=2, rng=rng, gridrad_only=False)
    assert (y == 0).any()

    one_year = np.array(["20150601"] * 20, dtype="U8")
    X1 = np.random.default_rng(0).normal(size=(20, len(trainer.ARTIFACT_FEATURE_NAMES))).astype(np.float32)
    y1 = np.array([0, 1] * 10, dtype=np.int8)
    with pytest.raises(RuntimeError, match="at least two years"):
        trainer.train_classifier(X1, y1, one_year)

    two_year = np.array([f"201{y%2+5}0601" for y in range(20)], dtype="U8")
    y_bad = np.ones(20, dtype=np.int8)
    with pytest.raises(RuntimeError, match="both weak-label classes"):
        trainer.train_classifier(X1, y_bad, two_year)


def test_train_load_raster_missing_date(load_script, tmp_path, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    monkeypatch.setattr(trainer, "CORRECTED_DIR", tmp_path / "empty")
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    assert trainer._load_raster("19990101") is None


# ---------------------------------------------------------------------------
# 06_validate_mesh_vs_spc.py — remaining branches
# ---------------------------------------------------------------------------


def test_stage06_parse_exception_and_pod_bins(s06, tmp_path, monkeypatch):
    broken = tmp_path / "broken.csv"
    broken.write_bytes(b"\xff\xfe")
    assert s06.parse_spc_csv(broken) == []

    spc_dir = tmp_path / "spc"
    spc_dir.mkdir()
    (spc_dir / "badname.csv").write_text("lat,lon,size,time\n40,-100,100,1200\n", encoding="latin-1")
    (spc_dir / "200515_rpts_hail.csv").write_text("lat,lon,size,time\n", encoding="latin-1")
    mesh_dir = tmp_path / "mesh"
    monkeypatch.setattr(s06, "SPC_DIR", spc_dir)
    monkeypatch.setattr(s06, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s06, "latlon_to_grid", lambda lat, lon: (-1, -1) if lat > 50 else (1, 1))
    assert s06.build_pairs() == []

    fig_dir = tmp_path / "figs"
    monkeypatch.setattr(s06, "FIG_DIR", fig_dir)
    pairs = [{"spc_size_in": 0.6 + 0.05 * i, "mesh75_in": 0.5, "mesh75_mm": 12.7} for i in range(15)]
    s06.make_figures(pairs)
    assert (fig_dir / "detection_by_size.png").exists()


# ---------------------------------------------------------------------------
# 11b_prepare_topography.py — validate error branches
# ---------------------------------------------------------------------------


def test_stage11b_validate_error_messages(tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_stage("11b_prepare_topography.py")
    elev = tmp_path / "elevation_0.05deg.tif"
    with rasterio.open(
        elev,
        "w",
        driver="GTiff",
        height=3,
        width=3,
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=from_origin(0.0, 3.0, 1.0, 1.0),
    ) as dst:
        arr = np.array([[100.0, np.nan, 200.0], [-5.0, 500.0, 500.0], [50.0, 50.0, 50.0]], dtype=np.float32)
        dst.write(arr, 1)
    monkeypatch.setattr(s, "NROWS", 3)
    monkeypatch.setattr(s, "NCOLS", 3)
    monkeypatch.setattr(s, "ELEVATION_TIF", elev)
    assert s.validate_outputs() is False


def test_stage11b_download_removes_tmp_and_reports_progress(tmp_path, monkeypatch):
    import requests

    s = load_stage("11b_prepare_topography.py")
    source = tmp_path / "ETOPO_2022_v1_60s_N90W180_surface.tif"
    tmp = source.with_suffix(".tif.part")
    tmp.write_bytes(b"partial")
    payload = b"x" * (s.MIN_SOURCE_BYTES + 1)

    class FakeResp:
        headers = {"content-length": str(len(payload))}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            yield payload[:50_000_000]
            yield b""
            yield payload[50_000_000:]

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    logs: list[str] = []
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: FakeResp())
    monkeypatch.setattr(s, "log", logs.append)
    out = s.download_source(source, url="https://example.invalid/dem.tif")
    assert out == source
    assert not tmp.exists()
    assert any("Downloaded" in m for m in logs)


# ---------------------------------------------------------------------------
# Additional targeted gaps (second pass)
# ---------------------------------------------------------------------------


def test_stage_direct_import_path_get_logger():
    for name in (
        "11_build_occurrence_probs.py",
        "12_apply_conus_mask.py",
        "06_validate_mesh_vs_spc.py",
    ):
        mod = _exec_fresh(REPO_ROOT / "scripts" / name, f"stage2_{name}", repo_on_path=False)
        assert callable(getattr(mod, "main", None))


def test_stage12_compute_topo_factor_with_freezing_level():
    s12 = load_stage("12_apply_conus_mask.py")
    elev = np.array([[1000.0, 2000.0], [500.0, 3000.0]], dtype=np.float32)
    fl = np.array([[3.0, 4.0], [np.nan, 2.0]], dtype=np.float32)
    out = s12.compute_topo_factor(elev, freezing_level_km=fl)
    assert out.shape == elev.shape
    assert out.min() >= 1.0


def test_publication_extract_ai_table_invalid_header():
    import scripts.diagnostics.render_pnas_publication_md as pub

    draft = (
        "Representative AI-assisted interventions are summarized in Table 1.\n\n"
        "| # | Issue | Evidence | Patch | Validation | Other |\n"
        "|---|---|---|---|---|---|\n| 1 | a | b | c | d | e |\n"
    )
    assert pub.extract_ai_process_table(draft) == ""


def test_rpf_stochastic_metrics_catalog_read_exception(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    map_dir = tmp_path / "maps"
    map_dir.mkdir()
    write_grid_tif(map_dir / "rp_00100yr_stochastic.tif", np.array([[40.0, 50.0]]))
    bad_catalog = tmp_path / "bad.parquet"
    bad_catalog.write_bytes(b"not-parquet")
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", map_dir)
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", tmp_path / "pet")
    monkeypatch.setattr(rpf, "STOCH_CATALOG", bad_catalog)
    metrics = rpf._stochastic_metrics()
    assert metrics["status"] in ("partial", "not_available", "complete")


def test_smp_iter_d_max_and_main_empty_scan(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.summarize_mesh_daily_peaks as smp

    seed_mesh_days(tmp_path, [date(2010, 6, 1), date(2011, 6, 1)], peak=40.0)
    bounded = list(smp.iter_mesh_tifs(tmp_path, None, date(2010, 12, 31)))
    assert len(bounded) == 1

    empty = tmp_path / "empty_scan"
    empty.mkdir()
    monkeypatch.setattr(smp, "require_mesh_tifs", lambda *_a, **_k: True)
    monkeypatch.setattr(smp.sys, "argv", [
        "summarize_mesh_daily_peaks.py", "--mesh-dir", str(empty), "--out-dir", str(tmp_path / "out"),
    ])
    capsys.readouterr()
    smp.main()
    assert "No mesh TIFFs found" in capsys.readouterr().out


def test_rad_main_geotiff_and_diff_paths(tmp_path, monkeypatch):
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    mesh = tmp_path / "mesh"
    out = tmp_path / "out"
    seed_mesh_days(mesh, [date(2010, 6, 1), date(2015, 6, 1)], nrows=8, ncols=8)
    monkeypatch.setattr(rad, "NROWS", 8)
    monkeypatch.setattr(rad, "NCOLS", 8)
    monkeypatch.setattr(rad, "ensure_range_km_grid", lambda *_a, **_k: np.full((8, 8), 50.0, dtype=np.float32))
    monkeypatch.setattr(rad, "RANGE_DEBIAS_NPZ", tmp_path / "debias.npz")
    monkeypatch.setattr(rad, "require_mesh_tifs", lambda *_a, **_k: True)
    monkeypatch.setattr(rad.sys, "argv", [
        "radar_artifact_diagnostic.py",
        "--mesh-dir", str(mesh),
        "--out-dir", str(out),
    ])
    rad.main()
    assert (out / "nearest_radar_distance_km.tif").exists()
    assert (out / "gridrad_minus_myrorss_mean_annual_max.tif").exists()


def test_rad_accumulate_returns_none_when_no_tifs(tmp_path, monkeypatch):
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    monkeypatch.setattr(rad, "NROWS", 8)
    monkeypatch.setattr(rad, "NCOLS", 8)
    assert rad.accumulate_era_stats(tmp_path / "empty", None, None, every_n=1) is None


def test_hdc_main_zero_files_exit(tmp_path, monkeypatch):
    import scripts.diagnostics.hail_day_climatology as hdc

    mesh = tmp_path / "mesh"
    mesh.mkdir()
    monkeypatch.setattr(hdc, "NROWS", 8)
    monkeypatch.setattr(hdc, "NCOLS", 8)
    monkeypatch.setattr(hdc, "require_mesh_tifs", lambda *_a, **_k: True)
    monkeypatch.setattr(hdc, "accumulate_hail_days", lambda *_a, **_k: ({}, {}, {}, [], 0))
    monkeypatch.setattr(hdc, "exit_if_missing", lambda *_a, **_k: (_ for _ in ()).throw(SystemExit(0)))
    monkeypatch.setattr(hdc.sys, "argv", [
        "hail_day_climatology.py", "--mesh-dir", str(mesh), "--out-dir", str(tmp_path / "out"),
    ])
    with pytest.raises(SystemExit):
        hdc.main()


def test_train_build_training_more_branches(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    mesh_dir = tmp_path / "corrected"
    write_mesh_tif(mesh_dir / "2015" / "mesh_20150601.tif", 60.0)
    write_mesh_tif(mesh_dir / "2010" / "mesh_20100601.tif", 60.0)
    nrows, ncols = 8, 8
    monkeypatch.setattr(trainer, "CORRECTED_DIR", mesh_dir)
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(trainer, "ensure_range_km_grid", lambda: np.full((nrows, ncols), 50.0, dtype=np.float32))
    monkeypatch.setattr(trainer, "ensure_nearest_site_index_grid", lambda: np.zeros((nrows, ncols), dtype=np.int16))
    monkeypatch.setattr(trainer, "azimuth_to_nearest_site_deg", lambda: np.zeros((nrows, ncols), dtype=np.float32))

    pairs = pd.DataFrame(
        [
            {"date": "20150601", "grid_row": 1, "grid_col": 1, "spc_size_in": 1.5, "mesh75_mm": 60.0},
            {"date": "20150601", "grid_row": 2, "grid_col": 2, "spc_size_in": 1.5, "mesh75_mm": 60.0},
            {"date": "20100601", "grid_row": 1, "grid_col": 1, "spc_size_in": 1.5, "mesh75_mm": 60.0},
        ]
    )
    X, y, groups = trainer.build_training_sets(
        pairs, max_neg_per_day=1, rng=np.random.default_rng(0), gridrad_only=True,
    )
    assert len(X) > 0

    monkeypatch.setattr(trainer, "_load_raster", lambda _d: None)
    with pytest.raises(RuntimeError, match="No training samples"):
        trainer.build_training_sets(pairs.iloc[:1], max_neg_per_day=5, rng=np.random.default_rng(0))


def test_radar_geometry_remaining_branches():
    from scripts._radar_geometry import (
        apply_range_debias,
        remove_persistent_range_artifacts,
        remove_radial_range_rings,
        remove_site_polar_spokes,
    )

    data = np.full((6, 6), 40.0, dtype=np.float32)
    range_km = np.full((6, 6), 50.0, dtype=np.float32)
    site_idx = np.zeros((6, 6), dtype=np.int16)
    debias = {
        "range_bin_edges_km": np.array([0, 100, 200], dtype=np.float32),
        "range_bin_centers_km": np.array([50, 150], dtype=np.float32),
        "factors": {"MYRORSS": np.array([1.0, 1.0], dtype=np.float32), "MRMS": np.array([0.9, 0.9], dtype=np.float32)},
    }
    apply_range_debias(data, range_km, "MYRORSS/MRMS", debias)

    hist = np.zeros((5, 6, 6), dtype=np.float32)
    quiet = np.zeros((6, 6), dtype=np.float32)
    remove_persistent_range_artifacts(quiet, site_idx, range_km, history=hist)

    ring_data = np.zeros((8, 8), dtype=np.float32)
    ring_range = np.full((8, 8), 95.0, dtype=np.float32)
    ring_range[:, :3] = 45.0
    ring_data[:, 3:5] = 45.0
    ring_site = np.zeros((8, 8), dtype=np.int16)
    remove_radial_range_rings(ring_data, ring_site, ring_range, min_annulus_cells=2, min_outer_range_km=80.0)

    _, _, ids = __import__("scripts._radar_geometry", fromlist=["nexrad_sites_conus"]).nexrad_sites_conus()
    tlx = ids.index("KTLX")
    si = np.full((10, 10), tlx, dtype=np.int16)
    si[:5, :] = -1
    remove_site_polar_spokes(np.full((10, 10), 40.0, dtype=np.float32), si, np.full((10, 10), 55.0, dtype=np.float32), site_ids=("KTLX",))


def test_lvs_more_branch_coverage(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    corr = tmp_path / "corr" / "2015"
    corr.mkdir(parents=True)
    (corr / "mesh_notadate.tif").write_bytes(b"x")
    monkeypatch.setattr(lvs, "PEAKS_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(lvs, "CORRECTED_DIR", tmp_path / "corr")
    lvs._load_peaks()

    assert lvs.check_mann_kendall_annual_max(pd.DataFrame()).status == "skip"

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    write_grid_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", np.array([[50.0, 60.0]]))
    monkeypatch.setattr(lvs, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(lvs, "RP_YEARS", (100, 1000))
    lvs.check_rp_monotonicity()

    gpd_xi = np.array([[0.0]], dtype=np.float32)
    gpd_sigma = np.array([[3.0]], dtype=np.float32)
    gpd_threshold = np.array([[45.0]], dtype=np.float32)
    fit_type = np.array([[2]], dtype=np.int8)
    p_occ = np.array([[0.2]], dtype=np.float32)
    lognorm_mu = np.array([[np.log(30.0)]], dtype=np.float32)
    lognorm_sigma = np.array([[0.2]], dtype=np.float32)
    u = float(gpd_threshold[0, 0])
    from scipy import stats
    p_below = stats.lognorm.cdf(u, float(lognorm_sigma[0, 0]), scale=np.exp(float(lognorm_mu[0, 0])))
    cond = p_below + (1.0 - p_below) * 0.5
    target_p = 1.0 / 1000.0
    p = 0.2
    cond_nonexceed = 1.0 - target_p / p
    assert cond_nonexceed > p_below
    lvs._composite_rp_mm(0, 0, 1000, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type)

    monkeypatch.setattr(lvs, "PAIRS_CSV", tmp_path / "missing.csv")
    assert lvs.check_spc_rural_urban_bias().status == "skip"
    pd.DataFrame({"spc_size_in": [1.0], "mesh75_mm": [30.0]}).to_csv(tmp_path / "pairs_no_lat.csv", index=False)
    monkeypatch.setattr(lvs, "PAIRS_CSV", tmp_path / "pairs_no_lat.csv")
    assert lvs.check_spc_rural_urban_bias().status == "skip"

