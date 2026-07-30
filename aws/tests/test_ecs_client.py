"""Tests for hail_aws.ecs_client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from hail_aws.ecs_client import EcsWorkflowClient, TaskOutcome


def test_outcome_succeeded() -> None:
    ok = TaskOutcome("arn", "t", "STOPPED", None, None, 0)
    assert ok.succeeded
    bad = TaskOutcome("arn", "t", "STOPPED", "EssentialContainerExited", "fail", 1)
    assert not bad.succeeded
    running = TaskOutcome("arn", "t", "RUNNING", None, None, None)
    assert not running.succeeded


def test_stack_outputs() -> None:
    session = MagicMock()
    cfn = MagicMock()
    ecs = MagicMock()
    session.client.side_effect = lambda svc, **kw: cfn if svc == "cloudformation" else ecs
    cfn.describe_stacks.return_value = {
        "Stacks": [{"Outputs": [{"OutputKey": "A", "OutputValue": "1"}]}]
    }
    client = EcsWorkflowClient(region="us-east-1", session=session)
    assert client.stack_outputs("stack") == {"A": "1"}


def test_stack_outputs_missing() -> None:
    session = MagicMock()
    cfn = MagicMock()
    ecs = MagicMock()
    session.client.side_effect = lambda svc, **kw: cfn if svc == "cloudformation" else ecs
    cfn.describe_stacks.return_value = {"Stacks": []}
    client = EcsWorkflowClient(region="us-east-1", session=session)
    with pytest.raises(RuntimeError, match="not found"):
        client.stack_outputs("stack")


def test_run_task_success() -> None:
    session = MagicMock()
    cfn = MagicMock()
    ecs = MagicMock()
    session.client.side_effect = lambda svc, **kw: cfn if svc == "cloudformation" else ecs
    ecs.run_task.return_value = {
        "tasks": [{"taskArn": "arn:task:1"}],
        "failures": [],
    }
    client = EcsWorkflowClient(region="us-east-1", session=session, endpoint_url="http://localhost:4566")
    rt = client.run_task(
        cluster="c",
        task_definition="td",
        subnets=["s1"],
        security_groups=["sg"],
        assign_public_ip=True,
        started_by="cli",
        task_name="download_mrms",
    )
    assert rt.task_arn == "arn:task:1"
    assert rt.task_name == "download_mrms"
    kwargs = ecs.run_task.call_args.kwargs
    assert kwargs["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"] == "ENABLED"


def test_run_task_failures() -> None:
    session = MagicMock()
    cfn = MagicMock()
    ecs = MagicMock()
    session.client.side_effect = lambda svc, **kw: cfn if svc == "cloudformation" else ecs
    ecs.run_task.return_value = {"tasks": [], "failures": [{"reason": "nope"}]}
    client = EcsWorkflowClient(region="us-east-1", session=session)
    with pytest.raises(RuntimeError, match="failures"):
        client.run_task(
            cluster="c",
            task_definition="td",
            subnets=["s1"],
            security_groups=["sg"],
            assign_public_ip=False,
            started_by="cli",
            task_name="t",
        )


def test_run_task_empty() -> None:
    session = MagicMock()
    cfn = MagicMock()
    ecs = MagicMock()
    session.client.side_effect = lambda svc, **kw: cfn if svc == "cloudformation" else ecs
    ecs.run_task.return_value = {"tasks": [], "failures": []}
    client = EcsWorkflowClient(region="us-east-1", session=session)
    with pytest.raises(RuntimeError, match="no tasks"):
        client.run_task(
            cluster="c",
            task_definition="td",
            subnets=["s1"],
            security_groups=["sg"],
            assign_public_ip=False,
            started_by="cli",
            task_name="t",
        )


def test_describe_and_stop() -> None:
    session = MagicMock()
    cfn = MagicMock()
    ecs = MagicMock()
    session.client.side_effect = lambda svc, **kw: cfn if svc == "cloudformation" else ecs
    ecs.describe_tasks.return_value = {"tasks": [{"taskArn": "a"}]}
    client = EcsWorkflowClient(region="us-east-1", session=session)
    assert client.describe_tasks("c", []) == []
    assert client.describe_tasks("c", ["a"])[0]["taskArn"] == "a"
    client.stop_task("c", "a", "reason")
    ecs.stop_task.assert_called_once()


def test_outcome_from_description() -> None:
    desc: dict[str, Any] = {
        "taskArn": "arn",
        "lastStatus": "STOPPED",
        "stopCode": "EssentialContainerExited",
        "stoppedReason": "exit",
        "containers": [{"exitCode": 0}],
    }
    o = EcsWorkflowClient.outcome_from_description("t", desc)
    assert o.succeeded
    # LocalStack-style: STOPPED with no container exitCode → treat as success.
    desc2 = {**desc, "containers": []}
    o2 = EcsWorkflowClient.outcome_from_description("t", desc2)
    assert o2.exit_code == 0
    assert o2.succeeded
    desc3 = {
        "taskArn": "arn",
        "lastStatus": "STOPPED",
        "stopCode": "TaskFailedToStart",
        "stoppedReason": "CannotPullContainerError",
        "containers": [],
    }
    o3 = EcsWorkflowClient.outcome_from_description("t", desc3)
    assert o3.exit_code is None
    assert not o3.succeeded
    desc4 = {
        "taskArn": "arn",
        "lastStatus": "STOPPED",
        "stoppedReason": "ResourceInitializationError: fail to start",
        "containers": [],
    }
    o4 = EcsWorkflowClient.outcome_from_description("t", desc4)
    assert o4.exit_code is None
    assert not o4.succeeded
