"""Targeted tests for the last uncovered lines toward 100% scripts/ coverage."""

from __future__ import annotations

import builtins
import importlib.util
import sys
import types
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import requests

from conftest import REPO_ROOT, load_stage
from scripts._io import write_geotiff
from tests._diagnostics_fixtures import seed_mesh_days, write_mesh_tif
from tests.test_01_download_myrorss_coverage import _FakeS3 as _FakeS3Stage01
from tests.test_02_download_mrms_mesh_coverage import _FakeS3 as _FakeS3Stage02


# ---------------------------------------------------------------------------
# Stage 09
# ---------------------------------------------------------------------------


def test_stage09_lmom_zero_l2_and_mrl_branches(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    monkeypatch.setattr(s, "NROWS", 6)
    monkeypatch.setattr(s, "NCOLS", 6)

    t, t3, l2 = s.compute_lmoment_ratios(np.zeros(4, dtype=np.float32))
    assert np.isnan(t) and np.isnan(t3) and np.isnan(l2)

    s.THRESHOLD_DIAGNOSTICS = []
    with patch("scipy.stats.genpareto.fit", side_effect=RuntimeError("bad fit")):
        exc = np.linspace(55, 120, 35, dtype=np.float64)
        thr = s.compute_mrl_and_threshold(exc, region_id=9)
        assert thr > 0

    s.THRESHOLD_DIAGNOSTICS = []
    tiny = np.array([50.0, 51.0, 52.0, 53.0, 54.0], dtype=np.float64)
    thr2 = s.compute_mrl_and_threshold(tiny, region_id=10)
    assert thr2 == s.DEFAULT_GPD_THRESHOLD_MM

    s.THRESHOLD_DIAGNOSTICS = []
    exc2 = np.linspace(60, 130, 40, dtype=np.float64)
    with patch("matplotlib.pyplot.savefig", side_effect=OSError("disk full")):
        s.compute_mrl_and_threshold(exc2, region_id=11)

    annual_max = np.zeros((8, 4, 4), dtype=np.float32)
    annual_max[:, 0, 0] = np.linspace(50, 90, 8)
    annual_max[:, 0, 1] = np.linspace(45, 55, 8)
    region_map = np.full((4, 4), -1, dtype=np.int8)
    region_map[0, 0] = 0
    region_map[0, 1] = 0

    real_lmom = s.lmom_fit_lognormal

    def bad_lmom(_nz):
        return np.nan, np.nan

    monkeypatch.setattr(s, "lmom_fit_gpd", lambda _x: (1.5, 1.0))
    monkeypatch.setattr(s, "compute_mrl_and_threshold", lambda _x, _r: 44.0)
    monkeypatch.setattr(s, "lmom_fit_lognormal", bad_lmom)
    s.fit_regional_gpd(annual_max, region_map, 1)

    monkeypatch.setattr(s, "lmom_fit_lognormal", real_lmom)
    monkeypatch.setattr(s, "lmom_fit_gpd", lambda _x: (1.5, 1.0))
    s.fit_regional_gpd(annual_max, region_map, 1)

    monkeypatch.setattr(s, "RP_YEARS", [10000])
    p_occ = np.zeros((6, 6), dtype=np.float32)
    p_occ[2, 2] = 0.02
    lognorm_mu = np.full((6, 6), np.log(45.0), dtype=np.float32)
    lognorm_sigma = np.full((6, 6), 0.2, dtype=np.float32)
    gpd_xi = np.full((6, 6), 0.15, dtype=np.float32)
    gpd_sigma = np.full((6, 6), 8.0, dtype=np.float32)
    gpd_threshold = np.full((6, 6), 50.0, dtype=np.float32)
    fit_type = np.zeros((6, 6), dtype=np.int8)
    fit_type[2, 2] = 2
    rp_maps = s.compute_return_periods(
        p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type,
    )
    assert rp_maps[10000][2, 2] > 50.0


# ---------------------------------------------------------------------------
# Stage 04b
# ---------------------------------------------------------------------------


def test_stage04b_catalog_download_residual_branches(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)
    monkeypatch.setattr(s, "time", type("T", (), {"sleep": lambda *_a, **_k: None})())

    real_range = builtins.range

    def patched_range(*args):
        if args == (10,):
            return iter([])
        return real_range(*args)

    monkeypatch.setattr(builtins, "range", patched_range)
    with pytest.raises(RuntimeError, match="exhausted retries"):
        s._catalog_get(types.SimpleNamespace(), "http://x", timeout=(1.0, 1.0))
    monkeypatch.setattr(builtins, "range", real_range)

    class Resp404:
        status_code = 404
        text = ""

        def raise_for_status(self):
            return None

    class SessSevereDay404:
        def get(self, url, timeout=60, stream=False):
            if url.endswith("20150501/catalog.xml"):
                return Resp404()
            r = Resp404()
            r.status_code = 200
            r.text = (
                '<?xml version="1.0"?>'
                '<catalog xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0" '
                'xmlns:xlink="http://www.w3.org/1999/xlink">'
                '<catalogRef xlink:title="20150501" xlink:href="20150501/catalog.xml"/>'
                "</catalog>"
            )
            return r

    assert s.list_day_catalog_files(
        SessSevereDay404(), s.DS_SEVERE, day, timeout=(1.0, 1.0),
    ) == []

    with pytest.raises(ValueError, match="Unknown dsid"):
        s.list_day_catalog_files(
            types.SimpleNamespace(), "not-a-dsid", day, timeout=(1.0, 1.0),
        )

    item = s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename="f.nc",
        url="http://example.com/f.nc",
        out_path=tmp_path / "f.nc",
    )
    tmp_part = item.out_path.with_suffix(item.out_path.suffix + ".tmp")
    tmp_part.write_bytes(b"partial")

    class Resp404Stream:
        status_code = 404

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    _, st404 = s._download_one(
        types.SimpleNamespace(get=lambda *a, **k: Resp404Stream()),
        item,
        connect_timeout=1.0,
        read_timeout=1.0,
    )
    assert st404 == "missing"

    item2 = s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename="err.nc",
        url="http://example.com/err.nc",
        out_path=tmp_path / "err.nc",
    )

    class Resp500:
        status_code = 500

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

        def iter_content(self, chunk_size=0):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class Sess500Once:
        def __init__(self):
            self.n = 0

        def get(self, url, params=None, stream=True, timeout=None):
            self.n += 1
            item2.out_path.with_suffix(item2.out_path.suffix + ".tmp").write_bytes(b"x")
            return Resp500()

    monkeypatch.setattr(s, "_retryable_http_error", lambda _e: True)
    with pytest.raises(requests.HTTPError):
        s._download_one(Sess500Once(), item2, connect_timeout=1.0, read_timeout=1.0)

    item3 = s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename="conn.nc",
        url="http://example.com/conn.nc",
        out_path=tmp_path / "conn.nc",
    )

    class SessConnOnce:
        def __init__(self):
            self.n = 0

        def get(self, url, params=None, stream=True, timeout=None):
            self.n += 1
            item3.out_path.with_suffix(item3.out_path.suffix + ".tmp").write_bytes(b"x")
            raise requests.ConnectionError("down")

    with pytest.raises(requests.ConnectionError):
        s._download_one(SessConnOnce(), item3, connect_timeout=1.0, read_timeout=1.0)

    bad_item = s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename="weird.nc",
        url="http://example.com/weird.nc",
        out_path=tmp_path / "weird.nc",
    )

    def fake_download_one(*_a, **_k):
        return bad_item, "corrupt"

    monkeypatch.setattr(s, "_download_one", fake_download_one)
    stats = s.download_planned_items(
        types.SimpleNamespace(),
        [bad_item],
        connect_timeout=1.0,
        read_timeout=1.0,
        max_workers=1,
    )
    assert stats["errors"] == 1

    monkeypatch.setattr(s, "severe_catalog_has_convective_data", lambda *_a, **_k: True)
    monkeypatch.setattr(s, "_severe_staging_covers_day", lambda _d: False)
    calls = {"n": 0}

    def fake_day_dl(*_a, **k):
        calls["n"] += 1
        return {"downloaded": calls["n"]}

    monkeypatch.setattr(s, "download_for_day", fake_day_dl)
    out = s.download_for_day_adaptive(
        types.SimpleNamespace(),
        day,
        catalog_timeout=(1.0, 1.0),
        connect_timeout=1.0,
        read_timeout=1.0,
        max_workers=1,
    )
    assert out["source_mode"] == "severe+hourly-fill"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Stage 05
