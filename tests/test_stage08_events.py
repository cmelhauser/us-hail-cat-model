from datetime import date

import numpy as np

from conftest import dense_footprint_to_cells, load_stage


def test_event_group_rejects_intensity_jump():
    s = load_stage("08_build_event_catalog.py")
    fp1 = np.zeros((40, 40), dtype=bool)
    fp1[10, 10] = True
    fp2 = np.zeros((40, 40), dtype=bool)
    fp2[10, 11] = True
    peak1 = fp1.astype(np.float32) * 30
    peak2 = fp2.astype(np.float32) * 35
    dates = [date(2020, 1, 1), date(2020, 1, 2)]
    cells = [
        dense_footprint_to_cells(fp1, peak1),
        dense_footprint_to_cells(fp2, peak2),
    ]
    groups = s.group_events(dates, cells)
    assert groups == [[0, 1]]

    peak4 = fp2.astype(np.float32) * 200  # >3x intensity jump rejects merge
    cells_jump = [
        dense_footprint_to_cells(fp1, peak1),
        dense_footprint_to_cells(fp2, peak4),
    ]
    groups = s.group_events(dates, cells_jump)
    assert groups == [[0], [1]]


def test_physical_merge_returns_diagnostics():
    s = load_stage("08_build_event_catalog.py")
    fp1 = np.zeros((40, 40), dtype=bool)
    fp1[10, 10] = True
    fp2 = np.zeros((40, 40), dtype=bool)
    fp2[10, 11] = True
    peak1 = fp1.astype(np.float32) * 30
    peak2 = fp2.astype(np.float32) * 35
    dates = [date(2020, 1, 1), date(2020, 1, 2)]
    cells = [
        dense_footprint_to_cells(fp1, peak1),
        dense_footprint_to_cells(fp2, peak2),
    ]
    ok, speed, ratio = s.physically_coherent_merge(dates, cells, 0, 1)
    assert ok is True
    assert speed >= 0
    assert ratio >= 1
