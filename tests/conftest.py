from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

@pytest.fixture
def load_script():
    def _load(filename: str):
        path = SCRIPTS / filename
        module_name = "stage_" + filename.replace(".py", "").replace("-", "_").replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod
    return _load
