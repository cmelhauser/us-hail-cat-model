"""Local orchestrator: plan and run Fargate workflow from PipelineConfig."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from hail_aws.config import PipelineConfig, TaskSpec
from hail_aws.ecs_client import EcsWorkflowClient, RunningTask, TaskOutcome

Mode = Literal["full", "downloads-only", "finalize", "dry-run"]

SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class PlannedTask:
    name: str
    family: str
    command: list[str]
    cpu: int
    memory: int
    ephemeral_storage_gib: int


@dataclass
class WorkflowPlan:
    mode: Mode
    parallel: list[PlannedTask] = field(default_factory=list)
    finalize: PlannedTask | None = None

    def summary_lines(self) -> list[str]:
        lines = [f"mode={self.mode}"]
        if self.parallel:
            lines.append("parallel downloads:")
            for t in self.parallel:
                lines.append(
                    f"  - {t.name} family={t.family} cpu={t.cpu} mem={t.memory} "
                    f"cmd={' '.join(t.command)}"
                )
        if self.finalize:
            t = self.finalize
            lines.append(
                f"finalize: {t.name} family={t.family} cpu={t.cpu} mem={t.memory} "
                f"cmd={' '.join(t.command)}"
            )
        return lines


@dataclass
class WorkflowResult:
    plan: WorkflowPlan
    outcomes: list[TaskOutcome] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if self.plan.mode == "dry-run":
            return True
        if not self.outcomes:
            return False
        return all(o.succeeded for o in self.outcomes)


def _planned(spec: TaskSpec) -> PlannedTask:
    return PlannedTask(
        name=spec.name,
        family=spec.family,
        command=list(spec.command),
        cpu=spec.cpu,
        memory=spec.memory,
        ephemeral_storage_gib=spec.ephemeral_storage_gib,
    )


def build_plan(config: PipelineConfig, mode: Mode) -> WorkflowPlan:
    if mode not in ("full", "downloads-only", "finalize", "dry-run"):
        raise ValueError(f"Unknown mode: {mode}")

    parallel: list[PlannedTask] = []
    finalize: PlannedTask | None = None
    effective: Mode = "full" if mode == "dry-run" else mode

    if effective in ("full", "downloads-only"):
        for name in config.parallel_downloads:
            parallel.append(_planned(config.tasks[name]))
    if effective in ("full", "finalize"):
        finalize = _planned(config.tasks[config.finalize_task])

    return WorkflowPlan(mode=mode, parallel=parallel, finalize=finalize)


def task_definition_arn(outputs: dict[str, str], family: str) -> str:
    """Resolve task definition ARN from CDK stack outputs."""
    preferred = [
        f"TaskDef{family}",
        f"{family}TaskDefinitionArn",
    ]
    for key in preferred:
        if key in outputs:
            return outputs[key]
    for key, value in outputs.items():
        if family in value and "task-definition" in value:
            return value
    raise KeyError(
        f"No task definition output for family '{family}'. "
        f"Tried {preferred}; available={sorted(outputs)}"
    )


def resolve_network(
    outputs: dict[str, str],
    *,
    cluster_fallback: str,
) -> dict[str, Any]:
    cluster = outputs.get("ClusterName") or outputs.get("ClusterArn") or cluster_fallback
    subnets_raw = outputs.get("SubnetIds") or outputs.get("PublicSubnetIds") or ""
    sgs_raw = outputs.get("TaskSecurityGroupId") or outputs.get("SecurityGroupId") or ""
    subnets = [s.strip() for s in subnets_raw.split(",") if s.strip()]
    security_groups = [s.strip() for s in sgs_raw.split(",") if s.strip()]
    if not subnets:
        raise RuntimeError("Stack outputs missing SubnetIds")
    if not security_groups:
        raise RuntimeError("Stack outputs missing TaskSecurityGroupId")
    return {
        "cluster": cluster,
        "subnets": subnets,
        "security_groups": security_groups,
    }


def _launch(
    client: EcsWorkflowClient,
    *,
    planned: PlannedTask,
    cluster: str,
    subnets: list[str],
    security_groups: list[str],
    assign_public_ip: bool,
    outputs: dict[str, str],
    started_by: str,
) -> RunningTask:
    task_def = task_definition_arn(outputs, planned.family)
    return client.run_task(
        cluster=cluster,
        task_definition=task_def,
        subnets=subnets,
        security_groups=security_groups,
        assign_public_ip=assign_public_ip,
        started_by=started_by,
        task_name=planned.name,
    )


def _wait_batch(
    client: EcsWorkflowClient,
    running: list[RunningTask],
    *,
    poll_seconds: float,
    sleep_fn: SleepFn,
    name_by_arn: dict[str, str],
    cancel_siblings_on_failure: bool = False,
) -> tuple[list[TaskOutcome], list[str]]:
    """Wait until all tasks stop. Optionally stop siblings when one fails."""
    pending = {t.task_arn: t for t in running}
    outcomes: list[TaskOutcome] = []
    cancelled: list[str] = []
    failure_seen = False
    cancel_issued = False
    while pending:
        cluster = next(iter(pending.values())).cluster
        descs = client.describe_tasks(cluster, list(pending.keys()))
        by_arn = {d["taskArn"]: d for d in descs}
        finished: list[str] = []
        for arn, rt in list(pending.items()):
            desc = by_arn.get(arn)
            if not desc:
                continue
            if desc.get("lastStatus") != "STOPPED":
                continue
            name = name_by_arn.get(arn, rt.task_name)
            outcome = client.outcome_from_description(name, desc)
            outcomes.append(outcome)
            finished.append(arn)
            if not outcome.succeeded:
                failure_seen = True
        for arn in finished:
            del pending[arn]

        if (
            failure_seen
            and cancel_siblings_on_failure
            and pending
            and not cancel_issued
        ):
            for arn, rt in list(pending.items()):
                client.stop_task(
                    cluster,
                    arn,
                    reason="Sibling download task failed; cancelling remaining downloads",
                )
                cancelled.append(rt.task_name)
            cancel_issued = True
        if pending:
            sleep_fn(poll_seconds)
    return outcomes, cancelled


def run_workflow(
    config: PipelineConfig,
    mode: Mode,
    *,
    client: EcsWorkflowClient | None = None,
    stack_name: str | None = None,
    stack_outputs: dict[str, str] | None = None,
    sleep_fn: SleepFn = time.sleep,
    started_by: str = "run-pipeline-aws",
) -> WorkflowResult:
    plan = build_plan(config, mode)
    if mode == "dry-run":
        return WorkflowResult(plan=plan)

    if client is None:
        client = EcsWorkflowClient(region=config.region)

    outputs = stack_outputs
    if outputs is None:
        name = stack_name or f"{config.project_name}-{config.environment}"
        outputs = client.stack_outputs(name)

    net = resolve_network(outputs, cluster_fallback=config.cluster_name)
    cluster = net["cluster"]
    subnets = net["subnets"]
    security_groups = net["security_groups"]

    outcomes: list[TaskOutcome] = []
    cancelled: list[str] = []

    if plan.parallel:
        running: list[RunningTask] = []
        name_by_arn: dict[str, str] = {}
        for planned in plan.parallel:
            rt = _launch(
                client,
                planned=planned,
                cluster=cluster,
                subnets=subnets,
                security_groups=security_groups,
                assign_public_ip=config.assign_public_ip,
                outputs=outputs,
                started_by=started_by,
            )
            running.append(rt)
            name_by_arn[rt.task_arn] = rt.task_name

        batch, cancelled = _wait_batch(
            client,
            running,
            poll_seconds=float(config.poll_seconds),
            sleep_fn=sleep_fn,
            name_by_arn=name_by_arn,
            cancel_siblings_on_failure=config.cancel_siblings_on_failure,
        )
        outcomes.extend(batch)

        if any(not o.succeeded for o in batch):
            return WorkflowResult(plan=plan, outcomes=outcomes, cancelled=cancelled)

    if plan.finalize:
        rt = _launch(
            client,
            planned=plan.finalize,
            cluster=cluster,
            subnets=subnets,
            security_groups=security_groups,
            assign_public_ip=config.assign_public_ip,
            outputs=outputs,
            started_by=started_by,
        )
        batch, _ = _wait_batch(
            client,
            [rt],
            poll_seconds=float(config.poll_seconds),
            sleep_fn=sleep_fn,
            name_by_arn={rt.task_arn: rt.task_name},
            cancel_siblings_on_failure=False,
        )
        outcomes.extend(batch)

    return WorkflowResult(plan=plan, outcomes=outcomes, cancelled=cancelled)
