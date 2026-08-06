"""Surgical coverage for the last ~25 uncovered scripts/ lines."""

from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import requests

from conftest import load_stage
from scripts._io import write_geotiff


def test_09_no_candidate_plot_skip_and_xi_ge_one(tmp_path, monkeypatch):
    s = load_stage("09_fit_cdf_regional.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "THRESHOLD_SELECTION_FILE", tmp_path / "t.csv")
    monkeypatch.setattr(s, "THRESHOLD_DIAGNOSTICS", [])
    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 10_000)
    x = np.linspace(55, 130, 40, dtype=np.float64)
    assert s.compute_mrl_and_threshold(x, 0) == s.DEFAULT_GPD_THRESHOLD_MM

    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 5)
    monkeypatch.setattr(s, "THRESHOLD_DIAGNOSTICS", [])
    with patch("matplotlib.figure.Figure.savefig", side_effect=OSError("disk")):
        s.compute_mrl_and_threshold(x, 1)

    monkeypatch.setattr(s, "NROWS", 4)
    monkeypatch.setattr(s, "NCOLS", 4)
    monkeypatch.setattr(s, "MIN_YEARS_FOR_FIT", 5)
    monkeypatch.setattr(s, "MIN_EXCEEDANCES_GPD", 2)
    monkeypatch.setattr(s, "MIN_REGION_EXCEEDANCES", 1)
    annual = np.zeros((10, 4, 4), dtype=np.float32)
    annual[0:2, 0, 0] = [60.0, 70.0]  # only 2 years → continue @ 517
    annual[:, 0, 1] = np.linspace(55, 95, 10)
    region_map = np.full((4, 4), -1, dtype=np.int8)
    region_map[0, 0] = 0
    region_map[0, 1] = 0
    monkeypatch.setattr(s, "compute_mrl_and_threshold", lambda *_a, **_k: 50.0)
    monkeypatch.setattr(s, "lmom_fit_lognormal", lambda nz: (np.log(40.0), 0.25))
    monkeypatch.setattr(s, "lmom_fit_gpd", lambda _x: (1.5, 10.0))
    # Bypass ξ clip so reg_xi >= 1 hits line 539
    real_clip = np.clip

    def clip_pass(a, a_min, a_max):
        if a_min == -0.5 and a_max == 0.5:
            return a
        return real_clip(a, a_min, a_max)

    monkeypatch.setattr(s.np, "clip", clip_pass)
    s.fit_regional_gpd(annual, region_map, 1)


