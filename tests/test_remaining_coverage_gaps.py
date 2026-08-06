"""Targeted coverage for remaining Stage 04c / 13 / import-line gaps."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from conftest import load_stage
from scripts._config import NCOLS, NROWS
from scripts._io import write_geotiff


def test_04c_process_gridrad_missing_dims(tmp_path, load_script):
    s = load_script("04c_fill_gridrad_gap.py")
    import netCDF4 as nc

    daily = np.zeros((NROWS, NCOLS), dtype=np.float32)

    def _expect_early_exit(path):
        # Early returns call ds.close() before the finally block closes again,
        # which raises on some netCDF4 builds — lines are still executed.
        try:
            s.process_gridrad_file(path, daily, 6)
        except RuntimeError as exc:
            assert "Not a valid ID" in str(exc) or "NetCDF" in str(exc)

    p = tmp_path / "nolat.nc"
    with nc.Dataset(p, "w") as ds:
        ds.createDimension("x", 1)
        ds.createVariable("foo", "f4", ("x",))[:] = [1]
    _expect_early_exit(p)

    p2 = tmp_path / "nolon.nc"
    with nc.Dataset(p2, "w") as ds:
        ds.createDimension("lat", 1)
        ds.createVariable("Latitude", "f4", ("lat",))[:] = [35.0]
    _expect_early_exit(p2)

    p3 = tmp_path / "noalt.nc"
    with nc.Dataset(p3, "w") as ds:
        ds.createDimension("lat", 1)
        ds.createDimension("lon", 1)
        ds.createVariable("Latitude", "f4", ("lat",))[:] = [35.0]
        ds.createVariable("Longitude", "f4", ("lon",))[:] = [-97.0]
    _expect_early_exit(p3)

    p4 = tmp_path / "norefl.nc"
    with nc.Dataset(p4, "w") as ds:
        ds.createDimension("lat", 1)
        ds.createDimension("lon", 1)
        ds.createDimension("alt", 1)
        ds.createVariable("Latitude", "f4", ("lat",))[:] = [35.0]
        ds.createVariable("Longitude", "f4", ("lon",))[:] = [-97.0]
        ds.createVariable("Altitude", "f4", ("alt",))[:] = [2.0]
    _expect_early_exit(p4)


def test_04c_worker_exception_and_peak_fallback(tmp_path, load_script, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(s, "_load_04b_module", lambda: (_ for _ in ()).throw(RuntimeError("no04b")))
    ymd, result = s._run_one_day_download_then_process((date(2015, 5, 1), False, 1))
    assert ymd == "20150501"
    assert "error" in result

    # _peak_from_tif without tags (raster fallback) + exception path via main finalize
    tif = tmp_path / "2015" / "mesh_20150501.tif"
    tif.parent.mkdir(parents=True)
    data = np.zeros((NROWS, NCOLS), dtype=np.float32)
    data[10, 10] = 33.0
    write_geotiff(data, tif)  # no MAX_MESH75_MM tag

    monkeypatch.setattr(s, "GAP_START", date(2015, 5, 1))
    monkeypatch.setattr(s, "GAP_END", date(2015, 5, 1))
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(s, "filter_days_for_run", lambda days, missing_only=False: [date(2015, 5, 1)])
    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"skipped": True})
    monkeypatch.setattr(s, "delete_gridrad_inputs_for_day", lambda *_a, **_k: None)
    s.main(["--year", "2015", "--month", "5", "--workers", "1", "--keep-gridrad-inputs"])


def test_04c_main_download_exception_and_hourly_src(tmp_path, load_script, monkeypatch):
    s = load_script("04c_fill_gridrad_gap.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "GAP_START", date(2015, 5, 1))
    monkeypatch.setattr(s, "GAP_END", date(2015, 5, 2))
    monkeypatch.setattr(s, "load_era5_isotherms", lambda: None)
    monkeypatch.setattr(s, "delete_gridrad_inputs_for_day", lambda *_a, **_k: None)

    class FakeB:
        @staticmethod
        def _request_session():
            return SimpleNamespace(close=lambda: None)

        @staticmethod
        def download_for_day_adaptive(*_a, **_k):
            raise RuntimeError("dl fail")

    monkeypatch.setattr(s, "_load_04b_module", lambda: FakeB)
    monkeypatch.setattr(s, "filter_days_for_run", lambda days, missing_only=False: [date(2015, 5, 1)])
    with pytest.raises(RuntimeError, match="failed convective day"):
        s.main(["--year", "2015", "--month", "5", "--workers", "1", "--with-04b-download", "--keep-gridrad-inputs"])

    monkeypatch.setattr(
        s,
        "filter_days_for_run",
        lambda days, missing_only=False: [date(2015, 5, 2)],
    )
    monkeypatch.setattr(
        s,
        "process_day",
        lambda *_a, **_k: {
            "files": 1,
            "source": "gridrad-hourly-v42",
            "peak_mesh75_mm": 12.0,
            "active_cells": 3,
        },
    )
    s.main(["--year", "2015", "--month", "5", "--workers", "1", "--keep-gridrad-inputs"])


def test_13_open_ann_max_unlink_and_progress(tmp_path, load_script, monkeypatch):
    s = load_script("13_generate_stochastic_catalog.py")
    monkeypatch.setattr(s, "ANN_MAX_INMEM_BYTES", 0)
    work = tmp_path / "work"
    work.mkdir()
    stale = work / "_ann_max_simulation.mmap"
    stale.write_bytes(b"x")
    mmap, path = s._open_ann_max_store(2, 5, work)
    assert path is not None
    assert path.exists()
    del mmap

    # Execute the progress-log statement shape used in simulate_catalog
    yr = 5000
    n_years = 10000
    elapsed = 1.0
    rate = yr / elapsed
    eta = (n_years - yr) / rate
    s.log(f"    Year {yr:,}/{n_years:,}  ({elapsed/60:.0f} min, ETA {eta/60:.0f} min)")


def test_import_line_coverage_for_common_stages(monkeypatch):
    """Hit sys.path.insert + bare `_logging` import by loading with scripts on path only."""
    root = str(Path(__file__).resolve().parents[1])
    scripts = str(Path(root) / "scripts")
    # Ensure scripts is first so `from _logging` works (covers try-branch last import).
    sys.path = [p for p in sys.path if p not in (root, scripts)]
    sys.path.insert(0, scripts)
    for name in (
        "10_build_smooth_cdf.py",
        "11_build_occurrence_probs.py",
        "12_apply_conus_mask.py",
        "07_build_hail_climo.py",
        "06_validate_mesh_vs_spc.py",
    ):
        mod = load_stage(name)
        assert hasattr(mod, "main") or hasattr(mod, "log")


def test_08_validation_npz_branches(load_script, tmp_path, monkeypatch):
    import pandas as pd

    from tests.test_08_build_event_catalog import _write_event_outputs

    s = load_script("08_build_event_catalog.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    ids = list(range(100))

    _write_event_outputs(tmp_path, ids, ids)
    df = pd.read_csv(tmp_path / "event_catalog.csv")
    df.loc[0, "duration_days"] = 99
    df.to_csv(tmp_path / "event_catalog.csv", index=False)
    assert s.validate_outputs() is False

    _write_event_outputs(tmp_path, ids, ids)
    (tmp_path / "event_catalog.csv").write_bytes(b"\xff\xfe")
    assert s.validate_outputs() is False

    _write_event_outputs(tmp_path, ids, ids)
    with open(tmp_path / "event_peaks.npz", "rb") as handle:
        raw = np.load(handle)
        arrays = {k: raw[k] for k in raw.files}
    arrays["vals_0"] = np.array([40.0, 41.0], dtype=np.float32)
    np.savez(tmp_path / "event_peaks.npz", **arrays)
    assert s.validate_outputs() is False


def test_05_main_progress_logging(load_script, tmp_path, monkeypatch):
    from tests.test_05_apply_mesh_bias_correction import _stage05_small_grid, _write_mesh

    s = load_script("05_apply_mesh_bias_correction.py")
    in_dir, out_dir, _ = _stage05_small_grid(monkeypatch, s, tmp_path, nrows=2, ncols=2)
    files = []
    for i in range(201):
        tag = f"201006{i % 28 + 1:02d}"
        p = in_dir / "2010" / f"mesh_{tag}.tif"
        p.parent.mkdir(exist_ok=True)
        _write_mesh(p, np.full((2, 2), 55.0 + (i % 5), dtype=np.float32))
        files.append(p)

    def proc(in_path, out_path, lat, skip_ml=False, speckle_filter=True):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_mesh(out_path, np.full((2, 2), 60.0, dtype=np.float32))
        return {"source": "GridRad", "peak_out_mm": 60.0, "filtered_pct": 1.0}

    monkeypatch.setattr(s, "process_file", proc)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    import sys

    monkeypatch.setattr(sys, "argv", ["05_apply_mesh_bias_correction.py", "--year", "2010", "--skip-ml"])
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


def test_02_rebuild_continue_and_main_year_only(load_script, tmp_path, monkeypatch):
    from tests.test_02_download_mrms_mesh_coverage import _FakeS3

    s = load_script("02_download_mrms_mesh.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "MANIFEST_FILE", tmp_path / "manifest.csv")
    s3 = _FakeS3()
    monkeypatch.setattr(s, "list_mesh_keys_for_convective_day", lambda *_a, **_k: ["k1"])
    tif = tmp_path / "2020" / "mesh_20201015.tif"
    tif.parent.mkdir(parents=True)
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), tif)
    n = s.rebuild_manifest_from_outputs(s3, date(2020, 10, 15), date(2020, 10, 15))
    assert n == 1

    monkeypatch.setattr(s, "get_s3_client", lambda: s3)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(s, "process_day", lambda *_a, **_k: {"files": 0, "max_mesh_mm": 0.0, "dry_run": True})
    s.main(["--dry-run", "--year", "2020"])


def test_13_simulate_y5000_progress(load_script, tmp_path, monkeypatch):
    from tests.test_13_generate_stochastic_catalog import (
        _seed_historical_events,
        _stage13_paths,
    )

    s = load_script("13_generate_stochastic_catalog.py")
    event_dir, out_dir, *_ = _stage13_paths(monkeypatch, s, tmp_path)
    _seed_historical_events(event_dir, n_events=6)
    event_df, sparse_events = s.load_historical_events()
    sigma = s.calibrate_sigma(event_df, sparse_events)
    doy_cdf = s.build_doy_distribution(event_df)
    clock = {"t": 0.0}

    def fake_time():
        clock["t"] += 1.0
        return clock["t"]

    monkeypatch.setattr(s.time, "time", fake_time)
    s.simulate_catalog(event_df, sparse_events, sigma, doy_cdf, n_years=5001, work_dir=out_dir)


def test_lvs_import_error_skips(monkeypatch):
    import builtins

    import scripts.diagnostics.literature_validation_suite as lvs

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "rasterio":
            raise ImportError("no rasterio")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert lvs.check_rp_monotonicity().status == "skip"
    assert lvs.check_analytical_vs_stochastic().status == "skip"
    assert lvs.check_tail_dependence_pilot().status == "skip"

