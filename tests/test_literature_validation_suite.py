"""Tests for literature_validation_suite helpers."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.diagnostics.literature_validation_suite import (
    CHECKS,
    CheckResult,
    _cell_latlon,
    _composite_rp_mm,
    _nearest_metro_km,
    check_bootstrap_rp_ci,
    check_gridrad_upstream_qc,
    check_ml_filter_reliability,
    check_negative_binomial_events,
    check_spc_rural_urban_bias,
    mann_kendall_statistic,
)


def test_checks_registry_has_fifteen():
    assert len(CHECKS) == 15


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

