"""Tests for aws/run_pipeline_aws.py CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

AWS_ROOT = Path(__file__).resolve().parents[1]
if str(AWS_ROOT) not in sys.path:
    sys.path.insert(0, str(AWS_ROOT))

import run_pipeline_aws as cli
from hail_aws.ecs_client import TaskOutcome
from hail_aws.orchestrator import WorkflowPlan, WorkflowResult


def test_parse_args_dry_run_flag() -> None:
    ns = cli.parse_args(["--dry-run"])
    assert ns.dry_run is True


def test_main_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Dry run complete" in out
    assert "parallel downloads" in out


def test_main_config_error(tmp_path: Path) -> None:
    code = cli.main(["--config", str(tmp_path / "missing.yaml"), "--dry-run"])
    assert code == 2


def test_main_success(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = WorkflowPlan(mode="finalize")
    result = WorkflowResult(
        plan=plan,
        outcomes=[TaskOutcome("arn", "finalize", "STOPPED", None, None, 0)],
    )
    monkeypatch.setattr(cli, "build_plan", lambda *_a, **_k: plan)
    monkeypatch.setattr(cli, "run_workflow", lambda *_a, **_k: result)
    monkeypatch.setattr(cli, "EcsWorkflowClient", MagicMock)
    code = cli.main(["--mode", "finalize", "--region", "us-west-2"])
    assert code == 0


def test_main_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = WorkflowPlan(mode="downloads-only")
    result = WorkflowResult(
        plan=plan,
        outcomes=[TaskOutcome("arn", "download_mrms", "STOPPED", None, "boom", 1)],
        cancelled=["download_gridrad"],
    )
    monkeypatch.setattr(cli, "build_plan", lambda *_a, **_k: plan)
    monkeypatch.setattr(cli, "run_workflow", lambda *_a, **_k: result)
    monkeypatch.setattr(cli, "EcsWorkflowClient", MagicMock)
    code = cli.main(["--mode", "downloads-only"])
    assert code == 1


def test_ensure_aws_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "path", [p for p in sys.path if not str(p).endswith("/aws")])
    cli._ensure_aws_on_path(tmp_path)
    assert str(tmp_path) in sys.path
    cli._ensure_aws_on_path(tmp_path)
    assert sys.path.count(str(tmp_path)) == 1