# ---------------------------------------------------------------------------


def test_stage05_era_pooled_and_validate_read_errors(load_script, tmp_path, monkeypatch):
    from tests.test_05_apply_mesh_bias_correction import _write_mesh

    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)
    monkeypatch.setattr(s, "OUT_DIR", out_dir)
    monkeypatch.setattr(s, "CAL_DIR", tmp_path / "cal")
    monkeypatch.setattr(s, "NROWS", 2)
    monkeypatch.setattr(s, "NCOLS", 2)

    for year in range(s.OVERLAP_START_YEAR, s.OVERLAP_END_YEAR + 1):
        ydir = in_dir / str(year)
        ydir.mkdir(parents=True, exist_ok=True)
        _write_mesh(ydir / "mesh_20100601.tif", np.full((2, 2), 40.0, dtype=np.float32))
        _write_mesh(ydir / f"mesh_{year}0601.tif", np.full((2, 2), 40.0, dtype=np.float32))

    monkeypatch.setattr(
        s,
        "is_gridrad_source",
        lambda d: d.startswith("201") and d != "20100601",
    )
    s._collect_era_pooled_calibration()

    monkeypatch.setattr(s, "load_gridrad_days", lambda: {"20120601"})
    (in_dir / "2012").mkdir(parents=True, exist_ok=True)
    _write_mesh(in_dir / "2012" / "mesh_20120601.tif", np.full((2, 2), 45.0, dtype=np.float32))
    (in_dir / "2012" / "mesh_badread.tif").write_bytes(b"not-tif")
    _write_mesh(in_dir / "2012" / "mesh_empty.tif", np.zeros((2, 2), dtype=np.float32))
    s.build_cross_calibration()

    good_in = in_dir / "2015" / "mesh_20150601.tif"
    good_in.parent.mkdir(parents=True, exist_ok=True)
    _write_mesh(good_in, np.full((2, 2), 40.0, dtype=np.float32))
    lat = np.zeros((2, 2), dtype=np.float32)
    sidecar = s.persistence_history_path(out_dir / "mesh_20150601.tif")
    if sidecar.exists():
        sidecar.unlink()
    frame = s.load_persistence_history_frame(
        out_dir / "mesh_20150601.tif",
        good_in,
        np.zeros((3, 3), dtype=np.float32),
        skip_ml=True,
    )
    assert frame is None

    import rasterio
    from rasterio.transform import from_origin

    good_out = out_dir / "2015" / "mesh_20150601.tif"
    good_out.parent.mkdir(parents=True, exist_ok=True)
    write_geotiff(np.zeros((2, 2), dtype=np.float32), good_out)
    bad_read = out_dir / "2015" / "mesh_20150602.tif"
    bad_read.write_bytes(b"bad")
    bad_vals = out_dir / "2015" / "mesh_20150603.tif"
    write_geotiff(np.full((2, 2), 500.0, dtype=np.float32), bad_vals)
    _write_mesh(in_dir / "2015" / "mesh_20150601.tif", np.zeros((2, 2), dtype=np.float32))
    _write_mesh(in_dir / "2015" / "mesh_20150602.tif", np.zeros((2, 2), dtype=np.float32))
    _write_mesh(in_dir / "2015" / "mesh_20150603.tif", np.zeros((2, 2), dtype=np.float32))

    class FixedRandom:
        def __init__(self, _seed):
            pass

        def sample(self, population, k):
            return [bad_read]

    monkeypatch.setattr("random.Random", FixedRandom)
    assert s.validate_outputs() is False


# ---------------------------------------------------------------------------
# Stage 08
# ---------------------------------------------------------------------------


