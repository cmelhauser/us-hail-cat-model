"""Cover remaining ImportError / validation edge branches."""

from __future__ import annotations

import builtins
import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import load_stage


def test_lvs_rasterio_importerror_branches(tmp_path, monkeypatch):
    from scripts.diagnostics import literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "CDF_DIR", tmp_path)
    monkeypatch.setattr(lvs, "STOCH_MAP_DIR", tmp_path)
    # Create one RP file so we don't take the "all missing" skip
    (tmp_path / "rp_00100yr_hail_smooth.tif").write_bytes(b"x")
    (tmp_path / "rp_00010yr_hail_smooth.tif").write_bytes(b"x")
    for rp in getattr(lvs, "RP_YEARS", [10, 100]):
        p = tmp_path / f"rp_{rp:05d}yr_hail_smooth.tif"
        if not p.exists():
            p.write_bytes(b"x")
    (tmp_path / "rp_00100yr_stochastic.tif").write_bytes(b"x")

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rasterio" or name.startswith("rasterio."):
            raise ImportError("no rasterio")
        if name == "scripts._radar_geometry" or name.endswith("_radar_geometry"):
            raise ImportError("no geom")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    r1 = lvs.check_rp_monotonicity()
    assert r1.status == "skip"
    r2 = lvs.check_analytical_vs_stochastic()
    assert r2.status == "skip"
    r3 = lvs.check_rp_ring_energy()
    assert r3.status == "skip"


def test_lvs_empty_rp_maps_and_bootstrap_skips(tmp_path, monkeypatch):
    from scripts.diagnostics import literature_validation_suite as lvs
    import rasterio
    from rasterio.transform import from_origin
    from scripts._config import DX, LAT_MAX, LON_MIN, NCOLS, NROWS

    monkeypatch.setattr(lvs, "CDF_DIR", tmp_path)
    monkeypatch.setattr(lvs, "STOCH_MAP_DIR", tmp_path)
    for name in ("rp_00100yr_hail_smooth.tif", "rp_00100yr_stochastic.tif"):
        path = tmp_path / name
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=NROWS,
            width=NCOLS,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(LON_MIN, LAT_MAX, DX, DX),
        ) as dst:
            dst.write(np.zeros((NROWS, NCOLS), dtype=np.float32), 1)
    r = lvs.check_analytical_vs_stochastic()
    assert r.status == "skip"


def test_stage08_validate_npz_edge_cases(tmp_path, monkeypatch):
    s = load_stage("08_build_event_catalog.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    # missing npz
    assert s.validate_outputs() is False
    # corrupt npz
    (tmp_path / "event_peaks.npz").write_bytes(b"not-npz")
    csv = tmp_path / "event_catalog.csv"
    csv.write_text("event_id,start_date,end_date,duration_days,n_cells,peak_mm\n")
    assert s.validate_outputs() is False

    # valid-looking but mismatched / duplicate ids
    ids = np.array([1, 1, 2], dtype=np.int32)
    np.savez(
        tmp_path / "event_peaks.npz",
        n_events=np.array([2], dtype=np.int32),
        event_ids=ids,
        rows_1=np.array([0], dtype=np.int16),
        cols_1=np.array([0], dtype=np.int16),
        vals_1=np.array([30.0], dtype=np.float32),
        rows_2=np.array([1, 2], dtype=np.int16),
        cols_2=np.array([1], dtype=np.int16),  # length mismatch
        vals_2=np.array([40.0, 41.0], dtype=np.float32),
        rows_bad=np.array([0], dtype=np.int16),
    )
    csv.write_text(
        "event_id,start_date,end_date,duration_days,n_cells,peak_mm\n"
        "1,2015-06-01,2015-06-01,1,1,30\n"
        "2,2015-06-02,2015-06-02,1,1,40\n"
        "3,2015-06-03,2015-06-03,1,1,50\n"
    )
    assert s.validate_outputs() is False


def test_sys_path_insert_for_stages(monkeypatch):
    """Cover `sys.path.insert` lines by loading with repo root absent."""
    root = str(Path(__file__).resolve().parents[1])
    scripts = str(Path(root) / "scripts")
    saved = [p for p in sys.path if p in (root, scripts) or p.endswith("us-hail-cat-model")]
    sys.path[:] = [p for p in sys.path if p not in saved]
    try:
        for name in (
            "10_build_smooth_cdf.py",
            "11_build_occurrence_probs.py",
            "07_build_hail_climo.py",
            "06_validate_mesh_vs_spc.py",
            "12_apply_conus_mask.py",
        ):
            # Clear cached stage module so path insert runs again
            for key in list(sys.modules):
                if key.startswith("stage_") and name.replace(".py", "") in key:
                    del sys.modules[key]
            mod = load_stage(name)
            assert hasattr(mod, "log") or hasattr(mod, "main")
    finally:
        for p in reversed(saved):
            if p not in sys.path:
                sys.path.insert(0, p)
