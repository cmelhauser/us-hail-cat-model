"""Additional Stage 04a/04b/04c coverage for remaining branches."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest
import requests
import xarray as xr

from scripts._config import NCOLS, NROWS
from scripts._io import write_geotiff
from tests.test_04a_download_era5_coverage import _pressure_chunk
from tests.test_04b_download_gridrad_coverage import _download_item
from tests.test_04c_fill_gridrad_gap_coverage import _inline_process_pool, _write_era5_isotherms, _write_gridrad_nc


def test_stage04a_cost_limit_fallback_and_licence(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)
    monkeypatch.setattr(s, "CLIM_YEARS", ["1991"])
    chunk = tmp_path / "chunks" / "era5_monthly_temp_plevels_conus_1991.nc"
    chunk.parent.mkdir(parents=True)

    class CostClient:
        calls = 0

        def retrieve(self, dataset, request, path):
            self.calls += 1
            if len(request["month"]) > 1:
                raise Exception("cost limits exceeded")
            _pressure_chunk(Path(path), int(request["year"][0]))

    import sys
    client = CostClient()
    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": lambda: client})
    files = s.download_era5_temperature()
    assert len(files) == 12

    class LicClient:
        def retrieve(self, dataset, request, path):
            raise Exception("licence not accepted")

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": LicClient})
    with pytest.raises(RuntimeError, match="licence"):
        s.download_era5_surface_geopotential()


def test_stage04a_time_dim_missing(load_script):
    s = load_script("04a_download_era5_isotherms.py")

    class DS:
        dims = {}
        coords = {}

    with pytest.raises(KeyError):
        s._time_dim_name(DS())


def test_stage04b_catalog_retry_and_download_retries(load_script, monkeypatch, tmp_path):
    s = load_script("04b_download_gridrad.py")
    monkeypatch.setattr(s, "time", type("T", (), {"sleep": lambda *_a, **_k: None})())

    calls = {"n": 0}

    class Resp503:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

    class Sess:
        def get(self, url, timeout=60, stream=False):
            calls["n"] += 1
            if calls["n"] < 2:
                raise requests.HTTPError(response=Resp503())
            r = Resp503()
            r.status_code = 200
            r.text = "<?xml version='1.0'?><catalog xmlns='http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0'/>"
            r.raise_for_status = lambda: None
            return r

    out = s._catalog_get(Sess(), "http://x", timeout=(1.0, 1.0))
    assert out.status_code == 200

    day = date(2015, 5, 1)
    item = _download_item(s, tmp_path, day)
    attempts = {"n": 0}

    class RespRetry:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

        def iter_content(self, chunk_size=0):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class SessDl:
        def get(self, url, params=None, stream=True, timeout=None):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise requests.ConnectionError("reset")
            r = RespRetry()
            r.status_code = 200
            r.raise_for_status = lambda: None
            r.iter_content = lambda chunk_size=0: [b"data"]
            return r

    _, status = s._download_one(SessDl(), item, connect_timeout=1.0, read_timeout=1.0)
    assert status == "downloaded"


def test_stage04b_adaptive_severe_and_fill(load_script, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)

    class Sess:
        def close(self):
            return None

    monkeypatch.setattr(s, "_severe_staging_covers_day", lambda _d: False)
    monkeypatch.setattr(s, "severe_catalog_has_convective_data", lambda *_a, **_k: True)
    monkeypatch.setattr(s, "download_for_day", lambda *_a, **_k: {"downloaded": 1, "skipped": 0, "missing": 0, "errors": 0})
    monkeypatch.setattr(s, "_severe_staging_covers_day", lambda _d: False)

    stats = s.download_for_day_adaptive(
        Sess(), day, catalog_timeout=(1.0, 1.0), connect_timeout=1.0, read_timeout=1.0, max_workers=1,
    )
    assert stats["source_mode"] == "severe+hourly-fill"


def test_stage04c_process_day_partial_errors_and_native_qc(
    load_script, tmp_path, monkeypatch,
):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(s, "get_freezing_levels_era5", lambda *_a, **_k: (2.0, 5.0))

    day = date(2015, 5, 25)
    good = tmp_path / "good.nc"
    bad = tmp_path / "bad.nc"
    _write_gridrad_nc(good)
    bad.write_bytes(b"x")

    monkeypatch.setattr(s, "find_gridrad_files", lambda _d: ([good, bad], "gridrad-hourly-v31"))
    monkeypatch.setattr(
        s,
        "temporal_coverage_summary",
        lambda *_a, **_k: {
            "source_first_utc": "2015-05-25T12:00:00+00:00",
            "source_last_utc": "2015-05-25T13:00:00+00:00",
            "source_max_gap_minutes": 60.0,
            "temporal_coverage_status": "complete",
        },
    )
    result = s.process_day(day, native_qc=True)
    assert result.get("errors", 0) >= 1
    assert (tmp_path / "2015" / "mesh_20150525.tif").exists()


def test_stage04c_process_day_skipped_and_no_data(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    day = date(2015, 5, 26)
    tif = tmp_path / "2015" / "mesh_20150526.tif"
    tif.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), tif)
    monkeypatch.setattr(s, "find_gridrad_files", lambda _d: ([], "none"))
    monkeypatch.setattr(
        s,
        "temporal_coverage_summary",
        lambda *_a, **_k: {"temporal_coverage_status": "missing"},
    )
    skipped = s.process_day(day)
    assert skipped["skipped"] is True

    tif.unlink()
    no_data = s.process_day(day)
    assert no_data.get("no_data") is True


def test_stage04c_rebuild_manifest_pending_inputs(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    day = date(2015, 5, 27)
    nc = tmp_path / "staged.nc"
    _write_gridrad_nc(nc)
    monkeypatch.setattr(s, "find_gridrad_files", lambda _d: ([nc], "gridrad-hourly-v31"))
    monkeypatch.setattr(
        s,
        "temporal_coverage_summary",
        lambda *_a, **_k: {"temporal_coverage_status": "partial"},
    )
    n = s.rebuild_manifest_from_outputs(day, day)
    assert n == 0


def test_stage04c_validate_fail_and_peak_from_raster(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    bad = tmp_path / "2015" / "mesh_20150528.tif"
    bad.parent.mkdir(parents=True)
    arr = np.zeros((NROWS, NCOLS), dtype=np.float32)
    arr[0, 0] = 999.0
    write_geotiff(arr, bad)

    def fake_rglob(self, pattern):
        if pattern == "mesh_????????.tif":
            return iter([bad] * 2001)
        return Path.rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    with pytest.raises(SystemExit) as exc:
        s.main(["--validate"])
    assert exc.value.code == 1

    good = tmp_path / "2015" / "mesh_20150529.tif"
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good, tags={})
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 29)],
    )
    monkeypatch.setattr(s, "delete_gridrad_inputs_for_day", lambda *_a, **_k: None)
    monkeypatch.setattr(s, "merge_gridrad_days_labels", lambda *_a, **_k: 1)
    monkeypatch.setattr(s, "rebuild_gridrad_days_from_geotiffs", lambda *_a, **_k: [])
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)

    def proc(_d, native_qc=None):
        out = tmp_path / "2015" / "mesh_20150529.tif"
        write_geotiff(np.full((NROWS, NCOLS), 0.0, dtype=np.float32), out)
        out_arr = np.zeros((NROWS, NCOLS), dtype=np.float32)
        out_arr[5, 5] = 40.0
        write_geotiff(out_arr, out)
        return {
            "files": 1,
            "source": "gridrad-hourly-v31",
            "peak_mesh75_mm": 40.0,
            "active_cells": 1,
        }

    monkeypatch.setattr(s, "process_day", proc)
    s.main(["--year", "2015", "--month", "5", "--workers", "1"])


def _write_gridrad_nc_dense(
    path: Path,
    *,
    lat: float = 35.0,
    lon: float = -97.0,
    z_dbz: float = 50.0,
) -> None:
    import netCDF4 as nc

    lats = np.array([lat], dtype=np.float32)
    lons = np.array([lon], dtype=np.float32)
    alts = np.array([2.0, 4.0, 6.0], dtype=np.float32)
    na, nl, nlon = len(alts), len(lats), len(lons)
    refl = np.full((na, nl, nlon), z_dbz, dtype=np.float32)
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("alt", na)
        ds.createDimension("lat", nl)
        ds.createDimension("lon", nlon)
        ds.createVariable("Latitude", "f4", ("lat",))[:] = lats
        ds.createVariable("Longitude", "f4", ("lon",))[:] = lons
        ds.createVariable("Altitude", "f4", ("alt",))[:] = alts
        ds.createVariable("Reflectivity", "f4", ("alt", "lat", "lon"))[:] = refl


def test_stage04c_process_gridrad_file_dense_and_early_returns(load_script, tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    s = load_script("04c_fill_gridrad_gap.py")
    daily = np.zeros((NROWS, NCOLS), dtype=np.float32)
    monkeypatch.setattr(s, "get_freezing_levels_era5", lambda *_a, **_k: (2.0, 5.0))

    good = tmp_path / "dense.nc"
    _write_gridrad_nc_dense(good)
    assert s.process_gridrad_file(good, daily, 5, native_qc=False) == 1
    assert daily.max() > 0

    def _mock_ds(var_names):
        ds = MagicMock()
        ds.variables = {name: MagicMock() for name in var_names}
        for name in var_names:
            ds.variables[name].__getitem__ = MagicMock(return_value=np.array([1.0]))
        return ds

    monkeypatch.setattr(
        "netCDF4.Dataset",
        lambda *_a, **_k: _mock_ds(["Latitude"]),
    )
    assert s.process_gridrad_file(tmp_path / "x.nc", daily, 5, native_qc=False) == 0

    monkeypatch.setattr(
        "netCDF4.Dataset",
        lambda *_a, **_k: _mock_ds(["Latitude", "Longitude"]),
    )
    assert s.process_gridrad_file(tmp_path / "y.nc", daily, 5, native_qc=False) == 0

    monkeypatch.setattr(
        "netCDF4.Dataset",
        lambda *_a, **_k: _mock_ds(["Latitude", "Longitude", "Altitude"]),
    )
    monkeypatch.setattr(s, "_load_reflectivity_3d", lambda _ds: None)
    assert s.process_gridrad_file(tmp_path / "z.nc", daily, 5, native_qc=False) == 0

    oob = tmp_path / "oob.nc"
    _write_gridrad_nc_dense(oob, lat=10.0, lon=-50.0)
    assert s.process_gridrad_file(oob, daily, 5, native_qc=False) == 0

    lon_wrap = tmp_path / "wrap.nc"
    _write_gridrad_nc_dense(lon_wrap, lon=200.0)
    assert s.process_gridrad_file(lon_wrap, daily, 5, native_qc=False) >= 0


def test_stage04c_compute_shi_climo_and_hourly_helpers(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    assert s.compute_shi_column(np.array([30.0]), np.array([3.0, 4.0]), 2.0, 5.0) == 0.0
    assert s._get_freezing_levels_climo(60.0, 6) == (3.5, 6.0)

    day = date(2015, 5, 20)
    assert s._hourly_fill_for_severe_gaps([], [], day) == []
    assert s._hourly_source_label([]) == "gridrad-hourly"
    assert s._hourly_source_label([Path("nexrad_3d_v4_2_x.nc")]) == "gridrad-hourly-v42"
    assert s._hourly_source_label([Path("nexrad_3d_v3_1_x.nc")]) == "gridrad-hourly-v31"

    sev_dir = tmp_path / "sev"
    hr_dir = tmp_path / "hr"
    monkeypatch.setattr(s, "GRIDRAD_SEV", sev_dir)
    monkeypatch.setattr(s, "GRIDRAD_DIR", hr_dir)
    ymd = day.strftime("%Y%m%d")
    sev_stage = sev_dir / "by_convective_day" / ymd
    hr_stage = hr_dir / "by_convective_day" / ymd
    sev_stage.mkdir(parents=True)
    hr_stage.mkdir(parents=True)
    (sev_stage / f"nexrad_3d_v4_2_{ymd}T120000Z.nc").write_bytes(b"x")
    (hr_stage / f"nexrad_3d_v3_1_{ymd}T130000Z.nc").write_bytes(b"x")
    files, src = s.find_gridrad_files(day)
    assert src.startswith("gridrad")

    empty_files, empty_src = s.find_gridrad_files(date(2015, 1, 1))
    monkeypatch.setattr(s, "staged_nc_files_for_convective_day", lambda *_a, **_k: [])
    empty_files, empty_src = s.find_gridrad_files(date(2015, 1, 2))
    assert empty_src == "none"
    cov = s.temporal_coverage_summary([], "none", day)
    assert cov["temporal_coverage_status"] == "missing"


def test_stage04c_indexed_3d_and_merge_labels(load_script, tmp_path):
    s = load_script("04c_fill_gridrad_gap.py")

    class DS:
        variables = {
            "Reflectivity": np.array([55.0, 60.0], dtype=np.float32),
            "index": np.array([0, 1], dtype=np.int64),
            "Altitude": np.array([2.0, 4.0], dtype=np.float32),
            "Latitude": np.array([35.0], dtype=np.float32),
            "Longitude": np.array([-97.0], dtype=np.float32),
        }

    assert s._load_indexed_3d(DS(), "missing") is None
    bad = type("B", (), {"variables": {"Reflectivity": np.array([1.0, 2.0])}})()
    assert s._load_indexed_3d(bad, "Reflectivity") is None
    assert s._load_indexed_3d(DS(), "Reflectivity") is not None

    labels_file = tmp_path / "gridrad_days.txt"
    labels_file.write_text("20150101\n", encoding="utf-8")
    n = s.merge_gridrad_days_labels(labels_file, ["20150201", "20150101"])
    assert n == 2
    assert "20150201" in labels_file.read_text(encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    tif = out_dir / "2015" / "mesh_20150501.tif"
    tif.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), tif)
    discovered = s.rebuild_gridrad_days_from_geotiffs(out_dir, date(2015, 5, 1), date(2015, 5, 2))
    assert "20150501" in discovered


def test_stage04c_main_extended_branches(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "GRIDRAD_DIR", tmp_path / "gridrad")
    monkeypatch.setattr(s, "GRIDRAD_SEV", tmp_path / "gridrad_severe")
    era5 = tmp_path / "era5.nc"
    _write_era5_isotherms(era5)
    monkeypatch.setattr(s, "ERA5_FILE", era5)
    monkeypatch.setattr(s, "rebuild_manifest_from_outputs", lambda *_a, **_k: 1)
    monkeypatch.setattr(s, "rebuild_gridrad_days_from_geotiffs", lambda *_a, **_k: [])
    monkeypatch.setattr(s, "delete_gridrad_inputs_for_day", lambda *_a, **_k: None)
    monkeypatch.setattr(s, "merge_gridrad_days_labels", lambda *_a, **_k: 1)
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    s._era5_h0c = np.ones((12, 1, 1))

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--year", "2015"])
    assert exc.value.code == 0

    def fake_rglob(self, pattern):
        if pattern == "mesh_????????.tif":
            return iter([])
        return Path.rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    with pytest.raises(SystemExit) as exc:
        s.main(["--validate"])
    assert exc.value.code == 1

    def check_src(day):
        sources = [
            "gridrad-severe-5min",
            "gridrad-hourly-v31",
            "gridrad-hourly-v42",
            "gridrad-hourly-mixed",
            "gridrad-severe-partial",
            "none",
        ]
        idx = day.day % len(sources)
        return [], sources[idx]

    monkeypatch.setattr(s, "find_gridrad_files", check_src)
    with pytest.raises(SystemExit) as exc:
        s.main(["--check-data", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    _inline_process_pool(monkeypatch, s)
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 10), date(2015, 5, 11)],
    )
    monkeypatch.setattr(
        s,
        "_process_day_worker",
        lambda day: (
            day.strftime("%Y%m%d"),
            {"files": 1, "source": "gridrad-severe-5min", "peak_mesh75_mm": 55.0, "active_cells": 3},
        ),
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "2"])

    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 12)],
    )
    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: {"skipped": True},
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "1"])

    class Fake04b:
        @staticmethod
        def _request_session():
            class S:
                def close(self):
                    return None

            return S()

        @staticmethod
        def download_for_day_adaptive(*_a, **_k):
            return {"downloaded": 1}

    monkeypatch.setattr(s, "_load_04b_module", lambda: Fake04b())
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 13)],
    )
    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: {"files": 1, "source": "gridrad-hourly-v31", "peak_mesh75_mm": 30.0, "active_cells": 2},
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "1", "--with-04b-download"])

    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 14)],
    )
    with pytest.raises(RuntimeError, match="failed convective day"):
        s.main(["--year", "2015", "--month", "5", "--workers", "1"])


def test_stage04c_run_one_day_and_worker_errors(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    day = date(2015, 5, 15)

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("fail")))
    ymd, res = s._process_day_worker(day)
    assert res["error"] == "fail"

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"files": 1})
    monkeypatch.setattr(s, "_worker_04b_mod", None)
    monkeypatch.setattr(s, "_load_04b_module", lambda: (_ for _ in ()).throw(RuntimeError("no04b")))
    ymd2, res2 = s._run_one_day_download_then_process((day, True, 1))
    assert "error" in res2


def test_stage04b_catalog_planning_and_adaptive(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2018, 6, 1)
    assert s._v42_hourly_eligible(day) is True
    assert s.DS_HOURLY_V42 in s._hourly_dataset_ids(day)

    ns = {"t": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"}
    ymd = day.strftime("%Y%m%d")
    hourly_xml = f"""<?xml version='1.0'?>
    <catalog xmlns='http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0'>
      <dataset name='nexrad_3d_v3_1_{ymd}T120000Z.nc'/>
    </catalog>"""
    severe_year_xml = f"""<?xml version='1.0'?>
    <catalog xmlns='http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0'>
      <catalogRef xlink:title='{ymd}' xlink:href='{ymd}/catalog.xml' xmlns:xlink='http://www.w3.org/1999/xlink'/>
    </catalog>"""
    severe_day_xml = f"""<?xml version='1.0'?>
    <catalog xmlns='http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0'>
      <dataset name='nexrad_3d_v4_2_{ymd}T120000Z.nc'/>
    </catalog>"""

    class Resp:
        def __init__(self, status, text):
            self.status_code = status
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

    class Sess:
        def get(self, url, timeout=60, stream=False):
            if "404" in url:
                return Resp(404, "")
            if f"{day.year}/catalog.xml" in url and ymd not in url.split("/")[-1]:
                return Resp(200, severe_year_xml)
            if ymd in url and "catalog.xml" in url:
                return Resp(200, severe_day_xml)
            return Resp(200, hourly_xml)

    monkeypatch.setattr(s, "_catalog_get", lambda sess, url, timeout: Sess().get(url))
    hourly = s.list_day_catalog_files(Sess(), s.DS_HOURLY, day, timeout=(1.0, 1.0))
    assert hourly
    assert s.list_day_catalog_files(Sess(), s.DS_HOURLY, date(2018, 1, 1), timeout=(1.0, 1.0)) == []
    severe = s.list_day_catalog_files(Sess(), s.DS_SEVERE, day, timeout=(1.0, 1.0))
    assert severe

    items = s.plan_downloads_for_day(
        Sess(), day, hourly=True, severe=True, catalog_timeout=(1.0, 1.0),
    )
    assert items

    class Sess2:
        def close(self):
            return None

    monkeypatch.setattr(s, "_severe_staging_covers_day", lambda _d: False)
    monkeypatch.setattr(s, "severe_catalog_has_convective_data", lambda *_a, **_k: False)
    monkeypatch.setattr(
        s,
        "download_for_day",
        lambda *_a, **_k: {"downloaded": 2, "skipped": 0, "missing": 0, "errors": 0},
    )
    stats = s.download_for_day_adaptive(
        Sess2(), day, catalog_timeout=(1.0, 1.0), connect_timeout=1.0, read_timeout=1.0, max_workers=1,
    )
    assert stats["source_mode"] == "hourly-only"


def test_stage04b_main_check_data_and_auth_log(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    day = date(2015, 5, 1)
    item = _download_item(s, tmp_path, day)
    item.out_path.write_bytes(b"x")

    class Sess:
        def close(self):
            return None

    monkeypatch.setattr(s, "_request_session", lambda: Sess())
    monkeypatch.setattr(s, "plan_downloads_for_day", lambda *_a, **_k: [item])
    monkeypatch.delenv("GDEX_TOKEN", raising=False)
    monkeypatch.delenv("GDEX_API_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc:
        s.main(["--check-data", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--plan-all-days-first", "--check-data", "--year", "2015"])
    assert exc.value.code == 0

    monkeypatch.setattr(s, "plan_downloads_for_day", lambda *_a, **_k: [])
    with pytest.raises(SystemExit) as exc:
        s.main(["--dry-run", "--year", "2015"])
    assert exc.value.code == 0