def test_stage08_progress_overlap_centroid_validate(load_script, tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("08_build_event_catalog.py")
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)
    monkeypatch.setattr(s, "OUT_DIR", out_dir)

    good = in_dir / "2015" / "mesh_20150601.tif"
    good.parent.mkdir(parents=True)
    with rasterio.open(
        good,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-100, 40, 0.05, 0.05),
    ) as dst:
        dst.write(np.array([[0, 30, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=np.float32), 1)

    orig_rglob = Path.rglob

    def fake_rglob(self, pattern):
        if self == in_dir and pattern == "mesh_*.tif":
            return iter([good] * 1001)
        return orig_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    dates, cells = s.load_daily_data()
    assert len(dates) >= 1

    r1 = np.array([10], dtype=np.int16)
    c1 = np.array([10], dtype=np.int16)
    r2 = np.array([10, 20], dtype=np.int16)
    c2 = np.array([20, 10], dtype=np.int16)
    assert s.footprints_overlap_sparse(r1, c1, r2, c2, buffer=0) is False

    r1b = np.array([0, 1], dtype=np.int16)
    c1b = np.array([0, 1], dtype=np.int16)
    r2b = np.array([1], dtype=np.int16)
    c2b = np.array([1], dtype=np.int16)
    assert s.footprints_overlap_sparse(r1b, c1b, r2b, c2b, buffer=1) is True

    groups = [[0]]
    daily = [{
        "rows": np.array([0], dtype=np.int16),
        "cols": np.array([0], dtype=np.int16),
        "vals": np.array([0.0], dtype=np.float32),
    }]
    monkeypatch.setattr(s, "DAMAGE_THRESHOLD_MM", 0.0)
    df, _sparse = s.build_catalog([date(2015, 6, 1)], daily, groups)
    assert len(df) == 1

    (out_dir / "event_catalog.csv").write_text("event_id\n1\n2\n")
    np.savez(out_dir / "event_peaks.npz", n_events=np.array([1]))
    assert s.validate_outputs() is False


# ---------------------------------------------------------------------------
# Stage 02 / 01 rebuild continue
# ---------------------------------------------------------------------------


def test_stage02_missing_dir_and_rebuild_continue(load_script, tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("02_download_mrms_mesh.py")
    missing = tmp_path / "missing_out"
    monkeypatch.setattr(s, "OUT_DIR", missing)
    assert s.validate_outputs() is False

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    monkeypatch.setattr(s, "OUT_DIR", out_dir)
    good = out_dir / "2020" / "mesh_20201014.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((s.NROWS, s.NCOLS), dtype=np.float32), good)
    bad_shape = out_dir / "2020" / "mesh_20201015.tif"
    with rasterio.open(
        bad_shape,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-125, 50, 0.05, 0.05),
    ) as dst:
        dst.write(np.zeros((4, 4), dtype=np.float32), 1)

    orig_rglob = Path.rglob

    def fake_rglob(self, pattern):
        if self == out_dir and pattern == "mesh_????????.tif":
            phantoms = [out_dir / f"mesh_{20201016 + i:08d}.tif" for i in range(1000)]
            return iter([good, bad_shape, *phantoms])
        return orig_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)

    class FixedRandom:
        def __init__(self, _seed):
            pass

        def sample(self, population, k):
            return [bad_shape]

    monkeypatch.setattr("random.Random", FixedRandom)
    assert s.validate_outputs() is False

    key = "CONUS/MESH_00.50/20200601/MRMS_MESH_00.50_20200601-130000.grib2.gz"
    s3 = _FakeS3Stage02({key: b"x"})
    assert s.rebuild_manifest_from_outputs(s3, date(2020, 6, 1), date(2020, 6, 1)) == 0


def test_stage01_rebuild_continue_branch(load_script, tmp_path, monkeypatch):
    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda *_a, **_k: ["k.netcdf"])
    s3 = _FakeS3Stage01({})
    assert s.rebuild_manifest_from_outputs(s3, date(1998, 6, 1), date(1998, 6, 1)) == 0


# ---------------------------------------------------------------------------
# Stage 04a
# ---------------------------------------------------------------------------


def test_stage04a_empty_chunk_licence_time_isotherm(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)

    empty = tmp_path / "empty.nc"
    empty.write_bytes(b"")
    fresh = tmp_path / "fresh.nc"
    unlinked = {"empty": False}
    orig_unlink = Path.unlink

    def track_unlink(self, missing_ok=False):
        if self == empty:
            unlinked["empty"] = True
        return orig_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", track_unlink)

    class FakeClient:
        def retrieve(self, dataset, request, path):
            from tests.test_04a_download_era5_coverage import _pressure_chunk

            _pressure_chunk(Path(path), int(request["year"][0]))

    s._retrieve_era5_chunk(FakeClient(), ["1991"], ["01"], empty)
    assert unlinked["empty"]
    s._retrieve_era5_chunk(FakeClient(), ["1991"], ["01"], fresh)
    assert fresh.stat().st_size > 0

    monkeypatch.setattr(s, "CLIM_YEARS", ["1991"])
    yearly = tmp_path / "pressure_chunks" / "era5_monthly_temp_plevels_conus_1991.nc"
    yearly.parent.mkdir(parents=True, exist_ok=True)

    class CostLimitClient:
        def retrieve(self, dataset, request, path):
            if len(request["month"]) > 1:
                raise Exception("cost limits exceeded")
            from tests.test_04a_download_era5_coverage import _pressure_chunk

            _pressure_chunk(Path(path), int(request["year"][0]))

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": CostLimitClient})
    chunks = s.download_era5_temperature()
    assert len(chunks) >= 1

    sfc = tmp_path / "era5_surface_geopotential_conus.nc"

    class LicenceClient:
        def retrieve(self, dataset, request, path):
            raise Exception("403 Client Error: Forbidden required licences not accepted")

    with pytest.raises(RuntimeError, match="licence"):
        s._retrieve_era5_chunk(LicenceClient(), ["2020"], ["01"], sfc)

    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)
    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": LicenceClient})
    with pytest.raises(RuntimeError, match="licence"):
        s.download_era5_surface_geopotential()

    class FakeCoordDs:
        dims = {}
        coords = {"valid_time": True}

        def __getitem__(self, name):
            return types.SimpleNamespace(dims=("valid_time",))

    assert s._time_dim_name(FakeCoordDs()) == "valid_time"

    lats = np.array([40.0], dtype=np.float32)
    lons = np.array([-100.0], dtype=np.float32)
    temp_monthly = np.zeros((12, 3, 1, 1), dtype=np.float32)
    heights_monthly = np.zeros((12, 3, 1, 1), dtype=np.float32)
    temp_monthly[0, :, 0, 0] = np.array([260.0, 268.0, 276.0], dtype=np.float32)
    heights_monthly[0, :, 0, 0] = np.array([9000.0, 7500.0, 6000.0], dtype=np.float32)
    counts = np.ones(12, dtype=np.int32)

    monkeypatch.setattr(
        s,
        "_load_pressure_climatology",
        lambda _files: (temp_monthly, heights_monthly, lats, lons, counts),
    )

    import xarray as xr

    sfc_path = tmp_path / "sfc.nc"
    ds_sfc = xr.Dataset({"z": (("latitude", "longitude"), np.array([[0.0]], dtype=np.float32))})
    ds_sfc.to_netcdf(sfc_path)
    monkeypatch.setattr(s, "OUT_FILE", tmp_path / "isotherms.nc")
    s.compute_isotherm_heights([fresh], sfc_path)


