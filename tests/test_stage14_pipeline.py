import subprocess
import sys
from pathlib import Path


def test_stage14_has_delta_renderer(load_script):
    s = load_script("14_render_figures.py")
    assert hasattr(s, "render_delta_maps")


def test_run_pipeline_hazard_only_no_vulnerability_script():
    root = Path(__file__).resolve().parents[1]
    source = (root / "run_pipeline.py").read_text()
    assert "--skip-ml" in source
    assert "--retrain-models" in source
    assert "05_apply_mesh_bias_correction.py" in source
    assert "14_build_vulnerability.py" not in source
    assert "14_render_figures.py" in source
    assert "15_render_figures.py" not in source
    assert not (root / "scripts" / "14_build_vulnerability.py").exists()
    assert not (root / "tests" / "test_14_build_vulnerability.py").exists()
    assert not (root / "docs" / "vulnerability_derivation.md").exists()


def test_run_pipeline_dry_run_lists_stage_14_render():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "run_pipeline.py"), "--dry-run"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "14_build_vulnerability" not in proc.stdout
    assert "14_render_figures.py" in proc.stdout
    assert "15_render_figures.py" not in proc.stdout
