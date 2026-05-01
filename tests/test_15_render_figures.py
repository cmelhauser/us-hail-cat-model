from pathlib import Path
from conftest import load_stage


def test_stage15_validate_outputs_detects_missing_figures(tmp_path, monkeypatch):
    s = load_stage("15_render_figures.py")
    monkeypatch.setattr(s, "FIG_HIST", tmp_path / "historical")
    monkeypatch.setattr(s, "FIG_STOCH", tmp_path / "stochastic")
    monkeypatch.setattr(s, "FIG_ANAL", tmp_path / "analysis")
    assert s.validate_outputs() is False