# ---------------------------------------------------------------------------
# Stage 04c
# ---------------------------------------------------------------------------


def test_stage04c_severe_only_and_qc_import_branch(load_script, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    import netCDF4 as nc

    s = load_script("04c_fill_gridrad_gap.py")
    day = date(2015, 5, 20)
    sev_t = datetime(2015, 5, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(s, "GRIDRAD_SEV", tmp_path / "sev")
    monkeypatch.setattr(s, "GRIDRAD_DIR", tmp_path / "hr")
    sev_dir = tmp_path / "sev" / "by_convective_day" / "20150520"
    hr_dir = tmp_path / "hr" / "by_convective_day" / "20150520"
    sev_dir.mkdir(parents=True)
    hr_dir.mkdir(parents=True)
    sev_nc = sev_dir / "nexrad_3d_v4_2_20150520T120000Z.nc"
    hr_nc = hr_dir / "nexrad_3d_v3_1_20150520T130000Z.nc"
    sev_nc.write_bytes(b"x")
    hr_nc.write_bytes(b"x")
    monkeypatch.setattr(
        s,
        "staged_nc_files_for_convective_day",
        lambda base, _d: list((base / "by_convective_day" / "20150520").glob("*.nc")),
    )
    monkeypatch.setattr(
        s,
        "observation_times_from_paths",
        lambda paths, _d: [sev_t for _ in paths],
    )
    monkeypatch.setattr(s, "convective_window_coverage_ok", lambda *_a, **_k: False)
    monkeypatch.setattr(s, "_hourly_fill_for_severe_gaps", lambda *_a, **_k: [])
    files, src = s.find_gridrad_files(day)
    assert src == "gridrad-severe-5min"
    assert files

    nc_path = tmp_path / "native_qc.nc"
    with nc.Dataset(nc_path, "w") as ds:
        ds.createDimension("alt", 2)
        ds.createDimension("lat", 1)
        ds.createDimension("lon", 1)
        ds.createDimension("sparse", 2)
        ds.createVariable("Latitude", "f4", ("lat",))[:] = [35.0]
        ds.createVariable("Longitude", "f4", ("lon",))[:] = [-97.0]
        ds.createVariable("Altitude", "f4", ("alt",))[:] = [2.0, 4.0]
        ds.createVariable("index", "i8", ("sparse",))[:] = [0, 1]
        ds.createVariable("Reflectivity", "f4", ("sparse",))[:] = [55.0, 55.0]
        ds.createVariable("Nradobs", "f4", ("alt", "lat", "lon"))[:] = np.ones((2, 1, 1))
        ds.createVariable("Nradecho", "f4", ("alt", "lat", "lon"))[:] = np.ones((2, 1, 1))

    daily = np.zeros((s.OUT_NROWS, s.OUT_NCOLS), dtype=np.float32)
    monkeypatch.setattr(s, "get_freezing_levels_era5", lambda *_a, **_k: (2.0, 5.0))
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "_gridrad_qc":
            raise ImportError("forced bare import failure")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        s.process_gridrad_file(nc_path, daily, 5, native_qc=True)


# ---------------------------------------------------------------------------
# Stage 13
# ---------------------------------------------------------------------------


def test_stage13_validate_and_streamed_main(load_script, tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from tests.test_13_generate_stochastic_catalog import _stage13_paths

    s = load_script("13_generate_stochastic_catalog.py")
    _event_dir, _out, cat_dir, map_dir, pet_dir, _mask = _stage13_paths(monkeypatch, s, tmp_path)
    monkeypatch.setattr(s, "RP_YEARS", [10])
    monkeypatch.setattr(s, "N_SIM_YEARS", 1000)

    manifest = cat_dir / "stochastic_catalog_manifest.json"
    manifest.write_text('{"n_years": 1000, "status": "complete", "seed": 42, "model_version": "2.3.0"}')
    pq.write_table(pa.table({"sim_year": pa.array([], type=pa.int32())}), cat_dir / "stochastic_event_summary.parquet")
    (map_dir / "rp_00010yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()
    assert s.validate_outputs() is False

    bad_table = pa.table({"sim_year": pa.array([-1, 2000], type=pa.int32())})
    pq.write_table(bad_table, cat_dir / "stochastic_event_summary.parquet")
    assert s.validate_outputs() is False

    stream_path = cat_dir / "stochastic_event_summary.parquet"

    def fake_sim(*_a, **kwargs):
        catalog_path = kwargs.get("catalog_path")
        if catalog_path is not None:
            pq.write_table(
                pa.table({
                    "sim_year": [0],
                    "event_idx": [0],
                    "template_id": [1],
                    "doy": [150],
                    "scale_factor": [1.0],
                    "peak_hail_mm": [40.0],
                    "n_cells": [1],
                }),
                catalog_path,
            )
        mmap_path = tmp_path / "_work" / "_ann_max_simulation.mmap"
        mmap_path.parent.mkdir(parents=True, exist_ok=True)
        mmap_path.write_bytes(b"\x00" * 64)
        return (
            np.zeros((2, 1), dtype=np.float32),
            np.array([1], dtype=np.int32),
            np.array([1], dtype=np.int32),
            np.array([40.0], dtype=np.float32),
            np.array([1], dtype=np.int32),
            np.array([1], dtype=np.int32),
            np.array([1], dtype=np.int32),
            pd.DataFrame(),
            mmap_path,
        )

    monkeypatch.setattr(s, "simulate_catalog", fake_sim)
    monkeypatch.setattr(s, "write_geotiff", lambda arr, path, **_kw: Path(path).write_bytes(b"tif"))
    monkeypatch.setattr(s, "load_historical_events", lambda: (pd.DataFrame(), {}))
    monkeypatch.setattr(s, "calibrate_sigma", lambda *_a, **_k: 0.2)
    monkeypatch.setattr(s, "build_doy_distribution", lambda *_a, **_k: np.ones(366) / 366)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["13_generate_stochastic_catalog.py", "--n-years", "1000"])
    if stream_path.exists():
        stream_path.unlink()
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


# ---------------------------------------------------------------------------
# LVS
# ---------------------------------------------------------------------------


def test_lvs_bootstrap_skip_converge_and_warn(tmp_path, monkeypatch):
    from scripts.diagnostics import literature_validation_suite as lvs

    n = 12
    arrays = {
        "fit_type": np.ones((n, n), dtype=np.int8),
        "p_occ": np.full((n, n), 0.25, dtype=np.float32),
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

    calls = {"n": 0}
    real_rp = lvs._composite_rp_mm

    def flaky_rp(*a, **k):
        if k.get("p_override") is not None or k.get("xi_override") is not None:
            return 0.0
        calls["n"] += 1
        return real_rp(*a, **k)

    monkeypatch.setattr(lvs, "_composite_rp_mm", flaky_rp)
    r_skip = lvs.check_bootstrap_rp_ci()
    assert r_skip.status == "skip"
    assert "converge" in r_skip.message.lower() or "bootstrap" in r_skip.message.lower()

    monkeypatch.setattr(lvs, "_composite_rp_mm", real_rp)

    def wide_percentile(arr, q, *a, **k):
        qs = list(q) if hasattr(q, "__iter__") else [q]
        if len(arr) >= 50 and qs == [2.5, 97.5]:
            return np.array([10.0, 500.0])
        return np.percentile(arr, q, *a, **k)

    monkeypatch.setattr(lvs.np, "percentile", wide_percentile)
    r_warn = lvs.check_bootstrap_rp_ci()
    assert r_warn.status == "warn"
    assert "wide CI" in r_warn.message


def test_lvs_tail_dependence_empty_chi_near(tmp_path, monkeypatch):
    from scripts.diagnostics import literature_validation_suite as lvs

    mesh = tmp_path / "mesh"
    monkeypatch.setattr(lvs, "_preferred_mesh_dir", lambda: mesh)
    monkeypatch.setattr(lvs, "_pooled_annual_max", lambda *_a, **_k: np.full((25, 25), 90.0, dtype=np.float32))
    out_tail = tmp_path / "out_tail"
    out_tail.mkdir()
    monkeypatch.setattr(lvs, "OUT_DIR", out_tail)
    monkeypatch.setattr(lvs, "NROWS", 25)
    monkeypatch.setattr(lvs, "NCOLS", 25)

    real_df = pd.DataFrame

    def fake_df(data=None, *a, **k):
        if isinstance(data, list) and data and isinstance(data[0], dict) and "distance_km_lo" in data[0]:
            return real_df([
                {"distance_km_lo": 150, "distance_km_hi": 300, "n_pairs": 5, "chi_u": 0.2},
                {"distance_km_lo": 300, "distance_km_hi": 600, "n_pairs": 5, "chi_u": 0.4},
            ])
        return real_df(data, *a, **k)

    monkeypatch.setattr(lvs.pd, "DataFrame", fake_df)
    res = lvs.check_tail_dependence_pilot()
    assert res.metrics.get("chi_50_150km") is None


def test_lvs_tail_dependence_distant_higher_warn(tmp_path, monkeypatch):
    from scripts.diagnostics import literature_validation_suite as lvs

    mesh = tmp_path / "mesh"
    monkeypatch.setattr(lvs, "_preferred_mesh_dir", lambda: mesh)
    monkeypatch.setattr(lvs, "_pooled_annual_max", lambda *_a, **_k: np.full((25, 25), 90.0, dtype=np.float32))
    out_tail2 = tmp_path / "out_tail2"
    out_tail2.mkdir()
    monkeypatch.setattr(lvs, "OUT_DIR", out_tail2)
    monkeypatch.setattr(lvs, "NROWS", 25)
    monkeypatch.setattr(lvs, "NCOLS", 25)

    real_df = pd.DataFrame

    def fake_df(data=None, *a, **k):
        if isinstance(data, list) and data and isinstance(data[0], dict) and "distance_km_lo" in data[0]:
            return real_df([
                {"distance_km_lo": 50, "distance_km_hi": 150, "n_pairs": 10, "chi_u": 0.1},
                {"distance_km_lo": 150, "distance_km_hi": 300, "n_pairs": 10, "chi_u": 0.2},
                {"distance_km_lo": 300, "distance_km_hi": 600, "n_pairs": 10, "chi_u": 0.9},
            ])
        return real_df(data, *a, **k)

    monkeypatch.setattr(lvs.pd, "DataFrame", fake_df)
    res = lvs.check_tail_dependence_pilot()
    assert res.status == "warn"
    assert "distant pairs" in res.message


# ---------------------------------------------------------------------------
# _radar_geometry + small leftovers
# ---------------------------------------------------------------------------


def test_radar_geometry_mrms_alias_and_persistence_loop(monkeypatch):
    import scripts._radar_geometry as rg
    from scripts._radar_geometry import apply_range_debias, remove_persistent_range_artifacts

    monkeypatch.setattr(rg, "NROWS", 8)
    monkeypatch.setattr(rg, "NCOLS", 8)
    debias = {
        "range_bin_edges_km": np.array([0, 100, 200], dtype=np.float32),
        "range_bin_centers_km": np.array([50, 150], dtype=np.float32),
        "factors": {
            "MYRORSS/MRMS": np.array([0.85, 0.95], dtype=np.float32),
            "MRMS": np.array([0.85, 0.95], dtype=np.float32),
        },
    }
    data = np.ones((8, 8), dtype=np.float32)
    rng = np.full((8, 8), 60.0, dtype=np.float32)
    out = apply_range_debias(data, rng, "MYRORSS/MRMS", debias)
    assert float(out[0, 0]) != 1.0

    quiet = np.zeros((8, 8), dtype=np.float32)
    site = np.zeros((8, 8), dtype=np.int16)
    out_q, n_q = remove_persistent_range_artifacts(quiet, site, rng, history=np.full((6, 8, 8), 10.0))
    assert n_q == 0

    site = np.zeros((8, 8), dtype=np.int16)
    site[:, :4] = 0
    site[:, 4:] = 1
    hist = np.full((6, 8, 8), 35.0, dtype=np.float32)
    active = np.full((8, 8), 40.0, dtype=np.float32)
    remove_persistent_range_artifacts(
        active, site, rng, history=hist, min_history_days=3, min_annulus_cells=1,
    )


def test_hdc_bad_filename_continue(tmp_path):
    import scripts.diagnostics.hail_day_climatology as hdc

    (tmp_path / "mesh_bad.tif").write_bytes(b"x")
    seed_mesh_days(tmp_path, [date(2010, 6, 1)], peak=35.0, nrows=8, ncols=8)
    assert len(list(hdc.iter_mesh_tifs(tmp_path, None, None))) == 1


def test_train_pos_cache_miss(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    mesh_dir = tmp_path / "corrected"
    write_mesh_tif(mesh_dir / "2015" / "mesh_20150601.tif", 60.0, nrows=8, ncols=8)
    nrows, ncols = 8, 8
    monkeypatch.setattr(trainer, "CORRECTED_DIR", mesh_dir)
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(trainer, "ensure_range_km_grid", lambda: np.full((nrows, ncols), 50.0, dtype=np.float32))
    monkeypatch.setattr(trainer, "ensure_nearest_site_index_grid", lambda: np.zeros((nrows, ncols), dtype=np.int16))
    monkeypatch.setattr(trainer, "azimuth_to_nearest_site_deg", lambda: np.zeros((nrows, ncols), dtype=np.float32))

    pairs = pd.DataFrame([
        {"date": "20150601", "grid_row": 4, "grid_col": 4, "spc_size_in": 1.5, "mesh75_mm": 60.0},
    ])
    X, y, _ = trainer.build_training_sets(
        pairs, max_neg_per_day=0, rng=np.random.default_rng(0), gridrad_only=False,
    )
    assert len(X) == 1

    loads: list[str] = []
    real_load = trainer._load_raster

    def counting_load(datestr):
        loads.append(datestr)
        return real_load(datestr)

    monkeypatch.setattr(trainer, "_load_raster", counting_load)
    pairs2 = pd.DataFrame([
        {"date": "20150601", "grid_row": 4, "grid_col": 4, "spc_size_in": 1.5, "mesh75_mm": 60.0},
        {"date": "20160601", "grid_row": 3, "grid_col": 3, "spc_size_in": 1.5, "mesh75_mm": 60.0},
    ])
    write_mesh_tif(mesh_dir / "2016" / "mesh_20160601.tif", 60.0, nrows=8, ncols=8)
    trainer.build_training_sets(pairs2, max_neg_per_day=0, rng=np.random.default_rng(0), gridrad_only=False)
    assert "20160601" in loads


def test_stage11b_wrong_dem_shape(tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_stage("11b_prepare_topography.py")
    elev = tmp_path / "elevation_0.05deg.tif"
    with rasterio.open(
        elev,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-125, 50, 0.05, 0.05),
    ) as dst:
        dst.write(np.full((2, 2), 100.0, dtype=np.float32), 1)
    monkeypatch.setattr(s, "NROWS", 3)
    monkeypatch.setattr(s, "NCOLS", 3)
    monkeypatch.setattr(s, "ELEVATION_TIF", elev)
    assert s.validate_outputs() is False


# ---------------------------------------------------------------------------
# Final 25-line push
# ---------------------------------------------------------------------------


def test_stage09_final_mrl_and_fit_branches(load_script, tmp_path, monkeypatch):
    from unittest.mock import patch

    s = load_script("09_fit_cdf_regional.py")
    monkeypatch.setattr(s, "NROWS", 6)
    monkeypatch.setattr(s, "NCOLS", 6)
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "THRESHOLD_DIAGNOSTICS", [])

    x = np.linspace(55, 130, 40, dtype=np.float64)
    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 10_000)
    assert s.compute_mrl_and_threshold(x, 0) == s.DEFAULT_GPD_THRESHOLD_MM

    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 5)
    monkeypatch.setattr(s, "THRESHOLD_DIAGNOSTICS", [])
    with patch("matplotlib.pyplot.savefig", side_effect=OSError("no plot")):
        s.compute_mrl_and_threshold(x, 1)

    annual_max = np.zeros((10, 4, 4), dtype=np.float32)
    annual_max[0:2, 0, 0] = [50.0, 55.0]
    annual_max[:, 0, 1] = np.linspace(45, 85, 10)
    region_map = np.full((4, 4), -1, dtype=np.int8)
    region_map[0, 0] = 0
    region_map[0, 1] = 0
    monkeypatch.setattr(s, "MIN_YEARS_FOR_FIT", 5)
    monkeypatch.setattr(s, "compute_mrl_and_threshold", lambda _x, _r: 44.0)
    monkeypatch.setattr(s, "lmom_fit_gpd", lambda _x: (1.5, 1.0))
    monkeypatch.setattr(s, "lmom_fit_lognormal", lambda nz: (np.log(40.0), 0.2))
    s.fit_regional_gpd(annual_max, region_map, 1)

    monkeypatch.setattr(s, "lmom_fit_gpd", lambda _x: (1.2, 1.0))
    s.fit_regional_gpd(annual_max, region_map, 1)


def test_stage04a_cost_limit_and_surface_licence(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)
    monkeypatch.setattr(s, "CLIM_YEARS", ["1992"])
    yearly = tmp_path / "pressure_chunks" / "era5_monthly_temp_plevels_conus_1992.nc"
    yearly.parent.mkdir(parents=True, exist_ok=True)
    yearly.write_bytes(b"partial")

    class CostLimitClient:
        def retrieve(self, dataset, request, path):
            if len(request["month"]) > 1:
                raise Exception("cost limits exceeded")
            from tests.test_04a_download_era5_coverage import _pressure_chunk

            _pressure_chunk(Path(path), int(request["year"][0]))

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": CostLimitClient})
    s.download_era5_temperature()

    class LicenceClient:
        def retrieve(self, dataset, request, path):
            raise Exception("403 required licences not accepted for this dataset")

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": LicenceClient})
    sfc = tmp_path / "era5_surface_geopotential_conus.nc"
    if sfc.exists():
        sfc.unlink()
    with pytest.raises(RuntimeError, match="licence"):
        s.download_era5_surface_geopotential()

    lats = np.array([40.0], dtype=np.float32)
    lons = np.array([-100.0], dtype=np.float32)
    temp_monthly = np.zeros((12, 3, 1, 1), dtype=np.float32)
    heights_monthly = np.zeros((12, 3, 1, 1), dtype=np.float32)
    temp_monthly[5, :, 0, 0] = np.array([248.0, 252.0, 256.0], dtype=np.float32)
    heights_monthly[5, :, 0, 0] = np.array([9000.0, 7500.0, 6000.0], dtype=np.float32)
    counts = np.ones(12, dtype=np.int32)
    monkeypatch.setattr(
        s,
        "_load_pressure_climatology",
        lambda _files: (temp_monthly, heights_monthly, lats, lons, counts),
    )
    import xarray as xr

    sfc_path = tmp_path / "sfc2.nc"
    xr.Dataset({"z": (("latitude", "longitude"), np.array([[0.0]], dtype=np.float32))}).to_netcdf(sfc_path)
    monkeypatch.setattr(s, "OUT_FILE", tmp_path / "iso2.nc")
    s.compute_isotherm_heights([tmp_path / "fresh.nc"], sfc_path)


def test_stage05_cross_cal_read_errors(load_script, tmp_path, monkeypatch):
    from tests.test_05_apply_mesh_bias_correction import _write_mesh

    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)
    monkeypatch.setattr(s, "CAL_DIR", tmp_path / "cal")
    monkeypatch.setattr(s, "NROWS", 2)
    monkeypatch.setattr(s, "NCOLS", 2)
    monkeypatch.setattr(s, "load_gridrad_days", lambda: {"20120601"})
    ydir = in_dir / "2012"
    ydir.mkdir()
    _write_mesh(ydir / "mesh_20120601.tif", np.full((2, 2), 45.0, dtype=np.float32))
    (ydir / "mesh_bad.tif").write_bytes(b"bad")
    _write_mesh(ydir / "mesh_empty.tif", np.zeros((2, 2), dtype=np.float32))
    s.build_cross_calibration()


def test_stage04b_unknown_dsid_and_adaptive_fill(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)

    with pytest.raises(ValueError, match="Unknown dsid"):
        s.list_day_catalog_files(types.SimpleNamespace(), "bogus", day, timeout=(1.0, 1.0))

    item = s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename="f.nc",
        url="http://example.com/f.nc",
        out_path=tmp_path / "f.nc",
    )
    item.out_path.with_suffix(item.out_path.suffix + ".tmp").write_bytes(b"x")

    class Resp404:
        status_code = 404

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=0):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    s._download_one(
        types.SimpleNamespace(get=lambda *a, **k: Resp404()),
        item,
        connect_timeout=1.0,
        read_timeout=1.0,
    )

    monkeypatch.setattr(s, "severe_catalog_has_convective_data", lambda *_a, **_k: True)
    monkeypatch.setattr(s, "_severe_staging_covers_day", lambda _d: False)
    calls = {"n": 0}

    def count_dl(*_a, **k):
        calls["n"] += 1
        return {"downloaded": 1}

    monkeypatch.setattr(s, "download_for_day", count_dl)
    out = s.download_for_day_adaptive(
        types.SimpleNamespace(),
        day,
        catalog_timeout=(1.0, 1.0),
        connect_timeout=1.0,
        read_timeout=1.0,
        max_workers=1,
    )
    assert out["source_mode"] == "severe+hourly-fill"
    assert calls["n"] == 2


