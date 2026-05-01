from datetime import date


def test_stage01_block_max(load_script):
    import numpy as np
    s = load_script("01_download_myrorss.py")
    data = np.arange(16, dtype=np.float32).reshape(4, 4)
    out = s.block_max(data, 2)
    assert out.tolist() == [[5, 7], [13, 15]]


def test_stage02_block_max(load_script):
    import numpy as np
    s = load_script("02_download_mrms_mesh.py")
    data = np.array([[1, 9], [4, 2]], dtype=np.float32)
    assert s.block_max(data, 2).shape == (1, 1)
    assert float(s.block_max(data, 2)[0, 0]) == 9.0


def test_iter_dates_inclusive(load_script):
    s = load_script("01_download_myrorss.py")
    days = list(s.iter_dates(date(2020, 1, 1), date(2020, 1, 3)))
    assert [d.day for d in days] == [1, 2, 3]
