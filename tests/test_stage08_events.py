from datetime import date


def test_event_group_rejects_intensity_jump(load_script):
    import numpy as np
    s = load_script("08_build_event_catalog.py")
    fp1 = np.zeros((40, 40), dtype=bool); fp1[10, 10] = True
    fp2 = np.zeros((40, 40), dtype=bool); fp2[10, 11] = True
    peak1 = fp1.astype(np.float32) * 30
    peak2 = fp2.astype(np.float32) * 35
    groups = s.group_events([date(2020,1,1), date(2020,1,2)], [fp1, fp2], [peak1, peak2])
    assert groups == [[0, 1]]

    peak4 = fp2.astype(np.float32) * 200  # >3x intensity jump rejects
    groups = s.group_events([date(2020,1,1), date(2020,1,2)], [fp1, fp2], [peak1, peak4])
    assert groups == [[0], [1]]


def test_physical_merge_returns_diagnostics(load_script):
    import numpy as np
    s = load_script("08_build_event_catalog.py")
    fp1 = np.zeros((40, 40), dtype=bool); fp1[10, 10] = True
    fp2 = np.zeros((40, 40), dtype=bool); fp2[10, 11] = True
    peak1 = fp1.astype(np.float32) * 30
    peak2 = fp2.astype(np.float32) * 35
    ok, speed, ratio = s.physically_coherent_merge([date(2020,1,1), date(2020,1,2)], [fp1, fp2], [peak1, peak2], 0, 1)
    assert ok is True
    assert speed >= 0
    assert ratio >= 1