def test_04b_plan_404_tmp_and_severe_cover(tmp_path, monkeypatch):
    s = load_stage("04b_download_gridrad.py")
    day = date(2015, 5, 1)
    monkeypatch.setattr(s, "_sleep_backoff", lambda *_a, **_k: None)

    # 318: non-retryable HTTPError raised immediately
    class R400:
        status_code = 400

        def raise_for_status(self):
            err = requests.HTTPError("bad request")
            err.response = self
            raise err

    with pytest.raises(requests.HTTPError):
        s._catalog_get(types.SimpleNamespace(get=lambda *a, **k: R400()), "http://x", timeout=(1.0, 1.0))

    monkeypatch.setattr(
        s,
        "list_day_catalog_files",
        lambda *_a, **_k: ["junk_no_timestamp.nc", "nexrad_3d_v3_1_20140101T120000Z.nc"],
    )
    monkeypatch.setattr(s, "_hourly_dataset_ids", lambda *_a, **_k: [s.DS_HOURLY])
    monkeypatch.setattr(s, "GRIDRAD_DIR", tmp_path / "gr")
    monkeypatch.setattr(s, "GRIDRAD_SEV_DIR", tmp_path / "sev")
    items = s.plan_downloads_for_day(
        types.SimpleNamespace(), day, hourly=True, severe=False, catalog_timeout=(1.0, 1.0),
    )
    assert items == []

    item = s.DownloadItem(
        dsid=s.DS_HOURLY,
        convective_day=day,
        catalog_day=day,
        filename="f.nc",
        url="http://example.com/f.nc",
        out_path=tmp_path / "out" / "f.nc",
    )
    monkeypatch.setattr(s, "_auth_params", lambda: {})

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

    class Sess:
        def get(self, *a, **k):
            # Recreate tmp after per-attempt unlink so 478 runs
            tmp = item.out_path.with_suffix(item.out_path.suffix + ".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(b"partial")
            return Resp404()

    assert s._download_one(Sess(), item, connect_timeout=1.0, read_timeout=1.0)[1] == "missing"

    # First staging check False (skip local early-return); after severe download True → 673
    n = {"c": 0}

    def covers(_d):
        n["c"] += 1
        return n["c"] >= 2

    monkeypatch.setattr(s, "_severe_staging_covers_day", covers)
    monkeypatch.setattr(s, "severe_catalog_has_convective_data", lambda *_a, **_k: True)
    monkeypatch.setattr(
        s, "download_for_day", lambda *_a, **_k: {"downloaded": 1, "skipped": 0, "missing": 0, "errors": 0}
    )
    out = s.download_for_day_adaptive(
        types.SimpleNamespace(),
        day,
        catalog_timeout=(1.0, 1.0),
        connect_timeout=1.0,
        read_timeout=1.0,
        max_workers=1,
    )
    assert out["source_mode"] == "severe-only"


def test_05_overlap_unreadable_and_empty(tmp_path, monkeypatch):
    from tests.test_05_apply_mesh_bias_correction import _write_mesh

    s = load_stage("05_apply_mesh_bias_correction.py")
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    monkeypatch.setattr(s, "IN_DIR", in_dir)
    monkeypatch.setattr(s, "CAL_DIR", tmp_path / "cal")
    monkeypatch.setattr(s, "NROWS", 2)
    monkeypatch.setattr(s, "NCOLS", 2)
    monkeypatch.setattr(s, "load_gridrad_days", lambda: {"20100601"})
    # Overlap loop is OVERLAP_START_YEAR..END (2005–2011), not GridRad calib years
    ydir = in_dir / "2010"
    ydir.mkdir()
    _write_mesh(ydir / "mesh_20100601.tif", np.full((2, 2), 45.0, dtype=np.float32))
    (ydir / "mesh_20100602.tif").write_bytes(b"not-tif")
    _write_mesh(ydir / "mesh_20100603.tif", np.zeros((2, 2), dtype=np.float32))
    s.build_cross_calibration()


def test_04a_cost_licence_equal_temp(tmp_path, monkeypatch):
    s = load_stage("04a_download_era5_isotherms.py")
    monkeypatch.setattr(s, "ERA5_DIR", tmp_path)
    monkeypatch.setattr(s, "CLIM_YEARS", ["1992"])
    monkeypatch.setattr(s, "MONTHS", ["01", "02"])
    monkeypatch.setattr(s, "OUT_FILE", tmp_path / "iso.nc")

    yearly = tmp_path / "pressure_chunks" / "era5_monthly_temp_plevels_conus_1992.nc"
    yearly.parent.mkdir(parents=True, exist_ok=True)
    yearly.write_bytes(b"")  # empty → not treated as existing chunk; unlinked on cost fallback

    class CostClient:
        def retrieve(self, dataset, request, path):
            if len(request["month"]) > 1:
                raise Exception("cost limits exceeded")
            Path(path).write_bytes(b"ok" * 200)

    sys.modules["cdsapi"] = types.SimpleNamespace(Client=CostClient)
    files = s.download_era5_temperature()
    assert len(files) >= 1
    monthlies = list((tmp_path / "pressure_chunks").glob("era5_monthly_temp_plevels_conus_1992_*.nc"))
    assert monthlies
    assert not yearly.exists()

    # 172: non-cost yearly failure re-raises
    class BoomClient:
        def retrieve(self, *a, **k):
            raise RuntimeError("CDS network exploded")

    sys.modules["cdsapi"] = types.SimpleNamespace(Client=BoomClient)
    raw = tmp_path / "era5_monthly_temp_plevels_conus.nc"
    if raw.exists():
        raw.unlink()
    # Clear monthly cache so yearly path is attempted
    for p in (tmp_path / "pressure_chunks").glob("*.nc"):
        p.unlink()
    with pytest.raises(RuntimeError, match="network exploded"):
        s.download_era5_temperature()

    # 213: non-licence surface failure re-raises
    class OtherClient:
        def retrieve(self, *a, **k):
            raise RuntimeError("CDS queue timeout")

    sys.modules["cdsapi"] = types.SimpleNamespace(Client=OtherClient)
    sfc = tmp_path / "era5_surface_geopotential_conus.nc"
    if sfc.exists():
        sfc.unlink()
    with pytest.raises(RuntimeError, match="queue timeout"):
        s.download_era5_surface_geopotential()

    # Equal adjacent temps → frac = 0.5 (335-336)
    import xarray as xr

    temp = np.zeros((12, 4, 1, 1), dtype=np.float32)
    heights = np.zeros((12, 4, 1, 1), dtype=np.float32)
    temp[0, :, 0, 0] = [253.15, 253.15, 273.15, 273.15]
    heights[0, :, 0, 0] = [8000.0, 6000.0, 4000.0, 2000.0]
    monkeypatch.setattr(
        s,
        "_load_pressure_climatology",
        lambda _f: (temp, heights, np.array([40.0]), np.array([-100.0]), np.ones(12, dtype=np.int32)),
    )
    sfc_path = tmp_path / "sfc.nc"
    xr.Dataset(
        {"z": (("latitude", "longitude"), np.array([[500.0]], dtype=np.float32))},
        coords={"latitude": [40.0], "longitude": [-100.0]},
    ).to_netcdf(sfc_path)
    s.compute_isotherm_heights([tmp_path / "p.nc"], sfc_path)


def test_08_no_hit_and_count_mismatch(tmp_path, monkeypatch):
    s = load_stage("08_build_event_catalog.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(s, "IN_DIR", tmp_path / "in")
    (tmp_path / "out").mkdir()
    (tmp_path / "in" / "2015").mkdir(parents=True)
    # Invalid calendar date in stem → ValueError → continue @ 102-103
    from scripts._config import NCOLS, NROWS

    bad = tmp_path / "in" / "2015" / "mesh_20151399.tif"
    write_geotiff(np.zeros((NROWS, NCOLS), dtype=np.float32), bad)
    dates, cells = s.load_daily_data()
    assert dates == []

    # Bbox overlaps but no cell within buffer → final return False @ 164
    r1 = np.array([0, 10], dtype=np.int16)
    c1 = np.array([0, 10], dtype=np.int16)
    r2 = np.array([2], dtype=np.int16)
    c2 = np.array([8], dtype=np.int16)
    assert s.footprints_overlap_sparse(r1, c1, r2, c2, buffer=2) is False

    # Same id set, different lengths (duplicates in CSV) → 503
    ids = list(range(1, 101))
    csv_lines = ["event_id,peak_hail_mm,duration_days"]
    for i in ids:
        csv_lines.append(f"{i},30.0,1")
    csv_lines.append("1,30.0,1")  # duplicate → len mismatch vs unique NPZ
    (tmp_path / "out" / "event_catalog.csv").write_text("\n".join(csv_lines) + "\n")
    arrays = {
        "n_events": np.array([100], dtype=np.int32),
        "event_ids": np.array(ids, dtype=np.int32),
    }
    for i in ids:
        arrays[f"rows_{i}"] = np.array([0], dtype=np.int16)
        arrays[f"cols_{i}"] = np.array([0], dtype=np.int16)
        arrays[f"vals_{i}"] = np.array([30.0], dtype=np.float32)
    np.savez(tmp_path / "out" / "event_peaks.npz", **arrays)
    assert s.validate_outputs() is False


def test_13_empty_year_range_and_streamed_except(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from tests.test_13_generate_stochastic_catalog import _stage13_paths

    s = load_stage("13_generate_stochastic_catalog.py")
    _event_dir, _out, cat_dir, map_dir, pet_dir, _mask = _stage13_paths(monkeypatch, s, tmp_path)
    monkeypatch.setattr(s, "RP_YEARS", [10])
    manifest = cat_dir / "stochastic_catalog_manifest.json"
    manifest.write_text(
        f'{{"n_years": {s.N_SIM_YEARS}, "status": "complete", '
        f'"seed": {s.RNG_SEED}, "model_version": "{s.MODEL_VERSION}"}}'
    )
    (map_dir / "rp_00010yr_stochastic.tif").touch()
    (pet_dir / "pet_occurrence.csv").touch()
    (pet_dir / "pet_aggregate.csv").touch()

    # Use required catalog columns so validation reaches the sim_year checks
    from scripts._config import N_SIM_YEARS as _N

    # Peek required columns from stage
    req = list(s.CATALOG_REQUIRED_COLUMNS)
    base = {c: pa.array([0 if "year" in c or "idx" in c or "id" in c or "doy" in c or "cells" in c else 1.0]) for c in req}
    if "sim_year" in base:
        base["sim_year"] = pa.array([0], type=pa.int32())
    cat = cat_dir / "stochastic_event_summary.parquet"
    pq.write_table(pa.table(base), cat)

    real_pf = pq.ParquetFile

    class EmptyPF:
        def __init__(self, path):
            real = real_pf(path)
            self.metadata = real.metadata
            self.schema_arrow = real.schema_arrow

        def read(self, columns=None):
            if columns == ["sim_year"]:
                return pa.table({"sim_year": pa.array([], type=pa.int32())})
            return real_pf(cat).read(columns=columns)

    monkeypatch.setattr(pq, "ParquetFile", EmptyPF)
    assert s.validate_outputs() is False

    class RangePF2:
        def __init__(self, path):
            real = real_pf(path)
            self.metadata = real.metadata
            self.schema_arrow = real.schema_arrow

        def read(self, columns=None):
            if columns == ["sim_year"]:
                return pa.table({"sim_year": pa.array([-1, 999999], type=pa.int32())})
            return real_pf(cat).read(columns=columns)

    monkeypatch.setattr(pq, "ParquetFile", RangePF2)
    assert s.validate_outputs() is False

    # Streamed parquet except @ 662-663: empty stoch_df, catalog exists, ParquetFile raises
    stream_path = cat_dir / "stochastic_event_summary.parquet"

    def fake_sim(*_a, **kwargs):
        cp = kwargs.get("catalog_path")
        if cp is not None:
            pq.write_table(pa.table(base), cp)
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

    class BoomPF:
        def __init__(self, *a, **k):
            raise OSError("corrupt parquet")

    monkeypatch.setattr(pq, "ParquetFile", BoomPF)
    monkeypatch.setattr(s, "simulate_catalog", fake_sim)
    monkeypatch.setattr(s, "write_geotiff", lambda arr, path, **_kw: Path(path).write_bytes(b"tif"))
    monkeypatch.setattr(s, "load_historical_events", lambda: (pd.DataFrame(), {}))
    monkeypatch.setattr(s, "calibrate_sigma", lambda *_a, **_k: 0.2)
    monkeypatch.setattr(s, "build_doy_distribution", lambda *_a, **_k: np.ones(366) / 366)
    monkeypatch.setattr(s, "compute_empirical_rps", lambda *a, **k: {10: np.zeros((2, 2), dtype=np.float32)})
    monkeypatch.setattr(s, "load_conus_mask", lambda: None)
    monkeypatch.setattr(
        s,
        "build_pet",
        lambda *a, **k: (
            pd.DataFrame({"x": [1]}),
            pd.DataFrame({"x": [1]}),
        ),
    )
    monkeypatch.setattr(s, "write_catalog_manifest", lambda **k: None)
    monkeypatch.setattr(s, "validate_outputs", lambda: True)
    monkeypatch.setattr(sys, "argv", ["13_generate_stochastic_catalog.py", "--n-years", "2"])
    if stream_path.exists():
        stream_path.unlink()
    with pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 0


def test_radar_no_active_guard():
    from scripts._radar_geometry import remove_persistent_range_artifacts

    quiet = np.full((8, 8), 1.0, dtype=np.float32)
    site = np.zeros((8, 8), dtype=np.int16)
    rng = np.full((8, 8), 50.0, dtype=np.float32)
    out, n = remove_persistent_range_artifacts(
        quiet,
        site,
        rng,
        history=np.full((6, 8, 8), 10.0, dtype=np.float32),
        min_history_days=3,
        active_mm=5.0,
    )
    assert n == 0 and out.shape == (8, 8)
