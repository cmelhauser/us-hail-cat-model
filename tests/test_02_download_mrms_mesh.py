import numpy as np
from conftest import load_stage


def test_stage02_block_max_shape_and_values():
    s = load_stage("02_download_mrms_mesh.py")
    data = np.array([[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11], [12, 13, 14, 15]], dtype=np.float32)
    out = s.block_max(data, 2)
    assert out.shape == (2, 2)
    assert np.allclose(out, [[5, 7], [13, 15]])
