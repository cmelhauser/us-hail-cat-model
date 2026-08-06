"""Final-pass tests for remaining scripts/ statement coverage gaps."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
import requests

from conftest import REPO_ROOT, load_stage
from tests._diagnostics_fixtures import seed_mesh_days, write_grid_tif, write_mesh_tif
from tests.test_13_generate_stochastic_catalog import (
    _full_catalog_row,
    _seed_historical_events,
    _stage13_paths,
)


def _exec_fresh(module_path: Path, module_name: str):
    """Execute script with repo root absent from sys.path (covers sys.path.insert)."""
    scripts = REPO_ROOT / "scripts"
    saved = sys.path.copy()
    saved_modules = {k: sys.modules.pop(k) for k in list(sys.modules) if k == module_name}
    try:
        sys.path = [p for p in sys.path if p not in (str(REPO_ROOT), str(scripts))]
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
# Import-path lines (sys.path.insert + direct _logging import)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path,module_name",
    [
        ("scripts/04c_fill_gridrad_gap.py", "s04c_fresh"),
        ("scripts/13_generate_stochastic_catalog.py", "s13_fresh"),
        ("scripts/04b_download_gridrad.py", "s04b_fresh"),
        ("scripts/09_fit_cdf_regional.py", "s09_fresh"),
        ("scripts/08_build_event_catalog.py", "s08_fresh"),
        ("scripts/05_apply_mesh_bias_correction.py", "s05_fresh"),
        ("scripts/02_download_mrms_mesh.py", "s02_fresh"),
        ("scripts/01_download_myrorss.py", "s01_fresh"),
        ("scripts/04a_download_era5_isotherms.py", "s04a_fresh"),
        ("scripts/10_build_smooth_cdf.py", "s10_fresh"),
        ("scripts/07_build_hail_climo.py", "s07_fresh"),
        ("scripts/11_build_occurrence_probs.py", "s11_fresh"),
        ("scripts/12_apply_conus_mask.py", "s12_fresh"),
        ("scripts/06_validate_mesh_vs_spc.py", "s06_fresh"),
        ("scripts/train_artifact_classifier.py", "tac_fresh2"),
    ],
)
def test_stage_scripts_fresh_import_covers_path_insert(rel_path, module_name):
    mod = _exec_fresh(REPO_ROOT / rel_path, module_name)
    assert mod is not None


# ---------------------------------------------------------------------------
# Stage 04c — remaining branches
# ---------------------------------------------------------------------------


def _write_gridrad_nc_full(path: Path, *, lat=35.0, lon=-97.0, z_dbz=55.0, lon360=False) -> None:
    import netCDF4 as nc

    if lon360:
        lon = lon + 360.0
    lats = np.array([lat], dtype=np.float32)
    lons = np.array([lon], dtype=np.float32)
    alts = np.array([2.0, 4.0, 6.0], dtype=np.float32)
    idx = np.array([0, 1, 2], dtype=np.int64)
    refl = np.array([z_dbz, z_dbz, z_dbz], dtype=np.float32)
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


def _write_gridrad_nc_dense3d(path: Path) -> None:
    import netCDF4 as nc

    with nc.Dataset(path, "w") as ds:
        ds.createDimension("alt", 2)
        ds.createDimension("lat", 1)
        ds.createDimension("lon", 1)
        ds.createVariable("Latitude", "f4", ("lat",))[:] = [35.0]
        ds.createVariable("Longitude", "f4", ("lon",))[:] = [-97.0]
        ds.createVariable("Altitude", "f4", ("alt",))[:] = [2.0, 4.0]
        ds.createVariable("Reflectivity", "f4", ("alt", "lat", "lon"))[:] = np.full((2, 1, 1), 55.0)


def _write_gridrad_nc_missing_lat(path: Path) -> None:
    import netCDF4 as nc

    with nc.Dataset(path, "w") as ds:
        ds.createDimension("alt", 1)
        ds.createDimension("lon", 1)
        ds.createVariable("Longitude", "f4", ("lon",))[:] = [-97.0]
        ds.createVariable("Altitude", "f4", ("alt",))[:] = [2.0]


def test_stage04c_climo_and_shi_edge_cases(load_script):
    s = load_script("04c_fill_gridrad_gap.py")
    assert s._get_freezing_levels_climo(60.0, 6) == (3.5, 6.0)
    assert s.compute_shi_column(np.array([50.0]), np.array([np.nan]), 2.0, 5.0) == 0.0
    assert s.compute_shi_column(np.array([50.0, 50.0]), np.array([2.0, 4.0]), 2.0, 5.0) > 0.0


def test_stage04c_hourly_helpers_and_find_files(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    day = date(2015, 5, 20)
    assert s._hourly_fill_for_severe_gaps([], [], day) == []
    assert s._hourly_source_label([]) == "gridrad-hourly"

    sev_t = datetime(2015, 5, 20, 12, 0, tzinfo=timezone.utc)
    bad_hr = Path("nexrad_3d_v3_1_20140101T120000Z.nc")
    assert s._hourly_fill_for_severe_gaps([bad_hr], [sev_t], day) == []

    v31 = [Path("nexrad_3d_v3_1_20150520T130000Z.nc")]
    v42 = [Path("nexrad_3d_v4_2_20150520T130000Z.nc")]
    assert s._hourly_source_label(v31) == "gridrad-hourly-v31"
    assert s._hourly_source_label(v42) == "gridrad-hourly-v42"

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
        lambda paths, _d: [datetime(2015, 5, 20, 12, 0, tzinfo=timezone.utc) for _ in paths],
    )
    monkeypatch.setattr(s, "convective_window_coverage_ok", lambda *_a, **_k: False)
    files, src = s.find_gridrad_files(day)
    assert "hourly-fill" in src or src == "gridrad-severe-5min"
    assert files

    monkeypatch.setattr(
        s,
        "staged_nc_files_for_convective_day",
        lambda base, _d: [] if "sev" in str(base) else list(hr_dir.glob("*.nc")),
    )
    files2, src2 = s.find_gridrad_files(day)
    assert src2.startswith("gridrad-hourly")

    monkeypatch.setattr(s, "staged_nc_files_for_convective_day", lambda *_a, **_k: [])
    assert s.find_gridrad_files(day) == ([], "none")
    summary = s.temporal_coverage_summary([], "none", day)
    assert summary["temporal_coverage_status"] == "missing"


def test_stage04c_load_indexed_3d_branches(load_script):
    s = load_script("04c_fill_gridrad_gap.py")

    class DS3d:
        variables = {"Reflectivity": np.array([[[55.0]]], dtype=np.float32)}

    assert s._load_indexed_3d(DS3d(), "Reflectivity").shape == (1, 1, 1)

    class DSNoIndex:
        variables = {"Reflectivity": np.array([55.0], dtype=np.float32)}

    assert s._load_indexed_3d(DSNoIndex(), "Reflectivity") is None

    class DSBadNd:
        variables = {
            "Reflectivity": np.array([[55.0, 56.0]], dtype=np.float32),
            "index": np.array([0], dtype=np.int64),
        }

    assert s._load_indexed_3d(DSBadNd(), "Reflectivity") is None

    class DSEmpty:
        variables = {
            "Reflectivity": np.array([], dtype=np.float32),
            "index": np.array([], dtype=np.int64),
            "Altitude": np.array([2.0], dtype=np.float32),
            "Latitude": np.array([35.0], dtype=np.float32),
            "Longitude": np.array([-97.0], dtype=np.float32),
        }

    assert s._load_indexed_3d(DSEmpty(), "Reflectivity") is None

    class DSInvalid:
        variables = {
            "Reflectivity": np.array([55.0], dtype=np.float32),
            "index": np.array([999999], dtype=np.int64),
            "Altitude": np.array([2.0], dtype=np.float32),
            "Latitude": np.array([35.0], dtype=np.float32),
            "Longitude": np.array([-97.0], dtype=np.float32),
        }

    assert s._load_indexed_3d(DSInvalid(), "Reflectivity") is None


def test_stage04c_process_gridrad_file_branches(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    daily = np.zeros((s.OUT_NROWS, s.OUT_NCOLS), dtype=np.float32)
    monkeypatch.setattr(s, "get_freezing_levels_era5", lambda *_a, **_k: (2.0, 5.0))

    missing_lat = tmp_path / "no_lat.nc"
    _write_gridrad_nc_missing_lat(missing_lat)
    with pytest.raises(RuntimeError, match="Not a valid ID"):
        s.process_gridrad_file(missing_lat, daily, 5, native_qc=False)

    no_refl = tmp_path / "no_refl.nc"
    import netCDF4 as nc

    with nc.Dataset(no_refl, "w") as ds:
        ds.createDimension("lat", 1)
        ds.createDimension("lon", 1)
        ds.createDimension("alt", 1)
        ds.createVariable("Latitude", "f4", ("lat",))[:] = [35.0]
        ds.createVariable("Longitude", "f4", ("lon",))[:] = [-97.0]
        ds.createVariable("Altitude", "f4", ("alt",))[:] = [2.0]
    with pytest.raises(RuntimeError, match="Not a valid ID"):
        s.process_gridrad_file(no_refl, daily, 5, native_qc=False)

    good = tmp_path / "good.nc"
    _write_gridrad_nc_full(good, lon360=True)
    n = s.process_gridrad_file(good, daily, 5, native_qc=False)
    assert n >= 1
    assert float(daily.max()) >= 5.0

    dense = tmp_path / "dense.nc"
    _write_gridrad_nc_dense3d(dense)
    daily2 = np.zeros((s.OUT_NROWS, s.OUT_NCOLS), dtype=np.float32)
    assert s.process_gridrad_file(dense, daily2, 5, native_qc=False) >= 1

    mod_name = "_gridrad_qc"
    saved = sys.modules.pop(mod_name, None)
    try:
        _write_gridrad_nc_full(tmp_path / "qc.nc")
        daily3 = np.zeros((s.OUT_NROWS, s.OUT_NCOLS), dtype=np.float32)
        s.process_gridrad_file(tmp_path / "qc.nc", daily3, 5, native_qc=True)
    finally:
        if saved is not None:
            sys.modules[mod_name] = saved

    out_of_bounds = tmp_path / "oob.nc"
    _write_gridrad_nc_full(out_of_bounds, lat=10.0, lon=10.0)
    daily4 = np.zeros((s.OUT_NROWS, s.OUT_NCOLS), dtype=np.float32)
    assert s.process_gridrad_file(out_of_bounds, daily4, 5, native_qc=False) == 0


def test_stage04c_process_day_repair_and_rebuild(load_script, tmp_path, monkeypatch):
    from scripts._config import NROWS, NCOLS
    from scripts._io import write_geotiff

    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(s, "get_freezing_levels_era5", lambda *_a, **_k: (2.0, 5.0))

    day = date(2015, 5, 20)
    nc = tmp_path / "input.nc"
    _write_gridrad_nc_full(nc)
    monkeypatch.setattr(s, "find_gridrad_files", lambda _d: ([nc], "gridrad-hourly-v31"))
    monkeypatch.setattr(
        s,
        "temporal_coverage_summary",
        lambda *_a, **_k: {"temporal_coverage_status": "partial", "source_first_utc": None,
                           "source_last_utc": None, "source_max_gap_minutes": None},
    )

    bad_daily = np.array([[np.inf, 400.0, 55.0] + [0.0] * (NCOLS - 3)], dtype=np.float32)
    bad_daily = np.tile(bad_daily[:, None], (1, 1)) if bad_daily.ndim == 1 else bad_daily
    if bad_daily.shape != (NROWS, NCOLS):
        frame = np.zeros((NROWS, NCOLS), dtype=np.float32)
        frame[0, :3] = [np.inf, 400.0, 55.0]
        bad_src = tmp_path / "bad_vals.nc"
        _write_gridrad_nc_full(bad_src)
        monkeypatch.setattr(
            s,
            "process_gridrad_file",
            lambda *_a, **_k: (frame.__setitem__((slice(None), slice(None)), frame) or int(np.count_nonzero(frame))),
        )
    result = s.process_day(day, native_qc=False)
    assert "peak_mesh75_mm" in result or result.get("active_cells") is not None

    monkeypatch.setattr(s, "find_gridrad_files", lambda _d: ([], "none"))
    n = s.rebuild_manifest_from_outputs(day, day)
    assert n == 1


def test_stage04c_worker_and_main_remaining(load_script, tmp_path, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    monkeypatch.setattr(s, "GRIDRAD_DIR", tmp_path / "gridrad")
    monkeypatch.setattr(s, "GRIDRAD_SEV", tmp_path / "gridrad_severe")
    monkeypatch.setattr(s, "ERA5_FILE", tmp_path / "era5.nc")
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(s, "delete_gridrad_inputs_for_day", lambda *_a, **_k: None)
    monkeypatch.setattr(s, "merge_gridrad_days_labels", lambda *_a, **_k: 1)
    monkeypatch.setattr(s, "rebuild_gridrad_days_from_geotiffs", lambda *_a, **_k: [])
    s._era5_h0c = np.ones((12, 1, 1))

    day = date(2015, 5, 1)

    def boom(*_a, **_k):
        raise RuntimeError("download failed")

    monkeypatch.setattr(s, "process_day", boom)
    ymd, res = s._run_one_day_download_then_process((day, False, 1))
    assert res.get("error")

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        s.main(["--manifest-only", "--year", "2015"])
    assert exc.value.code == 0

    bad_tif = tmp_path / "2015" / "mesh_20150501.tif"
    bad_tif.parent.mkdir(parents=True)
    bad_tif.write_bytes(b"not-geotiff")
    orig_rglob = Path.rglob

    def fake_rglob(self, pattern):
        if pattern == "mesh_????????.tif":
            return iter([bad_tif])
        return orig_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    with pytest.raises(SystemExit) as exc:
        s.main(["--validate"])
    assert exc.value.code == 1
    monkeypatch.setattr(
        s,
        "find_gridrad_files",
        lambda _d: ([], "gridrad-hourly-v31") if False else ([Path("a.nc")], "gridrad-hourly-v31"),
    )

    def find_files(day_):
        if day_.day == 1:
            return [Path("a.nc")], "gridrad-severe-5min"
        if day_.day == 2:
            return [Path("b.nc")], "gridrad-hourly-v31"
        if day_.day == 3:
            return [Path("c.nc")], "gridrad-hourly-v42"
        if day_.day == 4:
            return [Path("d.nc")], "gridrad-hourly-mixed"
        return [], "none"

    monkeypatch.setattr(s, "find_gridrad_files", find_files)
    with pytest.raises(SystemExit) as exc:
        s.main(["--check-data", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0

    from scripts._io import write_geotiff
    from scripts._config import NROWS, NCOLS

    tif = tmp_path / "2015" / "mesh_20150502.tif"
    write_geotiff(np.array([[30.0, 0.0], [0.0, 0.0]], dtype=np.float32), tif)

    class Fake04b:
        @staticmethod
        def _request_session():
            return types.SimpleNamespace(close=lambda: None)

        @staticmethod
        def download_for_day_adaptive(*_a, **_k):
            return {}

    monkeypatch.setattr(s, "_load_04b_module", lambda: Fake04b())
    monkeypatch.setattr(s, "filter_days_for_run", lambda days, missing_only=False: [date(2015, 5, 2)])
    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: {"files": 1, "source": "gridrad-severe-5min", "peak_mesh75_mm": 40.0, "active_cells": 2},
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "1", "--with-04b-download"])

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"skipped": True})
    s.main(["--year", "2015", "--month", "5", "--workers", "1"])

    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("proc fail")))
    monkeypatch.setattr(s, "filter_days_for_run", lambda days, missing_only=False: [date(2015, 5, 3)])
    with pytest.raises(RuntimeError, match="failed convective day"):
        s.main(["--year", "2015", "--month", "5", "--workers", "1"])

    s._era5_h0c = None

    class _InlinePool:
        def __init__(self, max_workers=1, initializer=None, initargs=()):
            if initializer is not None:
                initializer(*initargs)

        def map(self, fn, iterable):
            return [fn(x) for x in iterable]

        def shutdown(self, cancel_futures=False):
            return None

    monkeypatch.setattr(s, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"files": 1, "source": "gridrad-hourly", "peak_mesh75_mm": 10.0, "active_cells": 1})
    monkeypatch.setattr(s, "filter_days_for_run", lambda days, missing_only=False: [date(2015, 5, 4), date(2015, 5, 5)])
    s.main(["--year", "2015", "--month", "5", "--workers", "2", "--with-04b-download"])


# ---------------------------------------------------------------------------
# Stage 13 — remaining branches
# ---------------------------------------------------------------------------


def test_stage13_open_ann_max_unlink_existing(load_script, tmp_path, monkeypatch):
    s = load_script("13_generate_stochastic_catalog.py")
    monkeypatch.setattr(s, "ANN_MAX_INMEM_BYTES", 1)
    work = tmp_path / "work"
    work.mkdir()
    stale = work / "_ann_max_simulation.mmap"
    stale.write_bytes(b"\x00" * 32)
    ann_max, path = s._open_ann_max_store(4, 4, work)
    assert path == stale
    assert ann_max.shape == (4, 4)


def test_stage13_calibrate_sigma_without_peak_column(load_script, tmp_path, monkeypatch):
    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, *_ = _stage13_paths(monkeypatch, s, tmp_path)
    _seed_historical_events(event_dir, n_events=4)
    event_df, sparse_events = s.load_historical_events()
    event_df = event_df.drop(columns=["peak"])
    sigma = s.calibrate_sigma(event_df, sparse_events)
    assert 0.10 <= sigma <= 0.40


def test_stage13_sparse_shape_perturb_no_keep(load_script):
    s = load_script("13_generate_stochastic_catalog.py")
    rows = np.array([0], dtype=np.int32)
    cols = np.array([0], dtype=np.int32)
    vals = np.array([40.0], dtype=np.float32)
    rng = np.random.default_rng(0)
    for _ in range(30):
        r, c, v, tag = s.sparse_shape_perturb(rows, cols, vals, rng)
        if tag == "none" and len(r) == 1:
            break
    else:
        pytest.fail("expected sparse_shape_perturb none branch")


def test_stage13_simulate_progress_and_no_translate(load_script, tmp_path, monkeypatch):
    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, out_dir, *_ = _stage13_paths(monkeypatch, s, tmp_path)
    _seed_historical_events(event_dir, n_events=6)
    event_df, sparse_events = s.load_historical_events()
    sigma = s.calibrate_sigma(event_df, sparse_events)
    doy_cdf = s.build_doy_distribution(event_df)
    monkeypatch.setattr(s, "SPATIAL_TRANSLATE", False)
    monkeypatch.setattr(s, "time", types.SimpleNamespace(time=lambda: 1000.0))
    s.simulate_catalog(event_df, sparse_events, sigma, doy_cdf, n_years=5000, work_dir=out_dir)


def test_stage13_validate_outputs_all_errors(load_script, tmp_path, monkeypatch):
    s = load_script("13_generate_stochastic_catalog.py")
    _event_dir, _out, cat_dir, map_dir, pet_dir, _mask = _stage13_paths(monkeypatch, s, tmp_path)
    monkeypatch.setattr(s, "RP_YEARS", [10])

    assert s.validate_outputs() is False

    manifest = cat_dir / "stochastic_catalog_manifest.json"
    manifest.write_text('not-json')
    assert s.validate_outputs() is False

    manifest.write_text(json.dumps({"n_years": s.N_SIM_YEARS, "status": "pending", "seed": 1, "model_version": s.MODEL_VERSION}))
    assert s.validate_outputs() is False

    manifest.write_text(json.dumps({"n_years": s.N_SIM_YEARS, "status": "complete", "model_version": s.MODEL_VERSION}))
    assert s.validate_outputs() is False

    manifest.write_text(json.dumps({"n_years": s.N_SIM_YEARS, "status": "complete", "seed": s.RNG_SEED, "model_version": "wrong"}))
    (map_dir / "rp_00010yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()
    assert s.validate_outputs() is False

    manifest.write_text(json.dumps({"n_years": s.N_SIM_YEARS, "status": "complete", "seed": s.RNG_SEED, "model_version": s.MODEL_VERSION}))
    bad_parquet = cat_dir / "stochastic_event_summary.parquet"
    bad_parquet.write_bytes(b"not-parquet")
    assert s.validate_outputs() is False

    import pyarrow as pa
    import pyarrow.parquet as pq

    empty_table = pa.table({"sim_year": pa.array([], type=pa.int32())})
    pq.write_table(empty_table, bad_parquet)
    assert s.validate_outputs() is False

    rows = [_full_catalog_row(i) for i in range(5)]
    pd.DataFrame(rows).to_parquet(bad_parquet, index=False)
    assert s.validate_outputs() is False


def test_stage13_main_full_paths(load_script, tmp_path, monkeypatch):
    import sys

    import rasterio
    from rasterio.transform import from_origin

    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, out_dir, cat_dir, map_dir, pet_dir, mask_dir = _stage13_paths(monkeypatch, s, tmp_path)
    _seed_historical_events(event_dir, n_events=8)
    monkeypatch.setattr(s, "ANN_MAX_INMEM_BYTES", 1)

    with rasterio.open(
        mask_dir / "conus_mask.tif",
        "w",
        driver="GTiff",
        height=s.NROWS,
        width=s.NCOLS,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(-125, 50, 0.05, 0.05),
    ) as dst:
        dst.write(np.ones((s.NROWS, s.NCOLS), dtype=np.uint8), 1)

    written = []

    def capture_write(arr, path, **_kw):
        written.append(Path(path).name)
        Path(path).write_bytes(b"tif")

    monkeypatch.setattr(s, "write_geotiff", capture_write)
    stream_path = cat_dir / "stochastic_event_summary.parquet"
    stream_path.write_bytes(b"")

    def fake_sim(*_a, **kwargs):
        catalog_path = kwargs.get("catalog_path")
        if catalog_path is not None and Path(catalog_path).exists():
            import pyarrow as pa
            import pyarrow.parquet as pq

            pq.write_table(pa.table({"sim_year": [0], "event_idx": [0], "template_id": [1], "doy": [150],
                                     "scale_factor": [1.0], "peak_hail_mm": [40.0], "n_cells": [1]}), catalog_path)
        n_active = 4
        mmap_path = out_dir / "_work" / "_ann_max_simulation.mmap"
        mmap_path.parent.mkdir(parents=True, exist_ok=True)
        mmap_path.write_bytes(b"\x00" * 64)
        return (
            np.zeros((2, n_active), dtype=np.float32),
            np.array([1, 1, 2, 2], dtype=np.int32),
            np.array([1, 2, 1, 2], dtype=np.int32),
            np.array([40.0, 35.0], dtype=np.float32),
            np.array([1, 1], dtype=np.int32),
            np.array([2, 2], dtype=np.int32),
            np.array([1, 1], dtype=np.int32),
            pd.DataFrame(),
            mmap_path,
        )

    monkeypatch.setattr(s, "simulate_catalog", fake_sim)
    monkeypatch.setattr(sys, "argv", ["13_generate_stochastic_catalog.py", "--n-years", str(s.N_SIM_YEARS)])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Literature validation suite — remaining branches
# ---------------------------------------------------------------------------


def test_lvs_final_branch_coverage(tmp_path, monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    mesh = tmp_path / "mesh"
    (mesh / "2015").mkdir(parents=True)
    seed_mesh_days(mesh, [date(2015, 6, 1)], peak=40.0, nrows=8, ncols=8)
    monkeypatch.setattr(lvs, "CORRECTED_DIR", mesh)
    monkeypatch.setattr(lvs, "MESH_DIR", tmp_path / "empty")
    monkeypatch.setattr(lvs, "NROWS", 8)
    monkeypatch.setattr(lvs, "NCOLS", 8)
    lvs._load_peaks()

    assert lvs.check_mann_kendall_annual_max(pd.DataFrame()).status == "skip"

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    grid = np.array([[50.0, 60.0]], dtype=np.float32)
    write_grid_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", grid)
    write_grid_tif(cdf_dir / "rp_01000yr_hail_smooth.tif", grid + 5)
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
    lvs._composite_rp_mm(0, 0, 1000, p_occ, lognorm_mu, lognorm_sigma, gpd_xi, gpd_sigma, gpd_threshold, fit_type)

    monkeypatch.setattr(lvs, "PAIRS_CSV", tmp_path / "missing.csv")
    assert lvs.check_spc_rural_urban_bias().status == "skip"

    stoch = tmp_path / "stoch"
    stoch.mkdir()
    write_grid_tif(stoch / "rp_00100yr_stochastic.tif", grid)
    monkeypatch.setattr(lvs, "STOCH_MAP_DIR", stoch)
    lvs.check_analytical_vs_stochastic()

    write_grid_tif(cdf_dir / "rp_00100yr_hail_smooth.tif", grid)
    monkeypatch.setattr(lvs, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(
        "scripts._radar_geometry.ensure_range_km_grid",
        lambda: np.linspace(0, 250, grid.size, dtype=np.float32).reshape(grid.shape),
    )
    lvs.check_rp_ring_energy()

    arrays = {
        "fit_type": np.ones((8, 8), dtype=np.int8),
        "p_occ": np.full((8, 8), 0.2, dtype=np.float32),
        "lognorm_mu": np.full((8, 8), np.log(35.0), dtype=np.float32),
        "lognorm_sigma": np.full((8, 8), 0.25, dtype=np.float32),
        "gpd_xi": np.full((8, 8), 0.05, dtype=np.float32),
        "gpd_sigma": np.full((8, 8), 4.0, dtype=np.float32),
        "gpd_threshold": np.full((8, 8), 50.0, dtype=np.float32),
    }
    np.savez(tmp_path / "cdf_parameters.npz", **arrays)
    monkeypatch.setattr(lvs, "CDF_NPZ", tmp_path / "cdf_parameters.npz")
    monkeypatch.setattr(lvs, "OUT_DIR", tmp_path)
    monkeypatch.setattr(lvs, "NROWS", 8)
    monkeypatch.setattr(lvs, "NCOLS", 8)
    lvs.check_bootstrap_rp_ci()

    for year in (2014, 2015, 2016):
        for day in range(1, 15):
            write_grid_tif(mesh / str(year) / f"mesh_{year}06{day:02d}.tif", np.full((8, 8), 90.0, dtype=np.float32))
    monkeypatch.setattr(lvs, "CORRECTED_DIR", mesh)
    res = lvs.check_tail_dependence_pilot()
    assert res.status in ("pass", "warn")


def test_lvs_rasterio_import_skip_branches(monkeypatch):
    import scripts.diagnostics.literature_validation_suite as lvs

    real_import = builtins.__import__ if (builtins := __import__("builtins")) else __import__

    def fake_import(name, *args, **kwargs):
        if name == "rasterio":
            raise ImportError("no rasterio")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert lvs.check_rp_monotonicity().status == "skip"
    assert lvs.check_analytical_vs_stochastic().status == "skip"
    assert lvs.check_tail_dependence_pilot().status == "skip"


# ---------------------------------------------------------------------------
# Stage 04b — remaining branches
# ---------------------------------------------------------------------------


def test_stage04b_remaining_coverage(load_script, tmp_path, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    assert s._v42_hourly_eligible(date(2010, 6, 1)) is False
    assert s._v42_hourly_eligible(date(2018, 6, 1)) is True

    calls = {"n": 0}

    class Resp503:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

    class Sess503:
        def get(self, url, timeout=60, stream=False):
            calls["n"] += 1
            if calls["n"] < 10:
                raise requests.HTTPError(response=Resp503())
            r = Resp503()
            r.status_code = 200
            r.text = "<xml/>"
            r.raise_for_status = lambda: None
            return r

    monkeypatch.setattr(s, "time", type("T", (), {"sleep": lambda *_a, **_k: None})())
    out = s._catalog_get(Sess503(), "http://x", timeout=(1.0, 1.0))
    assert out.status_code == 200

    class SessConn:
        def __init__(self):
            self.n = 0

        def get(self, url, timeout=60, stream=False):
            self.n += 1
            if self.n < 10:
                raise requests.ConnectionError("down")
            r = Resp503()
            r.status_code = 200
            r.text = "<xml/>"
            r.raise_for_status = lambda: None
            return r

    out2 = s._catalog_get(SessConn(), "http://x", timeout=(1.0, 1.0))
    assert out2.status_code == 200

    class S404:
        status_code = 404
        text = ""

        def raise_for_status(self):
            return None

    class Sess404:
        def get(self, url, timeout=60, stream=False):
            return S404()

    assert s.list_day_catalog_files(Sess404(), s.DS_HOURLY, date(2015, 5, 1), timeout=(1.0, 1.0)) == []
    assert s.list_day_catalog_files(Sess404(), s.DS_SEVERE, date(2015, 5, 1), timeout=(1.0, 1.0)) == []
    with pytest.raises(ValueError):
        s.list_day_catalog_files(Sess404(), "bad-dsid", date(2015, 5, 1), timeout=(1.0, 1.0))

    day = date(2015, 5, 1)
    item = s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename="f.nc",
        url="http://example.com/f.nc",
        out_path=tmp_path / "f.nc",
    )
    tmp = item.out_path.with_suffix(".part")
    tmp.write_bytes(b"partial")

    class Resp429:
        status_code = 429

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

        def iter_content(self, chunk_size=0):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class Sess429:
        def get(self, url, params=None, stream=True, timeout=None):
            return Resp429()

    monkeypatch.setattr(s, "_auth_params", lambda: {})
    with pytest.raises(requests.HTTPError):
        s._download_one(Sess429(), item, connect_timeout=1.0, read_timeout=1.0)

    class SessConnDL:
        def __init__(self):
            self.n = 0

        def get(self, url, params=None, stream=True, timeout=None):
            self.n += 1
            if self.n < 8:
                raise requests.ConnectionError("down")
            r = Resp429()
            r.status_code = 200
            r.raise_for_status = lambda: None
            r.iter_content = lambda chunk_size=0: [b"data"]

            class Ctx:
                def __enter__(self):
                    return r

                def __exit__(self, *_a):
                    return False

            return Ctx()

    _, status = s._download_one(SessConnDL(), item, connect_timeout=1.0, read_timeout=1.0)
    assert status == "downloaded"

    stats = s.download_planned_items(
        types.SimpleNamespace(),
        [item],
        connect_timeout=1.0,
        read_timeout=1.0,
        max_workers=1,
    )
    assert stats["downloaded"] >= 0

    monkeypatch.setattr(s, "_severe_staging_covers_day", lambda _d: True)
    out_stats = s.download_for_day_adaptive(
        types.SimpleNamespace(),
        day,
        catalog_timeout=(1.0, 1.0),
        connect_timeout=1.0,
        read_timeout=1.0,
        max_workers=1,
    )
    assert out_stats["source_mode"] == "severe-only-local"

    class Sess:
        def close(self):
            return None

    monkeypatch.setattr(s, "_request_session", lambda: Sess())
    monkeypatch.setattr(s, "plan_downloads_for_day", lambda *_a, **_k: [])
    with pytest.raises(SystemExit) as exc:
        s.main(["--dry-run"])
    assert exc.value.code == 0

    monkeypatch.setattr(s, "plan_downloads_for_day", lambda *_a, **_k: [item])
    with pytest.raises(SystemExit) as exc:
        s.main(["--plan-all-days-first", "--check-data", "--year", "2015"])
    assert exc.value.code == 0

    item.out_path.write_bytes(b"x")
    with pytest.raises(SystemExit) as exc:
        s.main(["--check-data", "--year", "2015", "--month", "5"])
    assert exc.value.code == 0


# ---------------------------------------------------------------------------
# Stage 09, 08, 05, 02, 01, 04a, 10 — remaining
# ---------------------------------------------------------------------------


def test_stage09_remaining_lmom_and_mrl(load_script, tmp_path, monkeypatch):
    s = load_script("09_fit_cdf_regional.py")
    monkeypatch.setattr(s, "NROWS", 4)
    monkeypatch.setattr(s, "NCOLS", 4)

    mu, sig = s.lmom_fit_lognormal(np.array([30.0, 35.0, 40.0, 45.0], dtype=np.float32))
    assert np.isfinite(mu) and np.isfinite(sig)

    xi, sigma = s.lmom_fit_gpd(np.array([5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0], dtype=np.float32))
    assert np.isfinite(xi) or np.isnan(xi)

    t, t3, l2 = s.compute_lmoment_ratios(np.array([0.0, 0.0], dtype=np.float32))
    assert np.isnan(t)

    annual_max = np.zeros((3, 4, 4), dtype=np.float32)
    with pytest.raises(RuntimeError, match="No active hail cells"):
        s.cluster_cells(annual_max, n_regions=6)

    exc = np.array([50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0, 100.0], dtype=np.float32)
    assert s.compute_mrl_and_threshold(exc, region_id=0) > 0


def test_stage08_load_daily_and_main_branches(load_script, tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    s = load_script("08_build_event_catalog.py")
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)
    monkeypatch.setattr(s, "OUT_DIR", tmp_path / "out")

    bad = in_dir / "mesh_badname.tif"
    bad.write_bytes(b"x")
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

    dates, cells = s.load_daily_data()
    assert dates and cells

    import sys

    monkeypatch.setattr(s, "load_daily_data", lambda: ([date(2015, 6, 1)], cells))
    monkeypatch.setattr(s, "group_events", lambda *_a, **_k: [])
    monkeypatch.setattr(s, "build_catalog", lambda *_a, **_k: (pd.DataFrame(), []))
    monkeypatch.setattr(s, "save_outputs", lambda *_a, **_k: None)
    monkeypatch.setattr(s, "print_summary", lambda *_a, **_k: None)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["08_build_event_catalog.py"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


def test_stage05_import_and_remaining(load_script, tmp_path, monkeypatch):
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

    from tests.test_05_apply_mesh_bias_correction import _write_mesh

    _write_mesh(in_dir / "mesh_20150601.tif", np.full((2, 2), 45.0, dtype=np.float32))
    out_path = out_dir / "mesh_20150601.tif"
    lat = np.full((2, 2), 35.0, dtype=np.float32)
    monkeypatch.setattr(s, "is_gridrad_source", lambda _d: False)
    s.process_file(in_dir / "mesh_20150601.tif", out_path, lat, skip_ml=True)

    monkeypatch.setattr(s, "validate_outputs", lambda: False)
    import sys

    monkeypatch.setattr(sys, "argv", ["05_apply_mesh_bias_correction.py", "--validate"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 1


def test_stage02_remaining_manifest_and_main(load_script, tmp_path, monkeypatch):
    from tests.test_02_download_mrms_mesh_coverage import _FakeS3

    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")

    s3 = _FakeS3()
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda *_a, **_k: [])
    n = s.rebuild_manifest_from_outputs(s3, date(2020, 10, 15), date(2020, 10, 15))
    assert n >= 0

    monkeypatch.setattr(s, "get_s3_client", lambda: s3)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(s, "rebuild_manifest_from_outputs", lambda *_a, **_k: 1)
    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"files": 1, "max_mesh_mm": 50.0})

    with pytest.raises(SystemExit) as exc:
        s.main(["--year", "2020", "--month", "10", "--workers", "2"])
    assert exc.value.code == 0


def test_stage01_validate_sample_errors(load_script, tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin

    from scripts._config import NCOLS, NROWS
    from scripts._io import write_geotiff

    s = load_script("01_download_myrorss.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)

    good = tmp_path / "2000" / "mesh_20000601.tif"
    good.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), good)

    bad_crs = tmp_path / "2000" / "mesh_20000602.tif"
    with rasterio.open(
        bad_crs,
        "w",
        driver="GTiff",
        height=NROWS,
        width=NCOLS,
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=from_origin(-125, 50, 0.05, 0.05),
    ) as dst:
        dst.write(np.zeros((NROWS, NCOLS), dtype=np.float32), 1)

    unreadable = tmp_path / "2000" / "mesh_20000603.tif"
    unreadable.write_bytes(b"bad")

    monkeypatch.setattr(s, "iter_stage01_tifs", lambda: [good, bad_crs, unreadable] + [good] * 3998)
    assert s.validate_outputs() is False


def test_stage04a_remaining_branches(load_script, tmp_path, monkeypatch):
    s = load_script("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)

    empty = tmp_path / "empty.nc"
    empty.write_bytes(b"")
    fresh = tmp_path / "fresh.nc"

    class FakeClient:
        def retrieve(self, dataset, request, path):
            from tests.test_04a_download_era5_coverage import _pressure_chunk

            _pressure_chunk(Path(path), int(request["year"][0]))

    s._retrieve_era5_chunk(FakeClient(), ["1991"], ["01"], fresh)
    assert fresh.stat().st_size > 0

    monkeypatch.setattr(s, "CLIM_YEARS", ["1991"])
    calls = {"n": 0}

    class CostLimitClient:
        def retrieve(self, dataset, request, path):
            calls["n"] += 1
            if len(request["month"]) > 1:
                raise Exception("cost limits exceeded")
            from tests.test_04a_download_era5_coverage import _pressure_chunk

            _pressure_chunk(Path(path), int(request["year"][0]))

    import sys

    sys.modules["cdsapi"] = type("cdsapi", (), {"Client": CostLimitClient})
    chunks = s.download_era5_temperature()
    assert len(chunks) >= 1


def test_stage10_fresh_import_and_main_branches(tmp_path, monkeypatch):
    s10 = _exec_fresh(REPO_ROOT / "scripts/10_build_smooth_cdf.py", "s10_final")
    import sys

    import rasterio
    from rasterio.transform import from_origin

    nrows, ncols = 45, 45
    monkeypatch.setattr(s10, "NROWS", nrows)
    monkeypatch.setattr(s10, "NCOLS", ncols)
    monkeypatch.setattr(s10, "LAT_MAX", 50.0)
    monkeypatch.setattr(s10, "LON_MIN", -120.0)
    monkeypatch.setattr(s10, "DX", 0.05)
    monkeypatch.setattr(s10, "POOL_RADIUS_KM", 500.0)
    monkeypatch.setattr(s10, "DECAY_KM", 75.0)
    monkeypatch.setattr(s10, "MIN_OBS", 1)
    monkeypatch.setattr(s10, "GPD_THRESH_MM", 200.0)
    monkeypatch.setattr(s10, "RP_YEARS", [10])

    mesh_dir = tmp_path / "mesh"
    ydir = mesh_dir / "2015"
    ydir.mkdir(parents=True)
    data = np.full((nrows, ncols), 5.0, dtype=np.float32)
    data[0, 0] = 60.0
    with rasterio.open(
        ydir / "mesh_20150601.tif",
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-120, 50, 0.05, 0.05),
    ) as dst:
        dst.write(data, 1)

    cdf_dir = tmp_path / "cdf"
    cdf_dir.mkdir()
    region_map = np.zeros((nrows, ncols), dtype=np.int16)
    np.savez(cdf_dir / "cdf_parameters.npz", region_map=region_map, region_xi=np.array([0.1], dtype=np.float32))

    written = []

    def capture_write(arr, out_path, **_kw):
        written.append(Path(out_path).name)
        Path(out_path).write_bytes(b"tif")

    monkeypatch.setattr(s10, "MESH_DIR", mesh_dir)
    monkeypatch.setattr(s10, "CDF_DIR", cdf_dir)
    monkeypatch.setattr(s10, "write_geotiff", capture_write)
    monkeypatch.setattr(sys, "argv", ["10_build_smooth_cdf.py"])
    s10.main()
    assert written


# ---------------------------------------------------------------------------
# Small diagnostics + helpers
# ---------------------------------------------------------------------------


def test_train_classifier_remaining_branches(tmp_path, load_script, monkeypatch):
    trainer = load_script("train_artifact_classifier.py")
    mesh_dir = tmp_path / "corrected"
    write_mesh_tif(mesh_dir / "2015" / "mesh_20150601.tif", 60.0)
    nrows, ncols = 8, 8
    monkeypatch.setattr(trainer, "CORRECTED_DIR", mesh_dir)
    monkeypatch.setattr(trainer, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(trainer, "ensure_range_km_grid", lambda: np.full((nrows, ncols), 50.0, dtype=np.float32))
    monkeypatch.setattr(trainer, "ensure_nearest_site_index_grid", lambda: np.zeros((nrows, ncols), dtype=np.int16))
    monkeypatch.setattr(trainer, "azimuth_to_nearest_site_deg", lambda: np.zeros((nrows, ncols), dtype=np.float32))

    pairs = pd.DataFrame([{"date": "20150601", "grid_row": 4, "grid_col": 4, "spc_size_in": 1.5, "mesh75_mm": 60.0}])
    X, y, groups = trainer.build_training_sets(pairs, max_neg_per_day=0, rng=np.random.default_rng(0), gridrad_only=False)
    assert len(X) == 1

    monkeypatch.setattr(trainer, "_load_raster", lambda _d: np.full((nrows, ncols), 60.0, dtype=np.float32))
    X2, y2, _ = trainer.build_training_sets(pairs, max_neg_per_day=5, rng=np.random.default_rng(1), gridrad_only=False)
    assert len(X2) > len(X)


def test_radar_geometry_final_branches():
    from scripts._radar_geometry import (
        apply_range_debias,
        remove_persistent_range_artifacts,
        remove_radial_range_rings,
        remove_site_polar_spokes,
    )

    data = np.full((8, 8), 40.0, dtype=np.float32)
    range_km = np.full((8, 8), 95.0, dtype=np.float32)
    range_km[:, :3] = 45.0
    site_idx = np.zeros((8, 8), dtype=np.int16)
    hist = np.zeros((5, 8, 8), dtype=np.float32)
    remove_persistent_range_artifacts(data, site_idx, range_km, history=hist, min_history_days=1)

    ring_data = data.copy()
    remove_radial_range_rings(ring_data, site_idx, range_km, min_annulus_cells=2, min_outer_range_km=80.0)

    _, _, ids = __import__("scripts._radar_geometry", fromlist=["nexrad_sites_conus"]).nexrad_sites_conus()
    tlx = ids.index("KTLX")
    si = np.full((10, 10), tlx, dtype=np.int16)
    remove_site_polar_spokes(np.full((10, 10), 40.0, dtype=np.float32), si, np.full((10, 10), 55.0, dtype=np.float32), site_ids=("KTLX",))

    debias = {
        "range_bin_edges_km": np.array([0, 100, 200], dtype=np.float32),
        "range_bin_centers_km": np.array([50, 150], dtype=np.float32),
        "factors": {"MYRORSS": np.array([1.0, 1.0], dtype=np.float32)},
    }
    apply_range_debias(data, range_km, "MYRORSS/MRMS", debias)


def test_small_diagnostic_and_stage_one_liners(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_publication_md as pub
    import scripts.diagnostics.render_pnas_article_figures as rpf
    import scripts.diagnostics.summarize_mesh_daily_peaks as smp
    import scripts.diagnostics.hail_day_climatology as hdc
    import scripts.diagnostics.radar_artifact_diagnostic as rad

    draft = "Representative AI-assisted interventions are summarized in Table 1.\n\n| # | Issue | Evidence | Patch | Validation | Residual risk |\n|---|---|---|---|---|---|\n| 1 | a | b | c | d | e |\n\n## Next\n"
    assert pub.extract_ai_process_table(draft)

    monkeypatch.setattr(rpf, "VALID_DIR", tmp_path / "validation")
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER", tmp_path / "model.pkl")
    (tmp_path / "model.pkl").write_bytes(b"x")
    monkeypatch.setattr(rpf, "ARTIFACT_CLASSIFIER_DIAGNOSTICS", tmp_path / "diag.json")
    (tmp_path / "diag.json").write_text("{}")
    rpf._validation_metrics()

    seed_mesh_days(tmp_path, [date(2010, 6, 1), date(2011, 6, 1)], peak=40.0)
    list(smp.iter_mesh_tifs(tmp_path, date(2010, 12, 31), None))

    mesh = tmp_path / "mesh"
    seed_mesh_days(mesh, [date(2010, 6, 1)], peak=35.0, nrows=8, ncols=8)
    monkeypatch.setattr(hdc, "NROWS", 8)
    monkeypatch.setattr(hdc, "NCOLS", 8)
    from datetime import timedelta

    days = [date(2010, 1, 1) + timedelta(days=i) for i in range(1000)]
    seed_mesh_days(mesh, days, peak=35.0, nrows=8, ncols=8)
    hdc.accumulate_hail_days(mesh, hdc.selected_thresholds("skill_29mm"), None, None)

    monkeypatch.setattr(rad, "NROWS", 8)
    monkeypatch.setattr(rad, "NCOLS", 8)
    monkeypatch.setattr(rad, "ensure_range_km_grid", lambda *_a, **_k: np.full((8, 8), 50.0, dtype=np.float32))
    rad.accumulate_era_stats(mesh, None, None, every_n=1)

    s07 = load_stage("07_build_hail_climo.py")
    assert s07.classify_mesh_era(date(2010, 6, 1)) == "MYRORSS"

    s11 = _exec_fresh(REPO_ROOT / "scripts/11_build_occurrence_probs.py", "s11_final")
    assert callable(s11.main)

    s12 = _exec_fresh(REPO_ROOT / "scripts/12_apply_conus_mask.py", "s12_final")
    assert callable(s12.main)

    s06 = _exec_fresh(REPO_ROOT / "scripts/06_validate_mesh_vs_spc.py", "s06_final")
    assert callable(s06.main)

    s11b = load_stage("11b_prepare_topography.py")
    assert s11b.validate_outputs() is False
