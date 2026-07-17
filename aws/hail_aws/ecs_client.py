"""Thin ECS / CloudFormation helpers used by the local orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import boto3


class BotoSessionFactory(Protocol):
    def client(self, service_name: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class RunningTask:
    task_arn: str
    task_name: str
    cluster: str


@dataclass(frozen=True)
class TaskOutcome:
    task_arn: str
    task_name: str
    last_status: str
    stop_code: str | None
    stopped_reason: str | None
    exit_code: int | None

    @property
    def succeeded(self) -> bool:
        return self.last_status == "STOPPED" and self.exit_code == 0


class EcsWorkflowClient:
    """Wrapper around boto3 ECS + CloudFormation for testability."""

    def __init__(
        self,
        *,
        region: str,
        endpoint_url: str | None = None,
        session: Any | None = None,
    ) -> None:
        self.region = region
        self.endpoint_url = endpoint_url
        self._session = session or boto3.session.Session(region_name=region)
        client_kwargs: dict[str, Any] = {"region_name": region}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        self.ecs = self._session.client("ecs", **client_kwargs)
        self.cfn = self._session.client("cloudformation", **client_kwargs)

    def stack_outputs(self, stack_name: str) -> dict[str, str]:
        resp = self.cfn.describe_stacks(StackName=stack_name)
        stacks = resp.get("Stacks") or []
        if not stacks:
            raise RuntimeError(f"CloudFormation stack not found: {stack_name}")
        outs = stacks[0].get("Outputs") or []
        return {o["OutputKey"]: o["OutputValue"] for o in outs if "OutputKey" in o}

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
        resp = self.ecs.run_task(
            cluster=cluster,
            taskDefinition=task_definition,
            launchType="FARGATE",
            count=1,
            startedBy=started_by[:36],
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": subnets,
                    "securityGroups": security_groups,
                    "assignPublicIp": "ENABLED" if assign_public_ip else "DISABLED",
                }
            },
        )
        failures = resp.get("failures") or []
        if failures:
            raise RuntimeError(f"ECS RunTask failures for {task_name}: {failures}")
        tasks = resp.get("tasks") or []
        if not tasks:
            raise RuntimeError(f"ECS RunTask returned no tasks for {task_name}")
        arn = tasks[0]["taskArn"]
        return RunningTask(task_arn=arn, task_name=task_name, cluster=cluster)

    def describe_tasks(self, cluster: str, task_arns: list[str]) -> list[dict[str, Any]]:
        if not task_arns:
            return []
        resp = self.ecs.describe_tasks(cluster=cluster, tasks=task_arns)
        return list(resp.get("tasks") or [])

    def stop_task(self, cluster: str, task_arn: str, reason: str) -> None:
        self.ecs.stop_task(cluster=cluster, task=task_arn, reason=reason[:255])

    @staticmethod
    def outcome_from_description(task_name: str, desc: dict[str, Any]) -> TaskOutcome:
        containers = desc.get("containers") or []
        exit_code = None
        if containers:
            exit_code = containers[0].get("exitCode")
        return TaskOutcome(
            task_arn=desc["taskArn"],
            task_name=task_name,
            last_status=desc.get("lastStatus", "UNKNOWN"),
            stop_code=desc.get("stopCode"),
            stopped_reason=desc.get("stoppedReason"),
            exit_code=exit_code,
        )
