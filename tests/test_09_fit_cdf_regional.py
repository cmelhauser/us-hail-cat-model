import numpy as np
import pytest
from conftest import load_stage


def test_stage09_lognormal_fit_returns_finite_values():
    s = load_stage("09_fit_cdf_regional.py")
    mu, sig = s.lmom_fit_lognormal(np.array([10, 20, 30, 40, 50], dtype=np.float32))
    assert np.isfinite(mu)
    assert np.isfinite(sig)
    assert sig > 0


def test_stage09_threshold_selection_returns_positive_threshold(tmp_path, monkeypatch):
    s = load_stage("09_fit_cdf_regional.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "THRESHOLD_SELECTION_FILE", tmp_path / "threshold_selection.csv")
    rng = np.random.default_rng(1)
    data = 25 + rng.gamma(shape=2.0, scale=15.0, size=200)
    u = s.compute_mrl_and_threshold(data.astype(np.float32), region_id=0)
    assert u > 0
    assert (tmp_path / "threshold_selection.csv").exists()
    candidates = [
        row for row in s.THRESHOLD_DIAGNOSTICS if row.get("reason") != "too_few_observations_default"
    ]
    assert candidates
    for row in candidates:
        assert 0.0 <= row["score"] <= 1.0
        assert 0.0 <= row["gof_score_normalized"] <= 1.0
        assert 0.0 <= row["count_penalty_normalized"] <= 1.0


def _write_mesh_year(mesh_dir, year: int, peak: float, *, nrows=4, ncols=4) -> None:
    import rasterio
    from rasterio.transform import from_origin

    ydir = mesh_dir / str(year)
    ydir.mkdir(parents=True, exist_ok=True)
    data = np.zeros((nrows, ncols), dtype=np.float32)
    data[1, 1] = peak
    data[2, 2] = peak * 0.8
    path = ydir / f"mesh_{year}0601.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-100, 40, 0.05, 0.05),
    ) as dst:
        dst.write(data, 1)


def _stage09_small_grid(monkeypatch, s, tmp_path):
    mesh_dir = tmp_path / "mesh"
    out_dir = tmp_path / "cdf"
    mesh_dir.mkdir()
    out_dir.mkdir()
    monkeypatch.setattr(s, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s, "OUT_DIR", out_dir)
    monkeypatch.setattr(s, "THRESHOLD_SELECTION_FILE", out_dir / "threshold_selection.csv")
    monkeypatch.setattr(s, "NROWS", 4)
    monkeypatch.setattr(s, "NCOLS", 4)
    monkeypatch.setattr(s, "LAT_MAX", 40.0)
    monkeypatch.setattr(s, "LON_MIN", -100.0)
    monkeypatch.setattr(s, "DX", 0.05)
    monkeypatch.setattr(s, "MIN_YEARS_FOR_FIT", 2)
    monkeypatch.setattr(s, "MIN_REGION_EXCEEDANCES", 5)
    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 2)
    monkeypatch.setattr(s, "DEFAULT_N_REGIONS", 2)
    monkeypatch.setattr(s, "RP_YEARS", [10, 100, 1000])
    s.THRESHOLD_DIAGNOSTICS.clear()
    return mesh_dir, out_dir