def test_stage08_overlap_and_validate_mismatch(load_script, tmp_path, monkeypatch):
    s = load_script("08_build_event_catalog.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()

    r1 = np.array([0, 1, 2], dtype=np.int16)
    c1 = np.array([0, 1, 0], dtype=np.int16)
    r2 = np.array([0, 2], dtype=np.int16)
    c2 = np.array([2, 0], dtype=np.int16)
    assert s.footprints_overlap_sparse(r1, c1, r2, c2, buffer=1) is True

    (tmp_path / "out" / "event_catalog.csv").write_text("event_id\n1\n1\n2\n")
    np.savez(tmp_path / "out" / "event_peaks.npz", n_events=np.array([1, 2, 3]))
    assert s.validate_outputs() is False


def test_stage13_validate_and_streamed_log(load_script, tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from tests.test_13_generate_stochastic_catalog import _stage13_paths

    s = load_script("13_generate_stochastic_catalog.py")
    _event_dir, _out, cat_dir, map_dir, pet_dir, _mask = _stage13_paths(monkeypatch, s, tmp_path)
    monkeypatch.setattr(s, "RP_YEARS", [10])

    manifest = cat_dir / "stochastic_catalog_manifest.json"
    manifest.write_text(
        f'{{"n_years": {s.N_SIM_YEARS}, "status": "complete", '
        f'"seed": {s.RNG_SEED}, "model_version": "{s.MODEL_VERSION}"}}'
    )
    cols = {
        "sim_year": pa.array([0], type=pa.int32()),
        "event_idx": pa.array([0], type=pa.int32()),
        "template_id": pa.array([1], type=pa.int32()),
        "doy": pa.array([150], type=pa.int32()),
        "scale_factor": pa.array([1.0], type=pa.float32()),
        "peak_hail_mm": pa.array([40.0], type=pa.float32()),
        "n_cells": pa.array([1], type=pa.int32()),
    }
    pq.write_table(pa.table(cols), cat_dir / "stochastic_event_summary.parquet")
    (map_dir / "rp_00010yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()

    pq.write_table(
        pa.table({
            "sim_year": pa.array([-1, 999999], type=pa.int32()),
            "event_idx": pa.array([0, 1], type=pa.int32()),
            "template_id": pa.array([1, 1], type=pa.int32()),
            "doy": pa.array([150, 151], type=pa.int32()),
            "scale_factor": pa.array([1.0, 1.0], type=pa.float32()),
            "peak_hail_mm": pa.array([40.0, 41.0], type=pa.float32()),
            "n_cells": pa.array([1, 1], type=pa.int32()),
        }),
        cat_dir / "stochastic_event_summary.parquet",
    )
    assert s.validate_outputs() is False

    class EmptySimYearPF:
        def __init__(self, path):
            self._real = pq.ParquetFile(path)

        @property
        def metadata(self):
            return self._real.metadata

        @property
        def schema_arrow(self):
            return self._real.schema_arrow

        def read(self, columns=None):
            if columns == ["sim_year"]:
                return pa.table({"sim_year": pa.array([], type=pa.int32())})
            return self._real.read(columns=columns)

    monkeypatch.setattr(pq, "ParquetFile", EmptySimYearPF)
    assert s.validate_outputs() is False

    stream_path = cat_dir / "stochastic_event_summary.parquet"
    if stream_path.exists():
        stream_path.unlink()

    def fake_sim(*_a, **kwargs):
        cp = kwargs.get("catalog_path")
        if cp is not None:
            pq.write_table(pa.table(cols), cp)
        mmap_path = tmp_path / "_work" / "_ann.mmap"
        mmap_path.parent.mkdir(parents=True, exist_ok=True)
        mmap_path.write_bytes(b"\x00" * 64)
        return (
            np.zeros((2, 1), dtype=np.float32),
            np.array([1], dtype=np.int32),
            np.array([1], dtype=np.int32),
            np.array([40.0], dtype=np.float32),
            np.array([1], dtype=np.int32),
            np.array([1], dtype=np.int32),
            np.array([1], dtype=np.int32),
            pd.DataFrame(),
            mmap_path,
        )

    monkeypatch.setattr(s, "simulate_catalog", fake_sim)
    monkeypatch.setattr(s, "write_geotiff", lambda arr, path, **_kw: Path(path).write_bytes(b"tif"))
    monkeypatch.setattr(s, "load_historical_events", lambda: (pd.DataFrame(), {}))
    monkeypatch.setattr(s, "calibrate_sigma", lambda *_a, **_k: 0.2)
    monkeypatch.setattr(s, "build_doy_distribution", lambda *_a, **_k: np.ones(366) / 366)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["13_generate_stochastic_catalog.py", "--n-years", "1000"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


def test_train_pos_cache_line_133(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    mesh_dir = tmp_path / "corrected"
    write_mesh_tif(mesh_dir / "2016" / "mesh_20160601.tif", 60.0, nrows=8, ncols=8)
    nrows, ncols = 8, 8
    monkeypatch.setattr(trainer, "CORRECTED_DIR", mesh_dir)
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(trainer, "ensure_range_km_grid", lambda: np.full((nrows, ncols), 50.0, dtype=np.float32))
    monkeypatch.setattr(trainer, "ensure_nearest_site_index_grid", lambda: np.zeros((nrows, ncols), dtype=np.int16))
    monkeypatch.setattr(trainer, "azimuth_to_nearest_site_deg", lambda: np.zeros((nrows, ncols), dtype=np.float32))

    pairs = pd.DataFrame([
        {"date": "20150601", "grid_row": 1, "grid_col": 1, "spc_size_in": 0.5, "mesh75_mm": 0.0},
        {"date": "20160601", "grid_row": 4, "grid_col": 4, "spc_size_in": 1.5, "mesh75_mm": 60.0},
    ])
    X, y, _ = trainer.build_training_sets(
        pairs, max_neg_per_day=0, rng=np.random.default_rng(0), gridrad_only=False,
    )
    assert len(X) >= 1


def test_radar_geometry_quiet_active_guard(monkeypatch):
    import scripts._radar_geometry as rg
    from scripts._radar_geometry import remove_persistent_range_artifacts

    monkeypatch.setattr(rg, "NROWS", 8)
    monkeypatch.setattr(rg, "NCOLS", 8)
    quiet = np.full((8, 8), 1.0, dtype=np.float32)
    site = np.zeros((8, 8), dtype=np.int16)
    rng = np.full((8, 8), 50.0, dtype=np.float32)
    out, n = remove_persistent_range_artifacts(
        quiet, site, rng, history=np.full((6, 8, 8), 10.0), min_history_days=3, active_mm=5.0,
    )
    assert n == 0


def test_final_six_lines(load_script, tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Stage 08: invalid date in filename (102-103)
    import rasterio
    from rasterio.transform import from_origin

    s08 = load_script("08_build_event_catalog.py")
    in_dir = tmp_path / "in08"
    in_dir.mkdir()
    monkeypatch.setattr(s08, "IN_DIR", in_dir)
    bad = in_dir / "mesh_notadate.tif"
    bad.write_bytes(b"x")
    good = in_dir / "2015" / "mesh_20150601.tif"
    good.parent.mkdir(parents=True)
    with rasterio.open(
        good, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(-100, 40, 0.05, 0.05),
    ) as dst:
        dst.write(np.array([[0, 30, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=np.float32), 1)
    dates, _ = s08.load_daily_data()
    assert len(dates) == 1

    # Stage 04b: _catalog_get HTTPError on final retry (318)
    s04b = load_script("04b_download_gridrad.py")
    monkeypatch.setattr(s04b, "time", type("T", (), {"sleep": lambda *_a, **_k: None})())

    class Resp429:
        status_code = 429

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

    class Sess429:
        def __init__(self):
            self.n = 0

        def get(self, url, timeout=60, stream=False):
            self.n += 1
            return Resp429()

    monkeypatch.setattr(s04b, "_retryable_http_error", lambda _e: True)
    with pytest.raises(requests.HTTPError):
        s04b._catalog_get(Sess429(), "http://x", timeout=(1.0, 1.0))

    # Stage 04a: cost-limit raise on non-cost error (172) + surface licence (213)
    s04a = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s04a, "ERA5_DIR", tmp_path / "era5")
    monkeypatch.setattr(s04a, "CLIM_YEARS", ["1993"])

    class BoomClient:
        def retrieve(self, dataset, request, path):
            raise RuntimeError("unexpected CDS failure")

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": BoomClient})
    with pytest.raises(RuntimeError, match="unexpected"):
        s04a.download_era5_temperature()

    class LicenceOnlyClient:
        def retrieve(self, dataset, request, path):
            raise Exception("403 required licences not accepted")

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": LicenceOnlyClient})
    sfc = tmp_path / "era5" / "era5_surface_geopotential_conus.nc"
    sfc.parent.mkdir(parents=True, exist_ok=True)
    if sfc.exists():
        sfc.unlink()
    with pytest.raises(RuntimeError, match="licence"):
        s04a.download_era5_surface_geopotential()

    # Stage 13: empty sim_year column read (552)
    from tests.test_13_generate_stochastic_catalog import _stage13_paths

    s13 = load_script("13_generate_stochastic_catalog.py")
    _event_dir, _out, cat_dir, map_dir, pet_dir, _mask = _stage13_paths(monkeypatch, s13, tmp_path / "s13")
    monkeypatch.setattr(s13, "RP_YEARS", [10])
    manifest = cat_dir / "stochastic_catalog_manifest.json"
    manifest.write_text(
        f'{{"n_years": {s13.N_SIM_YEARS}, "status": "complete", '
        f'"seed": {s13.RNG_SEED}, "model_version": "{s13.MODEL_VERSION}"}}'
    )
    pq.write_table(
        pa.table({
            "sim_year": pa.array([0], type=pa.int32()),
            "event_idx": pa.array([0], type=pa.int32()),
            "template_id": pa.array([1], type=pa.int32()),
            "doy": pa.array([150], type=pa.int32()),
            "scale_factor": pa.array([1.0], type=pa.float32()),
            "peak_hail_mm": pa.array([40.0], type=pa.float32()),
            "n_cells": pa.array([1], type=pa.int32()),
        }),
        cat_dir / "stochastic_event_summary.parquet",
    )
    (map_dir / "rp_00010yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()

    class EmptyYearsPF:
        def __init__(self, path):
            self._real = pq.ParquetFile(path)

        @property
        def metadata(self):
            return self._real.metadata

        @property
        def schema_arrow(self):
            return self._real.schema_arrow

        def read(self, columns=None):
            if columns == ["sim_year"]:
                return pa.table({"sim_year": pa.array([], type=pa.int32())})
            return self._real.read(columns=columns)

    monkeypatch.setattr(pq, "ParquetFile", EmptyYearsPF)
    assert s13.validate_outputs() is False
