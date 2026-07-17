"""Shared fixtures for aws/ tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

AWS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AWS_ROOT.parent
if str(AWS_ROOT) not in sys.path:
    sys.path.insert(0, str(AWS_ROOT))

DEFAULT_YAML = AWS_ROOT / "config" / "pipeline.yaml"


@pytest.fixture
def config_path() -> Path:
    return DEFAULT_YAML


@pytest.fixture
def minimal_yaml(tmp_path: Path) -> Path:
    data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path
