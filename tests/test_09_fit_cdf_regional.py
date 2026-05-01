import numpy as np
from conftest import load_stage


def test_stage09_lognormal_fit_returns_finite_values():
    s = load_stage("09_fit_cdf_regional.py")
    mu, sig = s.lmom_fit_lognormal(np.array([10, 20, 30, 40, 50], dtype=np.float32))
    assert np.isfinite(mu)
    assert np.isfinite(sig)
    assert sig > 0


def test_stage09_threshold_selection_returns_positive_threshold(tmp_path, monkeypatch):
    s = load_stage("09_fit_cdf_regional.py")
    monkeypatch.setattr(s, "OUT_DIR", tmp_path)
    monkeypatch.setattr(s, "THRESHOLD_SELECTION_FILE", tmp_path / "threshold_selection.csv")
    rng = np.random.default_rng(1)
    data = 25 + rng.gamma(shape=2.0, scale=15.0, size=200)
    u = s.compute_mrl_and_threshold(data.astype(np.float32), region_id=0)
    assert u > 0
    assert (tmp_path / "threshold_selection.csv").exists()
