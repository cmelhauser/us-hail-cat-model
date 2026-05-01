import numpy as np
from conftest import load_stage


def test_stage01_block_max_uses_maximum_not_sum():
    s = load_stage("01_download_myrorss.py")
    data = np.arange(16, dtype=np.float32).reshape(4, 4)
    out = s.block_max(data, 2)
    assert out.tolist() == [[5.0, 7.0], [13.0, 15.0]]


def test_stage01_iter_dates_inclusive():
    from datetime import date
    s = load_stage("01_download_myrorss.py")
    days = list(s.iter_dates(date(2000, 1, 1), date(2000, 1, 3)))
    assert [d.isoformat() for d in days] == ["2000-01-01", "2000-01-02", "2000-01-03"]
