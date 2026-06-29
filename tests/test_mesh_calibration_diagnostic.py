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
    classify_source,
    corrected_path_for_day,
)


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
