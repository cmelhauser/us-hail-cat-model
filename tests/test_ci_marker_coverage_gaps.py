"""Cover the last CI-only gaps when slow/integration/regression tests are excluded."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def test_stage04b_severe_catalog_has_convective_data_calls_planner(load_script, monkeypatch):
    s = load_script("04b_download_gridrad.py")
    calls = {}

    def fake_plan(session, day, *, hourly, severe, catalog_timeout):
        calls["args"] = (hourly, severe, catalog_timeout, day)
        return ["x.nc"]

    monkeypatch.setattr(s, "plan_downloads_for_day", fake_plan)
    assert s.severe_catalog_has_convective_data(
        object(), date(2015, 5, 20), catalog_timeout=(1.0, 2.0)
    ) is True
    assert calls["args"][0] is False
    assert calls["args"][1] is True

    monkeypatch.setattr(s, "plan_downloads_for_day", lambda *_a, **_k: [])
    assert s.severe_catalog_has_convective_data(
        object(), date(2015, 5, 20), catalog_timeout=(1.0, 2.0)
    ) is False


def test_lvs_tail_dependence_rasterio_import_error_and_few_cells(tmp_path, monkeypatch):
    from scripts.diagnostics import literature_validation_suite as lvs

    monkeypatch.setattr(lvs, "_preferred_mesh_dir", lambda: tmp_path / "mesh")
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rasterio":
            raise ImportError("forced")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    res = lvs.check_tail_dependence_pilot()
    assert res.status == "skip"
    assert "rasterio unavailable" in res.message

    monkeypatch.setattr(builtins, "__import__", real_import)
    amax = np.zeros((10, 10), dtype=np.float32)
    amax[0, 0] = 40.0
    monkeypatch.setattr(lvs, "_pooled_annual_max", lambda *_a, **_k: amax)
    res2 = lvs.check_tail_dependence_pilot()
    assert res2.status == "skip"
    assert "Too few cells" in res2.message


def test_pnas_collect_metrics_counts_corrected_rasters(tmp_path, monkeypatch):
    import scripts.diagnostics.render_pnas_article_figures as rpf

    corr = tmp_path / "corrected"
    year = corr / "2018"
    year.mkdir(parents=True)
    (year / "mesh_20180601.tif").write_bytes(b"x")
    (year / "mesh_20180602.tif").write_bytes(b"x")
    monkeypatch.setattr(rpf, "CORRECTED_DIR", corr)
    monkeypatch.setattr(rpf, "MANIFESTS", {})
    monkeypatch.setattr(rpf, "HAIL_CLIM_DIR", tmp_path / "clim")
    monkeypatch.setattr(rpf, "VALID_DIR", tmp_path / "validation")
    monkeypatch.setattr(rpf, "STOCH_MAP_DIR", tmp_path / "maps")
    monkeypatch.setattr(rpf, "STOCH_PET_DIR", tmp_path / "pet")
    monkeypatch.setattr(rpf, "STOCH_CATALOG", tmp_path / "cat.parquet")
    monkeypatch.setattr(rpf, "_validation_metrics", lambda: {})
    monkeypatch.setattr(rpf, "_stochastic_metrics", lambda: {"complete": False})

    metrics = rpf.collect_metrics(pd.DataFrame(), {})
    assert metrics["total_daily_rasters"] == 2
