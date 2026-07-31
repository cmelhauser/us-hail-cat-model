"""Tests for hail_aws.orchestrator."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from hail_aws.config import load_pipeline_config
from hail_aws.ecs_client import RunningTask, TaskOutcome
from hail_aws.orchestrator import (
    FanoutOverrides,
    WorkflowPlan,
    WorkflowResult,
    build_plan,
    resolve_network,
    run_workflow,
    task_definition_arn,
)

FANOUT_1DAY = FanoutOverrides(
    from_date=date(2015, 5, 20),
    until_date=date(2015, 5, 20),
    max_concurrent=2,
)


def test_build_plan_modes(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    full = build_plan(cfg, "full", fanout_overrides=FANOUT_1DAY)
    assert len(full.parallel) == 2
    assert full.gridrad_fanout is not None
    assert full.gridrad_fanout.day_count == 1
    assert full.finalize is not None
    assert "gridrad fan-out" in "\n".join(full.summary_lines())

    dl = build_plan(cfg, "downloads-only", fanout_overrides=FANOUT_1DAY)
    assert len(dl.parallel) == 2
    assert dl.gridrad_fanout is not None
    assert dl.finalize is None

    fin = build_plan(cfg, "finalize")
    assert fin.parallel == []
    assert fin.gridrad_fanout is None
    assert fin.finalize is not None

    dry = build_plan(cfg, "dry-run", fanout_overrides=FANOUT_1DAY)
    assert dry.gridrad_fanout is not None
    assert dry.finalize is not None


def test_build_plan_monolithic(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    plan = build_plan(
        cfg,
        "downloads-only",
        fanout_overrides=FanoutOverrides(enabled=False),
    )
    assert plan.gridrad_fanout is None
    assert {t.name for t in plan.parallel} == {
        "download_myrorss",
        "download_mrms",
        "download_gridrad",
    }


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
    result = run_workflow(cfg, "dry-run", fanout_overrides=FANOUT_1DAY)
    assert result.ok
    assert result.outcomes == []


def _ok_outcome(name: str, arn: str) -> TaskOutcome:
    return TaskOutcome(arn, name, "STOPPED", None, None, 0)


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

    counter = {"n": 0}

    def run_task(**kwargs: Any) -> RunningTask:
        counter["n"] += 1
        name = kwargs["task_name"]
        return RunningTask(f"arn:{counter['n']}", name, "hail-pipeline")

    client.run_task.side_effect = run_task

    poll_state = {"n": 0}

    def describe(cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        poll_state["n"] += 1
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
        fanout_overrides=FANOUT_1DAY,
    )
    assert result.ok
    # myrorss + mrms + 1 gridrad day + manifest rebuild + finalize
    assert len(result.outcomes) == 5
    assert sleeps
    # Day task must override container command.
    day_calls = [
        c.kwargs
        for c in client.run_task.call_args_list
        if c.kwargs["task_name"].startswith("download_gridrad_20")
    ]
    assert day_calls
    assert day_calls[0]["command"] is not None
    assert "scripts/04c_fill_gridrad_gap.py" in day_calls[0]["command"]


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

    counter = {"n": 0}

    def run_task(**kwargs: Any) -> RunningTask:
        counter["n"] += 1
        return RunningTask(f"arn:{counter['n']}", kwargs["task_name"], "hail-pipeline")

    client.run_task.side_effect = run_task

    calls = {"n": 0}

    def describe(cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        calls["n"] += 1
        if calls["n"] == 1:
            out = []
            for a in task_arns:
                # Fail the first family task (myrorss); keep siblings running.
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
        fanout_overrides=FANOUT_1DAY,
    )
    assert not result.ok
    assert client.stop_task.call_count >= 1
    assert result.cancelled


def test_run_workflow_empty_outcomes_not_ok() -> None:
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


def test_monolithic_downloads_still_work(config_path: Path) -> None:
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
    client.describe_tasks.return_value = [
        {"taskArn": "arn:1", "lastStatus": "STOPPED", "containers": [{"exitCode": 0}]},
        {"taskArn": "arn:2", "lastStatus": "STOPPED", "containers": [{"exitCode": 0}]},
        {"taskArn": "arn:3", "lastStatus": "STOPPED", "containers": [{"exitCode": 0}]},
    ]
    client.outcome_from_description.side_effect = (
        lambda name, desc: _ok_outcome(name, desc["taskArn"])
    )
    result = run_workflow(
        cfg,
        "downloads-only",
        client=client,
        stack_outputs=outputs,
        sleep_fn=lambda _s: None,
        fanout_overrides=FanoutOverrides(enabled=False),
    )
    assert result.ok
    assert len(result.outcomes) == 3


def test_fanout_empty_days_sample_command(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    plan = build_plan(
        cfg,
        "downloads-only",
        fanout_overrides=FanoutOverrides(
            from_date=date(2015, 5, 20),
            until_date=date(2015, 5, 20),
        ),
    )
    assert plan.gridrad_fanout is not None
    gf = plan.gridrad_fanout
    empty = type(gf)(**{**gf.__dict__, "days": []})
    assert empty.sample_command() == []
    assert "sample cmd: (no days)" in "\n".join(
        WorkflowPlan(mode="downloads-only", gridrad_fanout=empty).summary_lines()
    )


def test_day_failure_does_not_cancel_by_default(config_path: Path) -> None:
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
    counter = {"n": 0}

    def run_task(**kwargs: Any) -> RunningTask:
        counter["n"] += 1
        return RunningTask(f"arn:{counter['n']}", kwargs["task_name"], "hail-pipeline")

    client.run_task.side_effect = run_task

    def describe(cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        out = []
        for a in task_arns:
            idx = int(a.split(":")[-1])
            code = 1 if idx == 3 else 0
            out.append(
                {
                    "taskArn": a,
                    "lastStatus": "STOPPED",
                    "containers": [{"exitCode": code}],
                }
            )
        return out

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
        fanout_overrides=FanoutOverrides(
            from_date=date(2015, 5, 20),
            until_date=date(2015, 5, 21),
            max_concurrent=2,
        ),
    )
    assert not result.ok
    assert client.stop_task.call_count == 0


def test_monolithic_download_failure_cancels(config_path: Path) -> None:
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
        fanout_overrides=FanoutOverrides(enabled=False),
    )
    assert not result.ok
    assert client.stop_task.call_count == 2
    assert set(result.cancelled) == {"download_mrms", "download_gridrad"}


def test_day_sibling_cancel_when_enabled(config_path: Path) -> None:
    from dataclasses import replace

    from hail_aws.config import GridradFanoutSpec

    base = load_pipeline_config(config_path)
    cfg = replace(
        base,
        # Keep family downloads running while a day fails so cancel skips them.
        cancel_siblings_on_failure=False,
        gridrad_fanout=replace(
            base.gridrad_fanout,
            cancel_day_siblings_on_failure=True,
            post_manifest_rebuild=False,
        ),
    )
    client = MagicMock()
    outputs = {
        "ClusterName": "hail-pipeline",
        "SubnetIds": "subnet-a",
        "TaskSecurityGroupId": "sg-1",
        "TaskDefhail-download-myrorss": "td-01",
        "TaskDefhail-download-mrms": "td-02",
        "TaskDefhail-download-gridrad": "td-04c",
    }
    counter = {"n": 0}

    def run_task(**kwargs: Any) -> RunningTask:
        counter["n"] += 1
        return RunningTask(f"arn:{counter['n']}", kwargs["task_name"], "hail-pipeline")

    client.run_task.side_effect = run_task
    calls = {"n": 0}

    def describe(cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        calls["n"] += 1
        out = []
        for a in task_arns:
            idx = int(a.split(":")[-1])
            if calls["n"] == 1:
                # Day task arn:3 fails; family (1,2) and sibling day (4) still running.
                if idx == 3:
                    out.append(
                        {
                            "taskArn": a,
                            "lastStatus": "STOPPED",
                            "containers": [{"exitCode": 1}],
                        }
                    )
                else:
                    out.append({"taskArn": a, "lastStatus": "RUNNING"})
            else:
                out.append(
                    {
                        "taskArn": a,
                        "lastStatus": "STOPPED",
                        "containers": [{"exitCode": 0 if idx < 3 else 137}],
                    }
                )
        return out

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
        fanout_overrides=FanoutOverrides(
            from_date=date(2015, 5, 20),
            until_date=date(2015, 5, 22),
            max_concurrent=2,
        ),
    )
    assert not result.ok
    assert client.stop_task.call_count >= 1
    assert result.cancelled
    assert isinstance(cfg.gridrad_fanout, GridradFanoutSpec)
    stopped_arns = {c.args[1] for c in client.stop_task.call_args_list}
    assert "arn:1" not in stopped_arns
    assert "arn:2" not in stopped_arns
    assert "arn:4" in stopped_arns
