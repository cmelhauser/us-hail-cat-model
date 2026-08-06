"""Tests for literature_validation_suite helpers."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from scripts.diagnostics.literature_validation_suite import (
    CHECKS,
    CheckResult,
    _cell_latlon,
    _composite_rp_mm,
    _load_peaks,
    _nearest_metro_km,
    _pooled_annual_max,
    _preferred_mesh_dir,
    check_analytical_vs_stochastic,
    check_bootstrap_rp_ci,
    check_gpd_threshold_summary,
    check_gridrad_upstream_qc,
    check_literature_hail_day_benchmarks,
    check_mann_kendall_annual_max,
    check_ml_filter_reliability,
    check_negative_binomial_events,
    check_poisson_dispersion,
    check_rp_monotonicity,
    check_rp_ring_energy,
    check_seasonality_radar_vs_spc,
    check_source_transition,
    check_spc_detection_and_rounding,
    check_spc_rural_urban_bias,
    check_tail_dependence_pilot,
    classify_source,
    mann_kendall_statistic,
    parse_args,
    write_readme,
)
from tests._diagnostics_fixtures import seed_mesh_days, write_grid_tif, write_mesh_tif


def test_checks_registry_has_expected_count():
    assert len(CHECKS) == 16


def test_mann_kendall_no_trend():
    x = np.arange(20, dtype=np.float64)
    s, p = mann_kendall_statistic(x)
    assert s > 0
    assert p < 0.05


def test_mann_kendall_flat():
    x = np.ones(15)
    s, p = mann_kendall_statistic(x)
    assert s == 0.0


def test_mann_kendall_short_series_nan():
    s, p = mann_kendall_statistic(np.array([1.0, 2.0]))
    assert np.isnan(s) and np.isnan(p)


def test_check_result_dataclass():
    r = CheckResult("x", "pass", "lit", "ok", {"a": 1})
    assert r.status == "pass"


def test_nearest_metro_km():
    # Manhattan should be within ~30 km of NYC centroid
    assert _nearest_metro_km(40.75, -73.99) < 35.0


def test_cell_latlon_corner():
    lat, lon = _cell_latlon(0, 0)
    assert lat < 50.1 and lon > -125.1


def test_composite_rp_mm_lognormal_only():
    p_occ = np.zeros((2, 2), dtype=np.float32)
    p_occ[0, 0] = 0.1
    lognorm_mu = np.full((2, 2), np.log(30.0), dtype=np.float32)
    lognorm_sigma = np.full((2, 2), 0.3, dtype=np.float32)
    gpd_xi = np.zeros((2, 2), dtype=np.float32)
    gpd_sigma = np.ones((2, 2), dtype=np.float32)
    gpd_threshold = np.full((2, 2), 50.0, dtype=np.float32)
    fit_type = np.ones((2, 2), dtype=np.int8)
    val = _composite_rp_mm(
        0, 0, 100, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type
    )
    assert val > 25.0


def test_check_gridrad_upstream_qc_skip(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "GRIDRAD_MANIFEST", tmp_path / "missing.csv")
    res = check_gridrad_upstream_qc()
    assert res.status == "skip"


def test_check_negative_binomial_skip(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "EVENT_CSV", tmp_path / "missing.csv")
    res = check_negative_binomial_events()
    assert res.status == "skip"


def test_check_negative_binomial_overdispersed(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    path = tmp_path / "events.csv"
    years = list(range(2000, 2015))
    rows = []
    for y in years:
        n = 50 if y % 2 == 0 else 150
        for _ in range(n):
            rows.append({"start_date": f"{y}-06-01"})
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(lvs, "EVENT_CSV", path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_negative_binomial_events()
    assert res.status in ("pass", "warn")
    assert res.metrics["index_of_dispersion"] > 1.0


def test_check_gridrad_upstream_qc_warns_on_missing(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    path = tmp_path / "manifest.csv"
    n = 100
    statuses = ["ok"] * 80 + ["missing_source"] * 20
    pd.DataFrame({"date": pd.date_range("2012-01-01", periods=n), "status": statuses}).to_csv(
        path, index=False
    )
    monkeypatch.setattr(lvs, "GRIDRAD_MANIFEST", path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_gridrad_upstream_qc()
    assert res.status == "warn"
    assert res.metrics["fraction_missing_source"] == 0.2


def test_check_spc_rural_urban_bias(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    path = tmp_path / "pairs.csv"
    rows = []
    for _ in range(40):
        rows.append({"lat": 40.75, "lon": -73.99, "spc_size_in": 1.5, "mesh75_mm": 30.0})
    for _ in range(40):
        rows.append({"lat": 46.0, "lon": -110.0, "spc_size_in": 1.5, "mesh75_mm": 10.0})
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(lvs, "PAIRS_CSV", path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_spc_rural_urban_bias()
    assert res.status in ("pass", "warn")
    assert res.metrics["pod_urban_severe"] > res.metrics["pod_rural_severe"]


def test_check_ml_filter_skip_without_model(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "HAIL_FILTER_PKL", tmp_path / "missing.pkl")
    res = check_ml_filter_reliability()
    assert res.status == "skip"
    assert res.metrics["model_present"] is False


def test_check_ml_filter_reads_diagnostics(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    cal = tmp_path / "calibration"
    cal.mkdir()
    pkl = cal / "hail_filter_model.pkl"
    pkl.write_bytes(b"x")
    pd.DataFrame([{"brier_score": 0.12, "auc": 0.85}]).to_csv(
        cal / "hail_filter_diagnostics.csv", index=False
    )
    monkeypatch.setattr(lvs, "ANALYSIS", tmp_path)
    monkeypatch.setattr(lvs, "HAIL_FILTER_PKL", pkl)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_ml_filter_reliability()
    assert res.status == "pass"
    assert res.metrics["brier_score"] == 0.12


def test_check_bootstrap_rp_ci_skip_without_npz(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "CDF_NPZ", tmp_path / "missing.npz")
    res = check_bootstrap_rp_ci()
    assert res.status == "skip"


def test_main_writes_summary(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs.sys, "argv", ["literature_validation_suite.py"])
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    monkeypatch.setattr(lvs, "_load_peaks", lambda: None)
    monkeypatch.setattr(
        lvs,
        "CHECKS",
        {"dummy": lambda _peaks: CheckResult("dummy", "pass", "lit", "ok", {})},
    )
    lvs.main()
    summary = json.loads((tmp_path / "validation_summary.json").read_text())
    assert summary["checks"][0]["name"] == "dummy"


def test_classify_source_eras():
    assert classify_source(date(2005, 6, 1)) == "MYRORSS"
    assert classify_source(date(2015, 6, 1)) == "GridRad"
    assert classify_source(date(2022, 6, 1)) == "MRMS"


def test_mann_kendall_decreasing_trend():
    x = np.arange(20, 0, -1, dtype=np.float64)
    s, p = mann_kendall_statistic(x)
    assert s < 0
    assert p < 0.05


def test_load_peaks_from_csv(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    path = tmp_path / "peaks.csv"
    pd.DataFrame({"date": ["2015-06-01"], "peak_mesh_mm": [42.0]}).to_csv(path, index=False)
    monkeypatch.setattr(lvs, "PEAKS_CSV", path)
    monkeypatch.setattr(lvs, "CORRECTED_DIR", tmp_path / "missing")
    df = _load_peaks()
    assert df is not None
    assert "peak_mm" in df.columns
    assert float(df["peak_mm"].iloc[0]) == 42.0


def test_load_peaks_from_tifs(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    corr = tmp_path / "corrected"
    write_mesh_tif(corr / "2015" / "mesh_20150601.tif", peak=55.0)
    monkeypatch.setattr(lvs, "PEAKS_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(lvs, "CORRECTED_DIR", corr)
    df = _load_peaks()
    assert df is not None
    assert float(df["peak_mm"].iloc[0]) == 55.0


def test_check_source_transition_pass_and_warn(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    rows = []
    for year, peak in [(2010, 30.0), (2011, 32.0), (2012, 90.0), (2013, 95.0)]:
        rows.append({"date": pd.Timestamp(f"{year}-06-01"), "peak_mm": peak})
    peaks = pd.DataFrame(rows)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_source_transition(peaks)
    assert res.status == "warn"
    assert res.metrics["gridrad_myrorss_median_ratio_2012"] > 2.5

    peaks_pass = peaks.copy()
    peaks_pass.loc[peaks_pass["date"].dt.year.isin([2012, 2013]), "peak_mm"] = 31.0
    res_pass = check_source_transition(peaks_pass)
    assert res_pass.status == "pass"


def test_check_spc_detection_skip_and_warn(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "PAIRS_CSV", tmp_path / "missing.csv")
    assert check_spc_detection_and_rounding().status == "skip"

    path = tmp_path / "pairs.csv"
    rows = []
    for i in range(120):
        rows.append(
            {
                "spc_size_in": 0.5 if i < 60 else 2.5,
                "mesh75_mm": 30.0 if i < 60 else 0.0,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(lvs, "PAIRS_CSV", path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_spc_detection_and_rounding()
    assert res.status == "warn"
    assert res.metrics["n_pairs"] == 120


def test_check_seasonality_alignment(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    peaks = pd.DataFrame(
        {
            "date": pd.date_range("2010-04-01", periods=120, freq="D"),
            "peak_mm": np.linspace(30, 60, 120),
        }
    )
    monkeypatch.setattr(lvs, "PAIRS_CSV", tmp_path / "missing.csv")
    assert check_seasonality_radar_vs_spc(peaks).status == "skip"

    pairs = tmp_path / "pairs.csv"
    pair_rows = [{"date": d, "spc_size_in": 1.0, "mesh75_mm": 30.0} for d in peaks["date"]]
    pd.DataFrame(pair_rows).to_csv(pairs, index=False)
    monkeypatch.setattr(lvs, "PAIRS_CSV", pairs)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_seasonality_radar_vs_spc(peaks)
    assert res.status in ("pass", "warn")


def test_check_mann_kendall_warn_on_trend(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    years = np.arange(1998, 2016)
    peaks = pd.DataFrame(
        {
            "date": pd.to_datetime([f"{y}-06-01" for y in years]),
            "peak_mm": np.linspace(20, 120, len(years)),
        }
    )
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_mann_kendall_annual_max(peaks)
    assert res.status == "warn"


def test_check_poisson_dispersion(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "EVENT_CSV", tmp_path / "missing.csv")
    assert check_poisson_dispersion().status == "skip"

    path = tmp_path / "events.csv"
    rows = []
    for y in range(2000, 2015):
        for _ in range(50 if y % 2 == 0 else 150):
            rows.append({"start_date": f"{y}-06-01"})
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(lvs, "EVENT_CSV", path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_poisson_dispersion()
    assert res.status == "warn"
    assert res.metrics["index_of_dispersion"] > 3.0


def test_check_gpd_threshold_summary(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "THRESH_CSV", tmp_path / "missing.csv")
    assert check_gpd_threshold_summary().status == "skip"

    path = tmp_path / "thresh.csv"
    pd.DataFrame({"xi": [0.5] * 20, "sigma": [1.0] * 20, "mrl_score": [0.1] * 20}).to_csv(
        path, index=False
    )
    monkeypatch.setattr(lvs, "THRESH_CSV", path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_gpd_threshold_summary()
    assert res.status == "warn"


def test_check_rp_monotonicity(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    write_grid_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", np.array([[50.0, 60.0]]))
    write_grid_tif(cdf_dir / "rp_01000yr_hail_smooth.tif", np.array([[40.0, 45.0]]))
    monkeypatch.setattr(lvs, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(lvs, "RP_YEARS", (100, 1000))
    res = check_rp_monotonicity()
    assert res.status == "fail"
    assert res.metrics["n_violations"] == 1


def test_check_analytical_vs_stochastic(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    cdf_dir = tmp_path / "cdf"
    stoch_dir = tmp_path / "stoch"
    cdf_dir.mkdir()
    stoch_dir.mkdir()
    write_grid_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", np.array([[10.0, 20.0]]))
    write_grid_tif(stoch_dir / "rp_00100yr_stochastic.tif", np.array([[50.0, 60.0]]))
    monkeypatch.setattr(lvs, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(lvs, "STOCH_MAP_DIR", stoch_dir)
    res = check_analytical_vs_stochastic()
    assert res.status == "warn"


def test_check_rp_ring_energy(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    data = np.full((8, 8), 30.0, dtype=np.float32)
    write_grid_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", data)
    range_km = np.linspace(0, 300, 64, dtype=np.float32).reshape(8, 8)
    monkeypatch.setattr(lvs, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(lvs, "NROWS", 8)
    monkeypatch.setattr(lvs, "NCOLS", 8)
    monkeypatch.setattr(
        "scripts._radar_geometry.ensure_range_km_grid",
        lambda *_args, **_kwargs: range_km,
    )
    res = check_rp_ring_energy()
    assert res.status in ("pass", "warn")


def test_check_literature_hail_day_benchmarks(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    bench = tmp_path / "threshold_benchmark_summary.csv"
    pd.DataFrame(
        [{"threshold_key": "skill_29mm", "gp_max_days_per_year": 25.0}]
    ).to_csv(bench, index=False)
    monkeypatch.setattr(lvs, "HAIL_CLIM_DIR", tmp_path)
    res = check_literature_hail_day_benchmarks()
    assert res.status == "warn"


def test_preferred_mesh_dir_and_pooled_annual_max(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "NROWS", 8)
    monkeypatch.setattr(lvs, "NCOLS", 8)
    mesh = tmp_path / "mesh"
    days = [date(2014, 6, d) for d in range(1, 31)]
    seed_mesh_days(mesh, days, peak=60.0, nrows=8, ncols=8)
    monkeypatch.setattr(lvs, "CORRECTED_DIR", mesh)
    monkeypatch.setattr(lvs, "MESH_DIR", tmp_path / "empty")
    assert _preferred_mesh_dir() == mesh
    amax = _pooled_annual_max(mesh, (2014,))
    assert float(amax.max()) == 60.0


def test_composite_rp_mm_branches():
    p_occ = np.full((2, 2), 0.01, dtype=np.float32)
    lognorm_mu = np.full((2, 2), np.log(30.0), dtype=np.float32)
    lognorm_sigma = np.full((2, 2), 0.3, dtype=np.float32)
    gpd_xi = np.full((2, 2), 0.1, dtype=np.float32)
    gpd_sigma = np.full((2, 2), 5.0, dtype=np.float32)
    gpd_threshold = np.full((2, 2), 50.0, dtype=np.float32)
    fit_type = np.full((2, 2), 2, dtype=np.int8)
    assert _composite_rp_mm(0, 0, 100, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type) == 0.0
    p_occ[0, 0] = 0.2
    val = _composite_rp_mm(
        0, 0, 100, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type,
        p_override=0.15, xi_override=0.05, sigma_override=4.0,
    )
    assert val > 0


def test_check_bootstrap_rp_ci_runs(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    nrows = ncols = 12
    fit_type = np.ones((nrows, ncols), dtype=np.int8)
    fit_type[:2, :2] = 0
    arrays = {
        "fit_type": fit_type,
        "p_occ": np.full((nrows, ncols), 0.15, dtype=np.float32),
        "lognorm_mu": np.full((nrows, ncols), np.log(35.0), dtype=np.float32),
        "lognorm_sigma": np.full((nrows, ncols), 0.25, dtype=np.float32),
        "gpd_xi": np.full((nrows, ncols), 0.05, dtype=np.float32),
        "gpd_sigma": np.full((nrows, ncols), 4.0, dtype=np.float32),
        "gpd_threshold": np.full((nrows, ncols), 50.0, dtype=np.float32),
    }
    npz_path = tmp_path / "cdf_parameters.npz"
    np.savez(npz_path, **arrays)
    monkeypatch.setattr(lvs, "CDF_NPZ", npz_path)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res = check_bootstrap_rp_ci()
    assert res.status in ("pass", "warn", "skip")


def test_check_tail_dependence_pilot(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    mesh = tmp_path / "mesh"
    for year in (2014, 2015, 2016):
        for day in range(1, 12):
            write_grid_tif(
                mesh / str(year) / f"mesh_{year}06{day:02d}.tif",
                np.full((8, 8), 55.0, dtype=np.float32),
            )
    monkeypatch.setattr(lvs, "CORRECTED_DIR", mesh)
    monkeypatch.setattr(lvs, "MESH_DIR", tmp_path / "empty")
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    monkeypatch.setattr(lvs, "NROWS", 8)
    monkeypatch.setattr(lvs, "NCOLS", 8)
    res = check_tail_dependence_pilot()
    assert res.status in ("pass", "warn")


def test_check_ml_filter_branches(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    pkl = tmp_path / "model.pkl"
    pkl.write_bytes(b"x")
    monkeypatch.setattr(lvs, "HAIL_FILTER_PKL", pkl)
    monkeypatch.setattr(lvs, "ANALYSIS", tmp_path)
    res = check_ml_filter_reliability()
    assert res.status == "warn"

    cal = tmp_path / "calibration"
    cal.mkdir()
    pd.DataFrame([{"brier_score": 0.35, "auc": 0.6}]).to_csv(
        cal / "hail_filter_diagnostics.csv", index=False
    )
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    res2 = check_ml_filter_reliability()
    assert res2.status == "warn"


def test_write_readme_and_parse_args(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    results = [CheckResult("a", "pass", "lit", "ok", {})]
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    write_readme(results)
    assert (tmp_path / "README.md").exists()
    monkeypatch.setattr(lvs.sys, "argv", ["prog", "--only", "poisson_dispersion"])
    args = parse_args()
    assert args.only == "poisson_dispersion"


def test_main_unknown_check(tmp_path, monkeypatch, capsys):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs.sys, "argv", ["prog", "--only", "not_real", "--out-dir", str(tmp_path)])
    monkeypatch.setattr(lvs, "_load_peaks", lambda: None)
    lvs.main()
    assert "unknown check" in capsys.readouterr().out


def test_all_registered_checks_callable():
    for name in CHECKS:
        assert callable(CHECKS[name])


def test_additional_skip_and_edge_branches(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    assert check_source_transition(None).status == "skip"
    assert check_source_transition(pd.DataFrame()).status == "skip"
    assert check_spc_detection_and_rounding().status == "skip"

    empty_pairs = tmp_path / "empty_pairs.csv"
    pd.DataFrame(columns=["spc_size_in", "mesh75_mm"]).to_csv(empty_pairs, index=False)
    monkeypatch.setattr(lvs, "PAIRS_CSV", empty_pairs)
    assert check_spc_detection_and_rounding().status == "skip"

    monkeypatch.setattr(lvs, "EVENT_CSV", tmp_path / "missing.csv")
    assert check_negative_binomial_events().status == "skip"

    short_events = tmp_path / "short_events.csv"
    pd.DataFrame({"start_date": ["2020-06-01"]}).to_csv(short_events, index=False)
    monkeypatch.setattr(lvs, "EVENT_CSV", short_events)
    assert check_negative_binomial_events().status == "skip"

    monkeypatch.setattr(lvs, "THRESH_CSV", tmp_path / "empty_thresh.csv")
    pd.DataFrame(columns=["xi"]).to_csv(lvs.THRESH_CSV, index=False)
    assert check_gpd_threshold_summary().status == "skip"

    monkeypatch.setattr(lvs, "CDF_DIR", tmp_path / "empty_cdf")
    assert check_rp_monotonicity().status == "skip"
    assert check_analytical_vs_stochastic().status == "skip"
    assert check_rp_ring_energy().status == "skip"

    monkeypatch.setattr(lvs, "HAIL_CLIM_DIR", tmp_path)
    assert check_literature_hail_day_benchmarks().status == "skip"

    bench = tmp_path / "threshold_benchmark_summary.csv"
    pd.DataFrame([{"threshold_key": "other", "gp_max_days_per_year": 1.0}]).to_csv(bench, index=False)
    assert check_literature_hail_day_benchmarks().status == "skip"

    assert check_tail_dependence_pilot().status == "skip"

    pkl = tmp_path / "model.pkl"
    pkl.write_bytes(b"x")
    monkeypatch.setattr(lvs, "HAIL_FILTER_PKL", pkl)
    monkeypatch.setattr(lvs, "ANALYSIS", tmp_path)
    cal = tmp_path / "calibration"
    cal.mkdir()
    pd.DataFrame(columns=["brier_score"]).to_csv(cal / "hail_filter_diagnostics.csv", index=False)
    assert check_ml_filter_reliability().status == "skip"


def test_composite_rp_mm_gpd_and_lognormal_paths():
    p_occ = np.array([[0.2]], dtype=np.float32)
    lognorm_mu = np.array([[np.log(25.0)]], dtype=np.float32)
    lognorm_sigma = np.array([[0.2]], dtype=np.float32)
    gpd_xi = np.array([[0.0]], dtype=np.float32)
    gpd_sigma = np.array([[3.0]], dtype=np.float32)
    gpd_threshold = np.array([[45.0]], dtype=np.float32)
    fit_type = np.array([[2]], dtype=np.int8)
    val = _composite_rp_mm(
        0, 0, 1000, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type,
    )
    assert val > 0

    fit_log = np.array([[1]], dtype=np.int8)
    val2 = _composite_rp_mm(
        0, 0, 50, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_log,
    )
    assert val2 > 0


def test_bootstrap_and_rural_urban_skip_paths(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    small = np.zeros((5, 5), dtype=np.int8)
    small[0, 0] = 1
    np.savez(
        tmp_path / "small.npz",
        fit_type=small,
        p_occ=np.full((5, 5), 0.1, dtype=np.float32),
        lognorm_mu=np.full((5, 5), 1.0, dtype=np.float32),
        lognorm_sigma=np.full((5, 5), 0.2, dtype=np.float32),
        gpd_xi=np.zeros((5, 5), dtype=np.float32),
        gpd_sigma=np.full((5, 5), 1.0, dtype=np.float32),
        gpd_threshold=np.full((5, 5), 50.0, dtype=np.float32),
    )
    monkeypatch.setattr(lvs, "CDF_NPZ", tmp_path / "small.npz")
    assert check_bootstrap_rp_ci().status == "skip"

    pairs = tmp_path / "pairs.csv"
    pd.DataFrame(
        {
            "lat": [40.0, 46.0],
            "lon": [-100.0, -110.0],
            "spc_size_in": [1.5, 1.5],
            "mesh75_mm": [30.0, 28.0],
        }
    ).to_csv(pairs, index=False)
    monkeypatch.setattr(lvs, "PAIRS_CSV", pairs)
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    assert check_spc_rural_urban_bias().status == "skip"


def test_load_peaks_skips_unreadable_tif(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    corr = tmp_path / "corrected"
    (corr / "2015").mkdir(parents=True)
    (corr / "2015" / "mesh_20150601.tif").write_bytes(b"bad")
    write_mesh_tif(corr / "2015" / "mesh_20150602.tif", peak=40.0)
    monkeypatch.setattr(lvs, "PEAKS_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(lvs, "CORRECTED_DIR", corr)
    df = _load_peaks()
    assert df is not None
    assert len(df) == 1

