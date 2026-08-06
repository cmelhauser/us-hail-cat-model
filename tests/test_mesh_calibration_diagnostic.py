"""Tests for raw vs Stage 05 calibration diagnostics."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from scripts.diagnostics.summarize_mesh_daily_peaks import (
    build_calibration_peaks_df,
    build_calibration_percentile_table,
    build_percentile_table,
    classify_source,
    corrected_path_for_day,
    iter_mesh_tifs,
    peak_from_tif,
    plot_calibration_ecdf_panel,
    plot_ecdf_panel,
    scan_mesh_peaks,
    write_calibration_outputs,
)
from tests._diagnostics_fixtures import seed_mesh_days, write_mesh_tif


def test_classify_source_eras():
    assert classify_source(date(2010, 6, 1)) == "MYRORSS"
    assert classify_source(date(2015, 6, 1)) == "GridRad"
    assert classify_source(date(2021, 6, 1)) == "MRMS"


def test_corrected_path_for_day():
    root = Path("/data/mesh_0.05deg_corrected")
    assert corrected_path_for_day(root, date(2013, 7, 4)) == root / "2013" / "mesh_20130704.tif"


def _write_peak_tif(path: Path, peak: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.zeros((4, 4), dtype=np.float32)
    arr[1, 1] = peak
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "width": 4,
        "height": 4,
        "crs": "EPSG:4326",
        "transform": from_origin(-100.0, 40.0, 0.05, 0.05),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def test_build_calibration_peaks_df_pairs_by_date(tmp_path: Path):
    raw_dir = tmp_path / "mesh_0.05deg"
    corr_dir = tmp_path / "mesh_0.05deg_corrected"
    day = date(2013, 5, 20)
    raw_path = raw_dir / "2013" / "mesh_20130520.tif"
    corr_path = corrected_path_for_day(corr_dir, day)
    _write_peak_tif(raw_path, 40.0)
    _write_peak_tif(corr_path, 55.0)

    raw_df = pd.DataFrame([{
        "date": day,
        "month": day.month,
        "source": "GridRad",
        "peak_mm": 40.0,
        "active_cells": 1,
        "path": str(raw_path),
    }])

    cal_df = build_calibration_peaks_df(raw_df, corr_dir)
    assert len(cal_df) == 1
    row = cal_df.iloc[0]
    assert row["peak_raw_mm"] == pytest.approx(40.0)
    assert row["peak_cal_mm"] == pytest.approx(55.0)
    assert row["delta_mm"] == pytest.approx(15.0)


def test_build_calibration_percentile_table():
    cal_df = pd.DataFrame([
        {"source": "MYRORSS", "peak_raw_mm": 20.0, "peak_cal_mm": 30.0},
        {"source": "MYRORSS", "peak_raw_mm": 40.0, "peak_cal_mm": 50.0},
        {"source": "GridRad", "peak_raw_mm": 10.0, "peak_cal_mm": 12.0},
    ])
    table = build_calibration_percentile_table(cal_df, subset="all_months")
    myr = table.loc[table["source"] == "MYRORSS"].iloc[0]
    assert myr["n_hail_days"] == 2
    assert myr["mean_raw_mm"] == pytest.approx(30.0)
    assert myr["mean_cal_mm"] == pytest.approx(40.0)


def test_peak_from_tif_tag_and_raster(tmp_path: Path):
    tagged = tmp_path / "tagged.tif"
    write_mesh_tif(tagged, peak=99.0, tags={"MAX_MESH75_MM": "77.0", "ACTIVE_CELLS": "3"})
    peak, active, src = peak_from_tif(tagged, prefer_tags=True)
    assert peak == 77.0
    assert active == 3
    assert src == "tag"

    raw = tmp_path / "raw.tif"
    write_mesh_tif(raw, peak=44.0)
    peak2, active2, src2 = peak_from_tif(raw, prefer_tags=False)
    assert peak2 == pytest.approx(44.0)
    assert active2 == 1
    assert src2 == "raster"


def test_scan_mesh_peaks_and_percentiles(tmp_path: Path):
    seed_mesh_days(tmp_path, [date(2010, 6, 1), date(2015, 5, 20)], peak=35.0)
    df = scan_mesh_peaks(tmp_path, d_min=None, d_max=None)
    assert len(df) == 2
    table = build_percentile_table(df, subset="all_months")
    assert table.iloc[0]["n_hail_days"] >= 1
    assert list(iter_mesh_tifs(tmp_path, date(2014, 1, 1), None))


def test_plot_panels_and_write_calibration(tmp_path: Path):
    import matplotlib.pyplot as plt

    raw_df = pd.DataFrame(
        [
            {"date": date(2010, 6, 1), "month": 6, "source": "MYRORSS", "peak_mm": 20.0},
            {"date": date(2015, 5, 20), "month": 5, "source": "GridRad", "peak_mm": 40.0},
        ]
    )
    cal_df = pd.DataFrame(
        [
            {"source": "MYRORSS", "peak_raw_mm": 20.0, "peak_cal_mm": 30.0, "month": 5},
            {"source": "GridRad", "peak_raw_mm": 40.0, "peak_cal_mm": 45.0, "month": 6},
        ]
    )
    fig, ax = plt.subplots()
    plot_ecdf_panel(ax, raw_df, title="t", hail_only=True)
    plt.close(fig)

    fig, ax = plt.subplots()
    plot_calibration_ecdf_panel(ax, cal_df, title="cal", hail_only=True)
    plt.close(fig)

    fig, ax = plt.subplots()
    empty_cal = pd.DataFrame(columns=["source", "peak_raw_mm", "peak_cal_mm", "month"])
    plot_calibration_ecdf_panel(ax, empty_cal, title="empty", hail_only=True)
    plt.close(fig)

    paths = write_calibration_outputs(cal_df, tmp_path, hail_only=True)
    assert len(paths) == 3


def test_main_summarize_mesh(tmp_path: Path, monkeypatch):
    import sys

    import scripts.diagnostics.summarize_mesh_daily_peaks as smp

    mesh = tmp_path / "mesh"
    corr = tmp_path / "corr"
    out = tmp_path / "out"
    seed_mesh_days(mesh, [date(2010, 6, 1), date(2015, 5, 20)], peak=40.0)
    seed_mesh_days(corr, [date(2010, 6, 1), date(2015, 5, 20)], peak=55.0)
    monkeypatch.setattr(smp.sys, "argv", [
        "summarize_mesh_daily_peaks.py",
        "--mesh-dir", str(mesh),
        "--corrected-dir", str(corr),
        "--out-dir", str(out),
    ])
    smp.main()
    assert (out / "mesh_daily_peaks.csv").exists()
    assert (out / "mesh_calibration_peaks.csv").exists()


def test_scan_skips_bad_tif(tmp_path: Path, monkeypatch, capsys):
    import sys

    import scripts.diagnostics.summarize_mesh_daily_peaks as smp

    bad = tmp_path / "mesh_20100601.tif"
    bad.write_bytes(b"not-a-tif")
    df = scan_mesh_peaks(tmp_path, d_min=None, d_max=None)
    assert df.empty
    assert "WARN skip" in capsys.readouterr().out

    monkeypatch.setattr(smp.sys, "argv", [
        "summarize_mesh_daily_peaks.py",
        "--mesh-dir", str(tmp_path / "empty"),
    ])
    with pytest.raises(SystemExit):
        smp.main()


def test_main_no_corrected_pairing(tmp_path: Path, monkeypatch, capsys):
    import sys

    import scripts.diagnostics.summarize_mesh_daily_peaks as smp

    mesh = tmp_path / "mesh"
    out = tmp_path / "out"
    seed_mesh_days(mesh, [date(2010, 6, 1)], peak=40.0)
    monkeypatch.setattr(smp.sys, "argv", [
        "summarize_mesh_daily_peaks.py",
        "--mesh-dir", str(mesh),
        "--corrected-dir", str(tmp_path / "no_corr"),
        "--out-dir", str(out),
        "--skip-calibration",
        "--all-days",
    ])
    smp.main()
    assert (out / "mesh_daily_peaks.csv").exists()
    assert "No paired corrected" not in capsys.readouterr().out


def test_build_calibration_skips_missing_and_bad(tmp_path: Path, capsys):
    raw_df = pd.DataFrame(
        [
            {
                "date": date(2010, 6, 1),
                "month": 6,
                "source": "MYRORSS",
                "peak_mm": 40.0,
                "active_cells": 1,
                "path": "raw.tif",
            }
        ]
    )
    corr = tmp_path / "corr"
    cal_df = build_calibration_peaks_df(raw_df, corr)
    assert cal_df.empty

    corr_day = corr / "2010" / "mesh_20100601.tif"
    corr_day.parent.mkdir(parents=True)
    corr_day.write_bytes(b"bad")
    cal_df2 = build_calibration_peaks_df(raw_df, corr)
    assert cal_df2.empty
    assert "WARN skip corrected" in capsys.readouterr().out
