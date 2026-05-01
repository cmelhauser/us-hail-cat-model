import subprocess
import sys
from pathlib import Path


def test_stage14_configured_classes(load_script):
    s = load_script("14_build_vulnerability.py")
    assert "3tab_asphalt_aged" in s.CONSTRUCTION_CLASSES
    assert len(s.HAIL_SIZES_MM) > 100


def test_stage15_has_delta_renderer(load_script):
    s = load_script("15_render_figures.py")
    assert hasattr(s, "render_delta_maps")


def test_run_pipeline_dry_run_only_stage_05():
    root = Path(__file__).resolve().parents[1]
    source = (root / "run_pipeline.py").read_text()
    assert "--skip-ml" in source
    assert "--retrain-models" in source
    assert "05_apply_mesh_bias_correction.py" in source
