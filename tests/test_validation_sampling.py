import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "filename",
    [
        "01_download_myrorss.py",
        "02_download_mrms_mesh.py",
        "03_download_spc.py",
        "05_apply_mesh_bias_correction.py",
    ],
)
def test_validation_sampling_uses_canonical_rng_seed(filename):
    script = Path(__file__).resolve().parents[1] / "scripts" / filename
    tree = ast.parse(script.read_text())

    seeded_samples = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "sample"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Attribute)
        and isinstance(node.func.value.func.value, ast.Name)
        and node.func.value.func.value.id == "random"
        and node.func.value.func.attr == "Random"
        and len(node.func.value.args) == 1
        and isinstance(node.func.value.args[0], ast.Name)
        and node.func.value.args[0].id == "RNG_SEED"
    ]
    assert seeded_samples
