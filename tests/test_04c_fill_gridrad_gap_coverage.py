"""Coverage tests for Stage 04c — GridRad processing, pool workers, main()."""

from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from scripts._config import NCOLS, NROWS
from scripts._io import write_geotiff


def _write_gridrad_nc(path: Path, *, lat=35.0, lon=-97.0, z_dbz=50.0) -> None:
    import netCDF4 as nc

    lats = np.array([lat], dtype=np.float32)
    lons = np.array([lon], dtype=np.float32)
    alts = np.array([2.0, 4.0, 6.0], dtype=np.float32)
    idx = np.array([0], dtype=np.int64)
    refl = np.array([z_dbz], dtype=np.float32)

    with nc.Dataset(path, "w") as ds:
        ds.createDimension("alt", len(alts))
        ds.createDimension("lat", len(lats))
        ds.createDimension("lon", len(lons))
        ds.createDimension("sparse", len(idx))
        ds.createVariable("Latitude", "f4", ("lat",))[:] = lats
        ds.createVariable("Longitude", "f4", ("lon",))[:] = lons
        ds.createVariable("Altitude", "f4", ("alt",))[:] = alts
        ds.createVariable("index", "i8", ("sparse",))[:] = idx
        ds.createVariable("Reflectivity", "f4", ("sparse",))[:] = refl


def _write_era5_isotherms(path: Path) -> None:
    xr.Dataset(
        {
            "h_0C_km": (["month", "latitude", "longitude"], np.full((12, 1, 1), 3.0)),
            "h_m20C_km": (["month", "latitude", "longitude"], np.full((12, 1, 1), 6.0)),
        },
        coords={"month": np.arange(1, 13), "latitude": [35.0], "longitude": [-97.0]},
    ).to_netcdf(path)


