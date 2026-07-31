"""Local orchestrator: plan and run Fargate workflow from PipelineConfig."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from hail_aws.config import GridradFanoutSpec, PipelineConfig, TaskSpec
from hail_aws.ecs_client import EcsWorkflowClient, RunningTask, TaskOutcome
from hail_aws.gridrad_fanout import (
    build_day_command,
    build_manifest_rebuild_command,
    day_task_name,
    iter_convective_days,
    resolve_gap_window,
)

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
    override_command: bool = False
    container_name: str = "hail"


@dataclass(frozen=True)
class GridradFanoutPlan:
    """Expanded Stage 04c day jobs (not listed individually in parallel)."""

    task_name: str
    family: str
    cpu: int
    memory: int
    ephemeral_storage_gib: int
    days: list[date]
    max_concurrent: int
    missing_only: bool
    with_04b_download: bool
    workers: int
    download_workers: int
    cancel_day_siblings_on_failure: bool
    post_manifest_rebuild: bool
    container_name: str

    @property
    def day_count(self) -> int:
        return len(self.days)

    def sample_command(self) -> list[str]:
        if not self.days:
            return []
        return build_day_command(
            self.days[0],
            with_04b_download=self.with_04b_download,
            workers=self.workers,
            download_workers=self.download_workers,
            missing_only=self.missing_only,
        ).argv

    def manifest_task(self) -> PlannedTask:
        return PlannedTask(
            name="download_gridrad_manifest",
            family=self.family,
            command=build_manifest_rebuild_command(),
            cpu=self.cpu,
            memory=self.memory,
            ephemeral_storage_gib=self.ephemeral_storage_gib,
            override_command=True,
            container_name=self.container_name,
        )


@dataclass
class WorkflowPlan:
    mode: Mode
    parallel: list[PlannedTask] = field(default_factory=list)
    gridrad_fanout: GridradFanoutPlan | None = None
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
        if self.gridrad_fanout is not None:
            gf = self.gridrad_fanout
            sample = " ".join(gf.sample_command()) if gf.days else "(no days)"
            lines.append(
                f"gridrad fan-out: days={gf.day_count} max_concurrent={gf.max_concurrent} "
                f"family={gf.family} cpu={gf.cpu} mem={gf.memory} "
                f"missing_only={gf.missing_only} post_manifest={gf.post_manifest_rebuild}"
            )
            lines.append(f"  sample cmd: {sample}")
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


@dataclass(frozen=True)
class FanoutOverrides:
    """CLI / caller overrides for GridRad fan-out planning."""

    enabled: bool | None = None
    from_date: date | None = None
    until_date: date | None = None
    max_concurrent: int | None = None


def _planned(spec: TaskSpec, *, container_name: str = "hail") -> PlannedTask:
    return PlannedTask(
        name=spec.name,
        family=spec.family,
        command=list(spec.command),
        cpu=spec.cpu,
        memory=spec.memory,
        ephemeral_storage_gib=spec.ephemeral_storage_gib,
        override_command=False,
        container_name=container_name,
    )


def _effective_fanout(
    config: PipelineConfig,
    overrides: FanoutOverrides | None,
) -> GridradFanoutSpec:
    base = config.gridrad_fanout
    if overrides is None:
        return base
    enabled = base.enabled if overrides.enabled is None else overrides.enabled
    return GridradFanoutSpec(
        enabled=enabled,
        task=base.task,
        max_concurrent=(
            base.max_concurrent
            if overrides.max_concurrent is None
            else overrides.max_concurrent
        ),
        from_date=overrides.from_date if overrides.from_date is not None else base.from_date,
        until_date=(
            overrides.until_date if overrides.until_date is not None else base.until_date
        ),
        missing_only=base.missing_only,
        with_04b_download=base.with_04b_download,
        workers=base.workers,
        download_workers=base.download_workers,
        cancel_day_siblings_on_failure=base.cancel_day_siblings_on_failure,
        post_manifest_rebuild=base.post_manifest_rebuild,
        container_name=base.container_name,
    )


def _build_gridrad_fanout_plan(
    config: PipelineConfig,
    fanout: GridradFanoutSpec,
) -> GridradFanoutPlan:
    start, end = resolve_gap_window(
        from_date=fanout.from_date,
        until_date=fanout.until_date,
    )
    days = iter_convective_days(start, end)
    spec = config.tasks[fanout.task]
    return GridradFanoutPlan(
        task_name=fanout.task,
        family=spec.family,
        cpu=spec.cpu,
        memory=spec.memory,
        ephemeral_storage_gib=spec.ephemeral_storage_gib,
        days=days,
        max_concurrent=fanout.max_concurrent,
        missing_only=fanout.missing_only,
        with_04b_download=fanout.with_04b_download,
        workers=fanout.workers,
        download_workers=fanout.download_workers,
        cancel_day_siblings_on_failure=fanout.cancel_day_siblings_on_failure,
        post_manifest_rebuild=fanout.post_manifest_rebuild,
        container_name=fanout.container_name,
    )


def build_plan(
    config: PipelineConfig,
    mode: Mode,
    *,
    fanout_overrides: FanoutOverrides | None = None,
) -> WorkflowPlan:
    if mode not in ("full", "downloads-only", "finalize", "dry-run"):
        raise ValueError(f"Unknown mode: {mode}")

    parallel: list[PlannedTask] = []
    finalize: PlannedTask | None = None
    gridrad: GridradFanoutPlan | None = None
    effective: Mode = "full" if mode == "dry-run" else mode
    fanout = _effective_fanout(config, fanout_overrides)

    if effective in ("full", "downloads-only"):
        for name in config.parallel_downloads:
            if fanout.enabled and name == fanout.task:
                continue
            parallel.append(_planned(config.tasks[name]))
        if fanout.enabled:
            gridrad = _build_gridrad_fanout_plan(config, fanout)
    if effective in ("full", "finalize"):
        finalize = _planned(config.tasks[config.finalize_task])

    return WorkflowPlan(
        mode=mode,
        parallel=parallel,
        gridrad_fanout=gridrad,
        finalize=finalize,
    )


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
    command = planned.command if planned.override_command else None
    return client.run_task(
        cluster=cluster,
        task_definition=task_def,
        subnets=subnets,
        security_groups=security_groups,
        assign_public_ip=assign_public_ip,
        started_by=started_by,
        task_name=planned.name,
        command=command,
        container_name=planned.container_name,
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


def _planned_day(gf: GridradFanoutPlan, day: date) -> PlannedTask:
    cmd = build_day_command(
        day,
        with_04b_download=gf.with_04b_download,
        workers=gf.workers,
        download_workers=gf.download_workers,
        missing_only=gf.missing_only,
    )
    return PlannedTask(
        name=day_task_name(day),
        family=gf.family,
        command=cmd.argv,
        cpu=gf.cpu,
        memory=gf.memory,
        ephemeral_storage_gib=gf.ephemeral_storage_gib,
        override_command=True,
        container_name=gf.container_name,
    )


def _run_downloads_with_fanout(
    client: EcsWorkflowClient,
    plan: WorkflowPlan,
    *,
    config: PipelineConfig,
    cluster: str,
    subnets: list[str],
    security_groups: list[str],
    outputs: dict[str, str],
    started_by: str,
    sleep_fn: SleepFn,
) -> tuple[list[TaskOutcome], list[str]]:
    """Run family downloads + GridRad day pool with bounded concurrency."""
    gf = plan.gridrad_fanout
    assert gf is not None

    outcomes: list[TaskOutcome] = []
    cancelled: list[str] = []
    pending: dict[str, RunningTask] = {}
    name_by_arn: dict[str, str] = {}
    is_day_task: dict[str, bool] = {}
    day_queue: deque[date] = deque(gf.days)
    family_failed = False
    day_failed = False
    cancel_issued = False

    def _start(planned: PlannedTask, *, day: bool) -> None:
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
        pending[rt.task_arn] = rt
        name_by_arn[rt.task_arn] = rt.task_name
        is_day_task[rt.task_arn] = day

    for planned in plan.parallel:
        _start(planned, day=False)

    def _fill_day_slots() -> None:
        running_days = sum(1 for arn in pending if is_day_task.get(arn))
        while day_queue and running_days < gf.max_concurrent:
            day = day_queue.popleft()
            _start(_planned_day(gf, day), day=True)
            running_days += 1

    _fill_day_slots()

    while pending:
        descs = client.describe_tasks(cluster, list(pending.keys()))
        by_arn = {d["taskArn"]: d for d in descs}
        finished: list[str] = []
        for arn, rt in list(pending.items()):
            desc = by_arn.get(arn)
            if not desc or desc.get("lastStatus") != "STOPPED":
                continue
            name = name_by_arn.get(arn, rt.task_name)
            outcome = client.outcome_from_description(name, desc)
            outcomes.append(outcome)
            finished.append(arn)
            if not outcome.succeeded:
                if is_day_task.get(arn):
                    day_failed = True
                else:
                    family_failed = True
        for arn in finished:
            del pending[arn]
            is_day_task.pop(arn, None)

        should_cancel_all = (
            family_failed
            and config.cancel_siblings_on_failure
            and not cancel_issued
        )
        should_cancel_days = (
            day_failed
            and gf.cancel_day_siblings_on_failure
            and not cancel_issued
            and not should_cancel_all
        )
        if should_cancel_all or should_cancel_days:
            day_queue.clear()
            for arn, rt in list(pending.items()):
                if should_cancel_days and not is_day_task.get(arn):
                    continue
                client.stop_task(
                    cluster,
                    arn,
                    reason="Sibling download task failed; cancelling remaining downloads",
                )
                cancelled.append(rt.task_name)
            cancel_issued = True

        if (family_failed and config.cancel_siblings_on_failure) or (day_failed and gf.cancel_day_siblings_on_failure):
            day_queue.clear()
        else:
            _fill_day_slots()

        if pending:
            sleep_fn(float(config.poll_seconds))

    if gf.post_manifest_rebuild:
        mt = gf.manifest_task()
        rt = _launch(
            client,
            planned=mt,
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
    fanout_overrides: FanoutOverrides | None = None,
) -> WorkflowResult:
    plan = build_plan(config, mode, fanout_overrides=fanout_overrides)
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

    if plan.parallel or plan.gridrad_fanout is not None:
        if plan.gridrad_fanout is not None:
            batch, cancelled = _run_downloads_with_fanout(
                client,
                plan,
                config=config,
                cluster=cluster,
                subnets=subnets,
                security_groups=security_groups,
                outputs=outputs,
                started_by=started_by,
                sleep_fn=sleep_fn,
            )
            outcomes.extend(batch)
        else:
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
