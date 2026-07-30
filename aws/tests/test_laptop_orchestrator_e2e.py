"""Laptop-orchestrator E2E for downloads-only and full workflows.

LocalStack Community 4.x gates ECS (Pro). moto's Fargate+awsvpc RunTask path is
currently broken (NetworkInterface.private_dns_name). These tests use an
in-process ECS stub that speaks the same client contract the laptop CLI uses,
so we still shake out plan → parallel RunTask → poll → finalize ordering.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

AWS_ROOT = Path(__file__).resolve().parents[1]
if str(AWS_ROOT) not in sys.path:
    sys.path.insert(0, str(AWS_ROOT))

from hail_aws.config import load_pipeline_config
from hail_aws.ecs_client import EcsWorkflowClient, RunningTask, TaskOutcome
from hail_aws.orchestrator import build_plan, run_workflow
import run_pipeline_aws as cli

LS_CONFIG = AWS_ROOT / "config" / "pipeline.localstack.yaml"


class StubEcsWorkflowClient(EcsWorkflowClient):
    """In-memory ECS/CFN stand-in that completes tasks on first describe poll."""

    def __init__(self, outputs: dict[str, str], *, fail_task: str | None = None) -> None:
        # Bypass boto3 — we override all methods used by the orchestrator.
        self.region = "us-east-1"
        self.endpoint_url = "http://stub.local"
        self._session = None
        self.ecs = None
        self.cfn = None
        self._outputs = outputs
        self._tasks: dict[str, dict[str, Any]] = {}
        self._fail_task = fail_task
        self.run_calls: list[str] = []
        self.stop_calls: list[str] = []

    def stack_outputs(self, stack_name: str) -> dict[str, str]:
        assert stack_name
        return dict(self._outputs)

    def run_task(
        self,
        *,
        cluster: str,
        task_definition: str,
        subnets: list[str],
        security_groups: list[str],
        assign_public_ip: bool,
        started_by: str,
        task_name: str,
    ) -> RunningTask:
        assert cluster and task_definition and subnets and security_groups
        assert started_by
        assert assign_public_ip in (True, False)
        arn = f"arn:stub:task/{task_name}/{uuid.uuid4()}"
        self._tasks[arn] = {
            "taskArn": arn,
            "lastStatus": "RUNNING",
            "task_name": task_name,
            "polls": 0,
        }
        self.run_calls.append(task_name)
        return RunningTask(task_arn=arn, task_name=task_name, cluster=cluster)

    def describe_tasks(self, cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for arn in task_arns:
            t = self._tasks[arn]
            t["polls"] += 1
            name = t["task_name"]
            # Fail the designated task on first poll while siblings stay RUNNING,
            # so cancel_siblings_on_failure is exercised.
            if name == self._fail_task and t["polls"] >= 1:
                out.append(
                    {
                        "taskArn": arn,
                        "lastStatus": "STOPPED",
                        "stopCode": "EssentialContainerExited",
                        "stoppedReason": "stub-fail",
                        "containers": [{"name": "hail", "exitCode": 1}],
                    }
                )
                continue
            if t["polls"] == 1:
                out.append({"taskArn": arn, "lastStatus": "RUNNING", "containers": []})
                continue
            out.append(
                {
                    "taskArn": arn,
                    "lastStatus": "STOPPED",
                    "stopCode": "EssentialContainerExited",
                    "stoppedReason": "stub-complete",
                    "containers": [{"name": "hail", "exitCode": 0}],
                }
            )
        return out

    def stop_task(self, cluster: str, task_arn: str, reason: str) -> None:
        self.stop_calls.append(task_arn)
        if task_arn in self._tasks:
            self._tasks[task_arn]["lastStatus"] = "STOPPED"

    @staticmethod
    def outcome_from_description(task_name: str, desc: dict[str, Any]) -> TaskOutcome:
        return EcsWorkflowClient.outcome_from_description(task_name, desc)


def _outputs_for(cfg) -> dict[str, str]:
    outs = {
        "ClusterName": f"{cfg.cluster_name}-stub",
        "SubnetIds": "subnet-stub-a,subnet-stub-b",
        "TaskSecurityGroupId": "sg-stub",
    }
    for spec in cfg.tasks.values():
        outs[f"TaskDef{spec.family}"] = f"arn:td:{spec.family}"
    return outs


@pytest.mark.parametrize("mode,expected_n", [("downloads-only", 3), ("full", 4)])
def test_stub_laptop_monitor_modes(mode: str, expected_n: int) -> None:
    cfg = load_pipeline_config(LS_CONFIG)
    plan = build_plan(cfg, mode)  # type: ignore[arg-type]
    if mode == "downloads-only":
        assert len(plan.parallel) == 3 and plan.finalize is None
    else:
        assert len(plan.parallel) == 3 and plan.finalize is not None

    client = StubEcsWorkflowClient(_outputs_for(cfg))
    sleeps: list[float] = []
    result = run_workflow(
        cfg,
        mode,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        stack_name="stub-stack",
        sleep_fn=sleeps.append,
    )
    assert result.ok
    assert len(result.outcomes) == expected_n
    assert sleeps  # polled while RUNNING
    assert set(client.run_calls[:3]) == {
        "download_myrorss",
        "download_mrms",
        "download_gridrad",
    }
    if mode == "full":
        assert client.run_calls[-1] == "finalize"
        assert result.outcomes[-1].task_name == "finalize"


def test_stub_cli_downloads_only_and_full(capsys: pytest.CaptureFixture[str]) -> None:
    cfg = load_pipeline_config(LS_CONFIG)
    outs = _outputs_for(cfg)
    clients: list[StubEcsWorkflowClient] = []

    def fake_client(**_kwargs: Any) -> StubEcsWorkflowClient:
        c = StubEcsWorkflowClient(outs)
        clients.append(c)
        return c

    with patch.object(cli, "EcsWorkflowClient", side_effect=fake_client):
        code_dl = cli.main(
            [
                "--config",
                str(LS_CONFIG),
                "--mode",
                "downloads-only",
                "--endpoint-url",
                "http://localhost:4566",
                "--stack-name",
                "stub-stack",
                "--region",
                "us-east-1",
            ]
        )
        out_dl = capsys.readouterr().out
        assert code_dl == 0, out_dl
        assert "parallel downloads" in out_dl
        assert "Workflow completed successfully" in out_dl

        code_full = cli.main(
            [
                "--config",
                str(LS_CONFIG),
                "--mode",
                "full",
                "--endpoint-url",
                "http://localhost:4566",
                "--stack-name",
                "stub-stack",
                "--region",
                "us-east-1",
            ]
        )
        out_full = capsys.readouterr().out
        assert code_full == 0, out_full
        assert "finalize:" in out_full
        assert "Workflow completed successfully" in out_full

    assert len(clients) == 2
    assert clients[0].run_calls == [
        "download_myrorss",
        "download_mrms",
        "download_gridrad",
    ]
    assert clients[1].run_calls[-1] == "finalize"


def test_stub_download_failure_skips_finalize() -> None:
    cfg = load_pipeline_config(LS_CONFIG)
    client = StubEcsWorkflowClient(_outputs_for(cfg), fail_task="download_mrms")
    result = run_workflow(
        cfg,
        "full",
        client=client,  # type: ignore[arg-type]
        stack_name="stub-stack",
        sleep_fn=lambda _s: None,
    )
    assert not result.ok
    assert "finalize" not in client.run_calls
    assert client.stop_calls  # sibling cancel
