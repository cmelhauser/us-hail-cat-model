"""Tests for hail_aws.orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from hail_aws.config import load_pipeline_config
from hail_aws.ecs_client import RunningTask, TaskOutcome
from hail_aws.orchestrator import (
    build_plan,
    resolve_network,
    run_workflow,
    task_definition_arn,
)


def test_build_plan_modes(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    full = build_plan(cfg, "full")
    assert len(full.parallel) == 3
    assert full.finalize is not None
    assert "mode=full" in full.summary_lines()[0]

    dl = build_plan(cfg, "downloads-only")
    assert len(dl.parallel) == 3
    assert dl.finalize is None

    fin = build_plan(cfg, "finalize")
    assert fin.parallel == []
    assert fin.finalize is not None

    dry = build_plan(cfg, "dry-run")
    assert len(dry.parallel) == 3
    assert dry.finalize is not None


def test_build_plan_bad_mode(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    with pytest.raises(ValueError, match="Unknown mode"):
        build_plan(cfg, "nope")  # type: ignore[arg-type]


def test_task_definition_arn_resolution() -> None:
    outs = {"TaskDefhail-download-mrms": "arn:td:mrms"}
    assert task_definition_arn(outs, "hail-download-mrms") == "arn:td:mrms"
    outs2 = {"hail-download-mrmsTaskDefinitionArn": "arn:td:2"}
    assert task_definition_arn(outs2, "hail-download-mrms") == "arn:td:2"
    outs3 = {"X": "arn:aws:ecs:us-east-1:1:task-definition/hail-download-mrms:1"}
    assert "hail-download-mrms" in task_definition_arn(outs3, "hail-download-mrms")
    with pytest.raises(KeyError, match="No task definition"):
        task_definition_arn({"A": "1"}, "missing")


def test_resolve_network() -> None:
    outs = {
        "ClusterName": "hail-pipeline",
        "SubnetIds": "subnet-a,subnet-b",
        "TaskSecurityGroupId": "sg-1",
    }
    net = resolve_network(outs, cluster_fallback="fb")
    assert net["cluster"] == "hail-pipeline"
    assert net["subnets"] == ["subnet-a", "subnet-b"]
    assert net["security_groups"] == ["sg-1"]


def test_resolve_network_missing() -> None:
    with pytest.raises(RuntimeError, match="SubnetIds"):
        resolve_network({"TaskSecurityGroupId": "sg"}, cluster_fallback="c")
    with pytest.raises(RuntimeError, match="TaskSecurityGroupId"):
        resolve_network({"SubnetIds": "s1"}, cluster_fallback="c")


def test_run_workflow_dry_run(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    result = run_workflow(cfg, "dry-run")
    assert result.ok
    assert result.outcomes == []


def test_run_workflow_full_success(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    client = MagicMock()
    outputs = {
        "ClusterName": "hail-pipeline",
        "SubnetIds": "subnet-a",
        "TaskSecurityGroupId": "sg-1",
        "TaskDefhail-download-myrorss": "td-01",
        "TaskDefhail-download-mrms": "td-02",
        "TaskDefhail-download-gridrad": "td-04c",
        "TaskDefhail-finalize": "td-fin",
    }
    client.stack_outputs.return_value = outputs

    arns = {
        "download_myrorss": "arn:1",
        "download_mrms": "arn:2",
        "download_gridrad": "arn:3",
        "finalize": "arn:4",
    }

    def run_task(**kwargs: Any) -> RunningTask:
        name = kwargs["task_name"]
        return RunningTask(arns[name], name, "hail-pipeline")

    client.run_task.side_effect = run_task

    # First poll: downloads still running; second: all stopped ok; then finalize.
    poll_state = {"n": 0}

    def describe(cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        poll_state["n"] += 1
        if set(task_arns) == {"arn:4"}:
            return [
                {
                    "taskArn": "arn:4",
                    "lastStatus": "STOPPED",
                    "containers": [{"exitCode": 0}],
                }
            ]
        if poll_state["n"] == 1:
            return [{"taskArn": a, "lastStatus": "RUNNING"} for a in task_arns]
        return [
            {
                "taskArn": a,
                "lastStatus": "STOPPED",
                "containers": [{"exitCode": 0}],
            }
            for a in task_arns
        ]

    client.describe_tasks.side_effect = describe
    client.outcome_from_description.side_effect = (
        lambda name, desc: TaskOutcome(
            desc["taskArn"],
            name,
            desc["lastStatus"],
            None,
            None,
            (desc.get("containers") or [{}])[0].get("exitCode"),
        )
    )

    sleeps: list[float] = []
    result = run_workflow(
        cfg,
        "full",
        client=client,
        stack_outputs=outputs,
        sleep_fn=sleeps.append,
    )
    assert result.ok
    assert len(result.outcomes) == 4
    assert sleeps  # polled at least once while RUNNING


def test_run_workflow_download_failure_cancels(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    client = MagicMock()
    outputs = {
        "ClusterName": "hail-pipeline",
        "SubnetIds": "subnet-a",
        "TaskSecurityGroupId": "sg-1",
        "TaskDefhail-download-myrorss": "td-01",
        "TaskDefhail-download-mrms": "td-02",
        "TaskDefhail-download-gridrad": "td-04c",
    }

    def run_task(**kwargs: Any) -> RunningTask:
        name = kwargs["task_name"]
        idx = {"download_myrorss": "1", "download_mrms": "2", "download_gridrad": "3"}[name]
        return RunningTask(f"arn:{idx}", name, "hail-pipeline")

    client.run_task.side_effect = run_task

    # First describe: myrorss failed, others still running -> cancel.
    # Second: all stopped.
    calls = {"n": 0}

    def describe(cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        calls["n"] += 1
        if calls["n"] == 1:
            out = []
            for a in task_arns:
                if a == "arn:1":
                    out.append(
                        {
                            "taskArn": a,
                            "lastStatus": "STOPPED",
                            "containers": [{"exitCode": 1}],
                        }
                    )
                else:
                    out.append({"taskArn": a, "lastStatus": "RUNNING"})
            return out
        return [
            {
                "taskArn": a,
                "lastStatus": "STOPPED",
                "containers": [{"exitCode": 1 if a == "arn:1" else 137}],
            }
            for a in task_arns
        ]

    client.describe_tasks.side_effect = describe
    client.outcome_from_description.side_effect = (
        lambda name, desc: TaskOutcome(
            desc["taskArn"],
            name,
            "STOPPED",
            None,
            None,
            (desc.get("containers") or [{}])[0].get("exitCode"),
        )
    )

    result = run_workflow(
        cfg,
        "downloads-only",
        client=client,
        stack_outputs=outputs,
        sleep_fn=lambda _s: None,
    )
    assert not result.ok
    assert client.stop_task.call_count == 2
    assert set(result.cancelled) == {"download_mrms", "download_gridrad"}


def test_run_workflow_empty_outcomes_not_ok(config_path: Path) -> None:
    from hail_aws.orchestrator import WorkflowPlan, WorkflowResult

    plan = WorkflowPlan(mode="finalize")
    assert WorkflowResult(plan=plan, outcomes=[]).ok is False


def test_wait_skips_missing_describe(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    client = MagicMock()
    outputs = {
        "ClusterName": "hail-pipeline",
        "SubnetIds": "subnet-a",
        "TaskSecurityGroupId": "sg-1",
        "TaskDefhail-finalize": "td-fin",
    }
    client.run_task.return_value = RunningTask("arn:f", "finalize", "hail-pipeline")
    client.describe_tasks.side_effect = [
        [],
        [{"taskArn": "arn:f", "lastStatus": "STOPPED", "containers": [{"exitCode": 0}]}],
    ]
    client.outcome_from_description.return_value = TaskOutcome(
        "arn:f", "finalize", "STOPPED", None, None, 0
    )
    result = run_workflow(
        cfg,
        "finalize",
        client=client,
        stack_outputs=outputs,
        sleep_fn=lambda _s: None,
    )
    assert result.ok


def test_run_workflow_creates_client(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_pipeline_config(config_path)
    fake = MagicMock()
    fake.stack_outputs.return_value = {
        "ClusterName": "hail-pipeline",
        "SubnetIds": "subnet-a",
        "TaskSecurityGroupId": "sg-1",
        "TaskDefhail-finalize": "td-fin",
    }
    fake.run_task.return_value = RunningTask("arn:f", "finalize", "hail-pipeline")
    fake.describe_tasks.return_value = [
        {"taskArn": "arn:f", "lastStatus": "STOPPED", "containers": [{"exitCode": 0}]}
    ]
    fake.outcome_from_description.return_value = TaskOutcome(
        "arn:f", "finalize", "STOPPED", None, None, 0
    )
    monkeypatch.setattr("hail_aws.orchestrator.EcsWorkflowClient", lambda **_k: fake)
    result = run_workflow(cfg, "finalize", sleep_fn=lambda _s: None)
    assert result.ok


def test_run_workflow_uses_stack_outputs_lookup(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    client = MagicMock()
    outputs = {
        "ClusterName": "hail-pipeline",
        "SubnetIds": "subnet-a",
        "TaskSecurityGroupId": "sg-1",
        "TaskDefhail-finalize": "td-fin",
    }
    client.stack_outputs.return_value = outputs
    client.run_task.return_value = RunningTask("arn:f", "finalize", "hail-pipeline")
    client.describe_tasks.return_value = [
        {"taskArn": "arn:f", "lastStatus": "STOPPED", "containers": [{"exitCode": 0}]}
    ]
    client.outcome_from_description.return_value = TaskOutcome(
        "arn:f", "finalize", "STOPPED", None, None, 0
    )
    result = run_workflow(cfg, "finalize", client=client, sleep_fn=lambda _s: None)
    assert result.ok
    client.stack_outputs.assert_called_once()