def test_stage09_lmom_helpers_and_clustering(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    mesh_dir, _ = _stage09_small_grid(monkeypatch, s, tmp_path)

    for year, peak in ((2018, 55.0), (2019, 65.0), (2020, 75.0)):
        _write_mesh_year(mesh_dir, year, peak)

    annual_max, years = s.build_annual_max_series()
    assert years == [2018, 2019, 2020]
    assert float(annual_max.max()) == 75.0

    t, t3, l2 = s.compute_lmoment_ratios(np.array([10.0, 20.0], dtype=np.float32))
    assert np.isnan(t) and np.isnan(t3) and np.isnan(l2)
    t, t3, l2 = s.compute_lmoment_ratios(np.array([10, 20, 30, 40, 50], dtype=float))
    assert np.isfinite(t) and np.isfinite(t3)

    region_map, active, rows, cols = s.cluster_cells(annual_max, n_regions=2)
    assert active.any()
    assert (region_map >= 0).any()

    xi, sig = s.lmom_fit_gpd(np.array([5, 6, 7, 8, 9, 10, 11, 12], dtype=np.float32))
    assert np.isfinite(xi) or np.isnan(xi)


def test_stage09_mrl_threshold_branches(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    _, out_dir = _stage09_small_grid(monkeypatch, s, tmp_path)

    u_small = s.compute_mrl_and_threshold(np.array([30, 35, 40], dtype=np.float32), region_id=0)
    assert u_small == s.DEFAULT_GPD_THRESHOLD_MM

    rng = np.random.default_rng(0)
    data = 30 + rng.gamma(2.0, 12.0, size=120)
    u = s.compute_mrl_and_threshold(data.astype(np.float32), region_id=1)
    assert u > 0
    assert (out_dir / "threshold_selection.csv").exists()
    assert any(row.get("selected") == 1 for row in s.THRESHOLD_DIAGNOSTICS)


def test_stage09_fit_regional_gpd_and_return_periods(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    mesh_dir, out_dir = _stage09_small_grid(monkeypatch, s, tmp_path)

    for year, peak in ((2015, 60.0), (2016, 70.0), (2017, 80.0), (2018, 90.0), (2019, 100.0)):
        _write_mesh_year(mesh_dir, year, peak)

    annual_max, _years = s.build_annual_max_series()
    region_map, _active, _rows, _cols = s.cluster_cells(annual_max, n_regions=2)
    (
        p_occ,
        lognorm_mu,
        lognorm_sigma,
        gpd_xi,
        gpd_sigma,
        gpd_threshold,
        fit_type,
        region_xi,
        _region_thresholds,
        fit_report,
    ) = s.fit_regional_gpd(annual_max, region_map, n_regions=2)
    assert fit_report
    assert (fit_type > 0).any()

    rp_maps = s.compute_return_periods(
        p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type
    )
    assert 10 in rp_maps
    assert float(rp_maps[10].max()) >= 0.0

    written = []

    def capture_write(arr, path, **_kw):
        written.append(path.name)
        path.write_bytes(b"tif")

    monkeypatch.setattr(s, "write_geotiff", capture_write)
    s.save_outputs(
        p_occ,
        lognorm_mu,
        lognorm_sigma,
        gpd_xi,
        gpd_sigma,
        gpd_threshold,
        fit_type,
        region_map,
        region_xi,
        rp_maps,
        fit_report,
    )
    assert (out_dir / "cdf_parameters.npz").exists()
    assert any(name.startswith("rp_") for name in written)


def test_stage09_validate_and_main(load_script, tmp_path, monkeypatch):
    import sys

    import pytest

    s = load_script("09_fit_cdf_regional.py")
    mesh_dir, out_dir = _stage09_small_grid(monkeypatch, s, tmp_path)

    monkeypatch.setattr(sys, "argv", ["09_fit_cdf_regional.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 1

    for year, peak in ((2015, 60.0), (2016, 70.0), (2017, 80.0), (2018, 90.0), (2019, 100.0)):
        _write_mesh_year(mesh_dir, year, peak)

    monkeypatch.setattr(sys, "argv", ["09_fit_cdf_regional.py", "--n-regions", "2"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0
    assert s.validate_outputs() is True


def test_stage09_remaining_fit_branches(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    mesh_dir, out_dir = _stage09_small_grid(monkeypatch, s, tmp_path)
    monkeypatch.setattr(s, "RP_YEARS", [10, 100])

    annual_max = np.zeros((3, 4, 4), dtype=np.float32)
    annual_max[:, 1, 1] = [40.0, 45.0, 50.0]
    annual_max[:, 2, 2] = [80.0, 90.0, 100.0]
    region_map = np.full((4, 4), -1, dtype=np.int8)
    region_map[1, 1] = 0
    region_map[2, 2] = 1

    (
        p_occ,
        lognorm_mu,
        lognorm_sigma,
        gpd_xi,
        gpd_sigma,
        gpd_threshold,
        fit_type,
        region_xi,
        _region_thresholds,
        fit_report,
    ) = s.fit_regional_gpd(annual_max, region_map, n_regions=2)
    assert fit_report

    fit_type[2, 2] = 2
    gpd_xi[2, 2] = 0.0
    gpd_sigma[2, 2] = 5.0
    gpd_threshold[2, 2] = 50.0
    lognorm_mu[2, 2] = 3.0
    lognorm_sigma[2, 2] = 0.3
    p_occ[2, 2] = 0.5
    rp_maps = s.compute_return_periods(
        p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type
    )
    assert rp_maps[100][2, 2] >= 0.0

    mu, sig = s.lmom_fit_lognormal(np.array([2.0], dtype=np.float32))
    assert np.isnan(mu) and np.isnan(sig)


def test_stage09_lmom_success_and_gpd_fallback(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    mesh_dir, _ = _stage09_small_grid(monkeypatch, s, tmp_path)
    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 5)
    monkeypatch.setattr(s, "MIN_REGION_EXCEEDANCES", 3)

    class FakeLm:
        class distr:  # noqa: N801  # mirrors lmoments3.distr API
            class ln3:  # noqa: N801
                @staticmethod
                def lmom_fit(data):
                    return {"mu": 3.5, "sigma": 0.4}

            class gpa:  # noqa: N801
                @staticmethod
                def lmom_fit(data):
                    return {"c": 0.1, "scale": 5.0}

    monkeypatch.setitem(__import__("sys").modules, "lmoments3", FakeLm())
    mu, sig = s.lmom_fit_lognormal(np.array([10, 20, 30, 40], dtype=np.float32))
    assert mu == 3.5 and sig == 0.4
    xi, sigma = s.lmom_fit_gpd(np.array([1, 2, 3, 4, 5, 6], dtype=np.float32))
    assert xi == 0.1 and sigma == 5.0

    annual_max = np.zeros((5, 4, 4), dtype=np.float32)
    annual_max[:, 1, 1] = [55.0, 60.0, 65.0, 70.0, 75.0]
    region_map = np.full((4, 4), -1, dtype=np.int8)
    region_map[1, 1] = 0
    (
        p_occ,
        lognorm_mu,
        lognorm_sigma,
        gpd_xi,
        gpd_sigma,
        gpd_threshold,
        fit_type,
        region_xi,
        _region_thresholds,
        fit_report,
    ) = s.fit_regional_gpd(annual_max, region_map, n_regions=1)
    assert fit_report
    assert (fit_type > 0).any()

    # Regional sigma fallback when 0 < cell_exc < MIN_EXCEEDANCES_GPD
    annual_max2 = np.zeros((5, 4, 4), dtype=np.float32)
    annual_max2[:, 2, 2] = [52.0, 53.0, 54.0, 55.0, 56.0]
    region_map2 = np.full((4, 4), -1, dtype=np.int8)
    region_map2[2, 2] = 0
    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 10)
    out = s.fit_regional_gpd(annual_max2, region_map2, n_regions=1)
    assert out[-1]


def test_stage09_compute_return_periods_skips_zero_p(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    _stage09_small_grid(monkeypatch, s, tmp_path)
    p_occ = np.zeros((4, 4), dtype=np.float32)
    p_occ[1, 1] = 0.0
    fit_type = np.zeros((4, 4), dtype=np.int8)
    fit_type[1, 1] = 1
    lognorm_mu = np.full((4, 4), 3.0, dtype=np.float32)
    lognorm_sigma = np.full((4, 4), 0.3, dtype=np.float32)
    gpd_xi = np.zeros((4, 4), dtype=np.float32)
    gpd_sigma = np.ones((4, 4), dtype=np.float32)
    gpd_threshold = np.full((4, 4), 50.0, dtype=np.float32)
    rp_maps = s.compute_return_periods(
        p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type
    )
    assert rp_maps[10][1, 1] == 0.0


def test_stage09_cluster_empty_active(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    _stage09_small_grid(monkeypatch, s, tmp_path)
    annual_max = np.zeros((3, 4, 4), dtype=np.float32)
    with pytest.raises(RuntimeError, match="No active hail cells"):
        s.cluster_cells(annual_max, n_regions=2)
