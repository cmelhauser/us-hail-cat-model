"""Unit tests for hail_aws.localstack_support (mocked — no live LocalStack)."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

AWS_ROOT = Path(__file__).resolve().parents[1]
if str(AWS_ROOT) not in sys.path:
    sys.path.insert(0, str(AWS_ROOT))

from hail_aws import localstack_support as ls
from hail_aws.config import load_pipeline_config

LS_CONFIG = AWS_ROOT / "config" / "pipeline.localstack.yaml"


def test_wait_for_localstack_success() -> None:
    with patch.object(ls, "_client") as client_factory:
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "1"}
        client_factory.return_value = sts
        ls.wait_for_localstack("http://localhost:4566", timeout_s=2.0)
        assert client_factory.called


def test_wait_for_localstack_timeout() -> None:
    with patch.object(ls, "_client") as client_factory:
        sts = MagicMock()
        sts.get_caller_identity.side_effect = RuntimeError("down")
        client_factory.return_value = sts
        with (
            patch.object(ls.time, "sleep", return_value=None),
            patch.object(ls.time, "time", side_effect=[0.0, 0.5, 2.0]),
            pytest.raises(RuntimeError, match="not ready"),
        ):
            ls.wait_for_localstack("http://localhost:4566", timeout_s=1.0)


def test_client_factory_kwargs() -> None:
    with patch("hail_aws.localstack_support.boto3.client") as boto_client:
        ls._client("sts", endpoint_url="http://localhost:4566", region="us-east-1")
        kwargs = boto_client.call_args.kwargs
        assert kwargs["endpoint_url"] == "http://localhost:4566"
        assert kwargs["aws_access_key_id"] == "test"
        assert kwargs["aws_secret_access_key"] == "test"


def _mock_clients(*, role_exists: bool = False, cluster_exists: bool = False) -> dict[str, Any]:
    ecs = MagicMock()
    ec2 = MagicMock()
    cfn = MagicMock()
    iam = MagicMock()

    ec2.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-1"}}
    ec2.create_subnet.return_value = {"Subnet": {"SubnetId": "subnet-1"}}
    ec2.create_security_group.return_value = {"GroupId": "sg-1"}
    iam.get_role.return_value = {"Role": {"Arn": "arn:role"}}
    if role_exists:
        iam.create_role.side_effect = RuntimeError("exists")
    if cluster_exists:
        ecs.create_cluster.side_effect = RuntimeError("exists")
    ecs.register_task_definition.return_value = {
        "taskDefinition": {"taskDefinitionArn": "arn:td:x"}
    }
    # First describe: CREATE_IN_PROGRESS; second: CREATE_COMPLETE with Outputs.
    cfn.describe_stacks.side_effect = [
        {"Stacks": [{"StackStatus": "CREATE_IN_PROGRESS", "Outputs": []}]},
        {
            "Stacks": [
                {
                    "StackStatus": "CREATE_COMPLETE",
                    "Outputs": [
                        {"OutputKey": "ClusterName", "OutputValue": "from-cfn"},
                    ],
                }
            ]
        },
        {
            "Stacks": [
                {
                    "StackStatus": "CREATE_COMPLETE",
                    "Outputs": [
                        {"OutputKey": "ClusterName", "OutputValue": "from-cfn"},
                    ],
                }
            ]
        },
    ]
    return {"ecs": ecs, "ec2": ec2, "cloudformation": cfn, "iam": iam}


def test_provision_workflow_surface() -> None:
    cfg = load_pipeline_config(LS_CONFIG)
    clients = _mock_clients(role_exists=True, cluster_exists=True)

    def client(service: str, **_kw: Any) -> Any:
        return clients[service]

    with (
        patch.object(ls, "_client", side_effect=client),
        patch.object(ls.time, "sleep", return_value=None),
    ):
        env = ls.provision_workflow_surface(
            cfg, endpoint_url="http://localhost:4566", stack_name="test-ls"
        )
    assert env.cluster.endswith("-ls") or "hail" in env.cluster
    assert env.outputs["ClusterName"] == "from-cfn"
    assert clients["ecs"].register_task_definition.call_count == len(cfg.tasks)
    assert clients["cloudformation"].create_stack.called
    assert clients["cloudformation"].delete_stack.called


def test_provision_handles_delete_and_output_failures() -> None:
    cfg = load_pipeline_config(LS_CONFIG)
    clients = _mock_clients()
    clients["cloudformation"].delete_stack.side_effect = RuntimeError("missing")
    # Wait loop COMPLETE on first poll; final Outputs fetch raises.
    clients["cloudformation"].describe_stacks.side_effect = [
        {"Stacks": [{"StackStatus": "CREATE_COMPLETE"}]},
        RuntimeError("no outputs"),
    ]

    def client(service: str, **_kw: Any) -> Any:
        return clients[service]

    with (
        patch.object(ls, "_client", side_effect=client),
        patch.object(ls.time, "sleep", return_value=None),
    ):
        env = ls.provision_workflow_surface(
            cfg, endpoint_url="http://localhost:4566"
        )
    assert "ClusterName" in env.outputs
    assert env.stack_name  # default name from config


def test_start_task_completer_stops_running() -> None:
    ecs = MagicMock()
    ecs.list_tasks.return_value = {"taskArns": ["arn:t1"]}
    ecs.describe_tasks.return_value = {
        "tasks": [{"taskArn": "arn:t1", "lastStatus": "RUNNING"}]
    }

    with patch.object(ls, "_client", return_value=ecs):
        stop, thread = ls.start_task_completer(
            endpoint_url="http://localhost:4566",
            region="us-east-1",
            cluster="c",
            poll_seconds=0.05,
        )
        for _ in range(40):
            if ecs.stop_task.called:
                break
            threading.Event().wait(0.05)
        stop.set()
        thread.join(timeout=2.0)
    assert ecs.stop_task.called


def test_start_task_completer_swallows_errors() -> None:
    ecs = MagicMock()
    ecs.list_tasks.side_effect = [
        {"taskArns": ["arn:t1"]},
        RuntimeError("boom"),
        {"taskArns": []},
    ]
    ecs.describe_tasks.return_value = {
        "tasks": [{"taskArn": "arn:t1", "lastStatus": "PENDING"}]
    }
    ecs.stop_task.side_effect = RuntimeError("already stopped")

    with patch.object(ls, "_client", return_value=ecs):
        stop, thread = ls.start_task_completer(
            endpoint_url="http://localhost:4566",
            region="us-east-1",
            cluster="c",
            poll_seconds=0.02,
        )
        for _ in range(50):
            if ecs.stop_task.called and ecs.list_tasks.call_count >= 2:
                break
            threading.Event().wait(0.02)
        stop.set()
        thread.join(timeout=2.0)
    assert thread.is_alive() is False