def test_stage04c_load_era5_and_freezing_levels(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    era5 = tmp_path / "era5.nc"
    _write_era5_isotherms(era5)
    monkeypatch.setattr(s, "ERA5_FILE", era5)
    s._era5_h0c = s._era5_hm20c = s._era5_lats = s._era5_lons = None
    s.load_era5_isotherms()
    assert s._era5_h0c is not None
    s.load_era5_isotherms()  # cached

    h0, hm20 = s.get_freezing_levels_era5(35.0, -97.0, 6)
    assert 0.5 < h0 < hm20

    s._era5_h0c = None
    h0c, hm20c = s.get_freezing_levels_era5(35.0, -97.0, 6)
    assert h0c > 0

    monkeypatch.setattr(s, "ERA5_FILE", tmp_path / "missing.nc")
    s._era5_h0c = None
    s.load_era5_isotherms()


def test_stage04c_indexed_3d_helpers(load_script):
    s = load_script("04c_fill_gridrad_gap.py")

    class DS:
        variables = {
            "dense": np.array([[[1.0]]], dtype=np.float32),
            "bad": np.array([1.0, 2.0], dtype=np.float32),
        }

    assert s._load_dense_3d(DS(), "missing") is None
    assert s._load_dense_3d(DS(), "bad") is None
    assert s._load_dense_3d(DS(), "dense").shape == (1, 1, 1)

    class DS2:
        variables = {
            "Reflectivity": np.array([55.0], dtype=np.float32),
            "index": np.array([0], dtype=np.int64),
            "Altitude": np.array([2.0, 4.0], dtype=np.float32),
            "Latitude": np.array([35.0], dtype=np.float32),
            "Longitude": np.array([-97.0], dtype=np.float32),
        }

    grid = s._load_indexed_3d(DS2(), "Reflectivity")
    assert grid is not None
    assert s._load_reflectivity_3d(DS2()) is not None


def test_stage04c_process_gridrad_file(tmp_path, load_script, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    nc = tmp_path / "g.nc"
    _write_gridrad_nc(nc)
    daily = np.zeros((NROWS, NCOLS), dtype=np.float32)
    monkeypatch.setattr(s, "get_freezing_levels_era5", lambda *_a, **_k: (2.0, 5.0))
    n = s.process_gridrad_file(nc, daily, 5, native_qc=False)
    assert n >= 0

    bad = tmp_path / "bad.nc"
    bad.write_bytes(b"not nc")
    with pytest.raises(OSError):
        s.process_gridrad_file(bad, daily, 5, native_qc=False)


def test_stage04c_process_day_success(tmp_path, load_script, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(s, "get_freezing_levels_era5", lambda *_a, **_k: (2.0, 5.0))

    day = date(2015, 5, 20)
    nc = tmp_path / "nexrad_3d_v3_1_20150520T120000Z.nc"
    _write_gridrad_nc(nc)

    monkeypatch.setattr(s, "find_gridrad_files", lambda _d: ([nc], "gridrad-hourly-v31"))
    monkeypatch.setattr(
        s,
        "temporal_coverage_summary",
        lambda *_a, **_k: {
            "source_first_utc": "2015-05-20T12:00:00+00:00",
            "source_last_utc": "2015-05-20T13:00:00+00:00",
            "source_max_gap_minutes": 60.0,
            "temporal_coverage_status": "complete",
        },
    )

    result = s.process_day(day, native_qc=False)
    assert "peak_mesh75_mm" in result or result.get("no_data") or result.get("skipped")


def test_stage04c_manifest_helpers(tmp_path, load_script, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    day = date(2015, 5, 21)
    out = tmp_path / "mesh_20150521.tif"
    out.write_bytes(b"x")

    plain, gz = s.summarize_gridrad_formats([Path("a.nc"), Path("b.nc.gz")])
    assert plain == 1 and gz == 1

    row = s.manifest_row_for_day(
        day, out, [], source_pixels=0, active_cells=0, max_mesh_mm=0.0,
        skipped=True, prior_row={"status": "ok", "source_files": 3},
    )
    assert row["source_files"] == 3

    assert s._prior_manifest_row(day) is None
    s.upsert_manifest_row(row)
    assert s._prior_manifest_row(day) is not None

    preserved = s._preserve_provenance_fields({"status": "new"}, None)
    assert preserved["temporal_coverage_status"] == "unknown_after_cleanup"


def test_stage04c_rebuild_manifest_and_filters(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    day = date(2015, 5, 22)
    tif = tmp_path / "2015" / "mesh_20150522.tif"
    tif.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), tif)
    monkeypatch.setattr(s, "find_gridrad_files", lambda _d: ([], "none"))
    monkeypatch.setattr(
        s,
        "temporal_coverage_summary",
        lambda *_a, **_k: {"temporal_coverage_status": "missing"},
    )
    n = s.rebuild_manifest_from_outputs(day, day)
    assert n == 1

    assert s.parse_iso_date("2015-05-22") == day
    all_days = [day, date(2015, 5, 23)]
    assert s.filter_days_for_run(all_days, missing_only=False) == all_days
    assert len(s.filter_days_for_run(all_days, missing_only=True)) == 1


def test_stage04c_hourly_fill_and_compute_shi_edge(load_script):
    s = load_script("04c_fill_gridrad_gap.py")
    day = date(2015, 5, 20)
    sev_t = datetime(2015, 5, 20, 12, 0, tzinfo=timezone.utc)
    hr_path = Path("nexrad_3d_v3_1_20150520T130000Z.nc")
    fill = s._hourly_fill_for_severe_gaps([hr_path], [sev_t], day)
    assert fill == [hr_path]

    assert s.compute_shi_column(np.array([30.0]), np.array([3.0]), 2.0, 5.0) == 0.0
    assert s.compute_shi_column(
        np.array([50.0, 50.0]),
        np.array([4.0, 5.0]),
        2.0,
        5.0,
    ) > 0.0


def test_stage04c_load_04b_and_pool_init(load_script, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    mod = s._load_04b_module()
    assert hasattr(mod, "download_for_day_adaptive")

    s._04c_pool_init(False, False)
    assert s._NATIVE_QC_ENABLED is False

    s._04c_pool_init_load_04b()
    assert s._worker_04b_mod is not None


def test_stage04c_run_one_day_with_mock_04b(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    day = date(2015, 5, 1)

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

    s._worker_04b_mod = Fake04b()
    monkeypatch.setattr(s, "process_day", lambda _d: {"files": 1, "source": "gridrad-hourly"})
    ymd, res = s._run_one_day_download_then_process((day, True, 2))
    assert ymd == "20150501"
    assert res["files"] == 1

    s._worker_04b_mod = None
    monkeypatch.setattr(s, "_load_04b_module", lambda: Fake04b())
    ymd2, res2 = s._run_one_day_download_then_process((day, True, 1))
    assert ymd2 == "20150501"


def _inline_process_pool(monkeypatch, module):
    """Run ProcessPoolExecutor map in-process (avoids worker import issues)."""

    class _InlinePool:
        def __init__(self, max_workers=1, initializer=None, initargs=()):
            if initializer is not None:
                initializer(*initargs)

        def map(self, fn, iterable):
            return [fn(x) for x in iterable]

        def shutdown(self, cancel_futures=False):
            return None

    monkeypatch.setattr(module, "ProcessPoolExecutor", _InlinePool)


def test_stage04c_main_branches(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "GRIDRAD_DIR", tmp_path / "gridrad")
    monkeypatch.setattr(s, "GRIDRAD_SEV", tmp_path / "gridrad_severe")
    monkeypatch.setattr(s, "ERA5_FILE", tmp_path / "era5.nc")
    _write_era5_isotherms(tmp_path / "era5.nc")
    monkeypatch.setattr(s, "rebuild_manifest_from_outputs", lambda *_a, **_k: 1)
    monkeypatch.setattr(s, "rebuild_gridrad_days_from_geotiffs", lambda *_a, **_k: ["20150501"])
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(s, "delete_gridrad_inputs_for_day", lambda *_a, **_k: None)
    monkeypatch.setattr(s, "merge_gridrad_days_labels", lambda *_a, **_k: 1)

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--from-date", "2015-05-01", "--until-date", "2015-05-02"])
    assert exc.value.code == 0

    good = tmp_path / "2015" / "mesh_20150501.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good)

    def fake_rglob(self, pattern):
        if pattern == "mesh_????????.tif":
            return iter([good] * 2001)
        return Path.rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    with pytest.raises(SystemExit) as exc:
        s.main(["--validate"])
    assert exc.value.code == 0

    monkeypatch.setattr(
        s,
        "find_gridrad_files",
        lambda _d: ([], "none"),
    )
    with pytest.raises(SystemExit) as exc:
        s.main(["--check-data", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [],
    )
    with pytest.raises(SystemExit) as exc:
        s.main(["--missing-only", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    def proc(_d, native_qc=None):
        return {"files": 1, "source": "gridrad-severe-5min", "peak_mesh75_mm": 45.0, "active_cells": 10}

    monkeypatch.setattr(s, "process_day", proc)
    monkeypatch.setattr(s, "_load_04b_module", lambda: type("B", (), {
        "_request_session": staticmethod(lambda: type("S", (), {"close": lambda self: None})()),
        "download_for_day_adaptive": staticmethod(lambda *_a, **_k: {}),
    })())

    s.main(["--year", "2015", "--month", "5", "--workers", "1", "--with-04b-download"])

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"skipped": True})
    tif_skip = tmp_path / "2015" / "mesh_20150502.tif"
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), tif_skip, tags={"MAX_MESH75_MM": "30.0", "ACTIVE_CELLS": "5"})
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 2)],
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "1"])

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"no_data": True})
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 3)],
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "1"])

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"error": "boom"})
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 4)],
    )
    with pytest.raises(RuntimeError, match="failed convective day"):
        s.main(["--year", "2015", "--month", "5", "--workers", "1"])

    # Parallel workers without 04b download
    _inline_process_pool(monkeypatch, s)
    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"files": 1, "source": "gridrad-hourly-v31", "peak_mesh75_mm": 20.0, "active_cells": 2})
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 5)],
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "2"])

    # Parallel with 04b download note path
    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 6), date(2015, 5, 7)],
    )
    monkeypatch.setattr(s, "_run_one_day_download_then_process", lambda spec: (spec[0].strftime("%Y%m%d"), {"files": 1, "source": "gridrad-hourly", "peak_mesh75_mm": 10.0, "active_cells": 1}))
    s.main(["--year", "2015", "--month", "5", "--workers", "2", "--with-04b-download", "--04b-download-workers", "2"])
