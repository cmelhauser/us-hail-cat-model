"""Typed loader and validation for aws/config/pipeline.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Fargate CPU → allowed memory (MiB) pairs (AWS docs).
_FARGATE_CPU_MEMORY: dict[int, set[int]] = {
    256: {512, 1024, 2048},
    512: {1024, 2048, 3072, 4096},
    1024: {2048, 3072, 4096, 5120, 6144, 7168, 8192},
    2048: set(range(4096, 16385, 1024)),
    4096: set(range(8192, 30721, 1024)),
    8192: set(range(16384, 61441, 4096)),
    16384: set(range(32768, 122881, 8192)),
}


class ConfigError(ValueError):
    """Invalid pipeline YAML."""


@dataclass(frozen=True)
class TaskSpec:
    name: str
    family: str
    cpu: int
    memory: int
    ephemeral_storage_gib: int
    command: list[str]
    stage: str | None = None


@dataclass(frozen=True)
class PipelineConfig:
    raw: dict[str, Any]
    path: Path
    project_name: str
    version: str
    environment: str
    region: str
    tags: dict[str, str]
    image_repository: str
    image_tag: str
    vpc_id: str | None
    subnet_ids: list[str]
    assign_public_ip: bool
    max_azs: int
    efs_encrypted: bool
    data_mount: str
    logs_mount: str
    figures_mount: str
    cluster_name: str
    log_group: str
    log_retention_days: int
    cancel_siblings_on_failure: bool
    cdsapi_secret_arn: str | None
    ncar_rda_secret_arn: str | None
    tasks: dict[str, TaskSpec]
    parallel_downloads: list[str]
    finalize_task: str
    poll_seconds: int
    stop_timeout_seconds: int
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def image_uri_suffix(self) -> str:
        return f"{self.image_repository}:{self.image_tag}"


def _require(mapping: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Missing required key '{key}' under {ctx}")
    return mapping[key]


def _as_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{name} must be an int, got {type(value).__name__}")
    return value


def _as_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def _as_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be a bool")
    return value


def _as_str_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ConfigError(f"{name} must be a list of non-empty strings")
    return list(value)


def validate_fargate_size(cpu: int, memory: int, task_name: str) -> None:
    allowed = _FARGATE_CPU_MEMORY.get(cpu)
    if allowed is None:
        raise ConfigError(
            f"Task '{task_name}': cpu={cpu} is not a valid Fargate CPU value "
            f"(allowed: {sorted(_FARGATE_CPU_MEMORY)})"
        )
    if memory not in allowed:
        raise ConfigError(
            f"Task '{task_name}': memory={memory} invalid for cpu={cpu}. "
            f"Allowed MiB: {sorted(allowed)}"
        )


def validate_ephemeral(gib: int, task_name: str) -> None:
    if gib < 20 or gib > 200:
        raise ConfigError(
            f"Task '{task_name}': ephemeral_storage_gib must be 20–200, got {gib}"
        )


def _parse_task(name: str, body: dict[str, Any]) -> TaskSpec:
    if not isinstance(body, dict):
        raise ConfigError(f"tasks.{name} must be a mapping")
    cpu = _as_int(_require(body, "cpu", f"tasks.{name}"), f"tasks.{name}.cpu")
    memory = _as_int(_require(body, "memory", f"tasks.{name}"), f"tasks.{name}.memory")
    ephemeral = _as_int(
        _require(body, "ephemeral_storage_gib", f"tasks.{name}"),
        f"tasks.{name}.ephemeral_storage_gib",
    )
    command = _require(body, "command", f"tasks.{name}")
    if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
        raise ConfigError(f"tasks.{name}.command must be a non-empty list of strings")
    family = _as_str(_require(body, "family", f"tasks.{name}"), f"tasks.{name}.family")
    stage = body.get("stage")
    if stage is not None:
        stage = _as_str(stage, f"tasks.{name}.stage")
    validate_fargate_size(cpu, memory, name)
    validate_ephemeral(ephemeral, name)
    return TaskSpec(
        name=name,
        family=family,
        cpu=cpu,
        memory=memory,
        ephemeral_storage_gib=ephemeral,
        command=list(command),
        stage=stage,
    )


def load_pipeline_config(path: str | Path) -> PipelineConfig:
    cfg_path = Path(path).expanduser().resolve()
    if not cfg_path.is_file():
        raise ConfigError(f"Config file not found: {cfg_path}")
    with cfg_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError("Pipeline config root must be a mapping")

    project = _require(raw, "project", "root")
    image = _require(raw, "image", "root")
    network = _require(raw, "network", "root")
    storage = _require(raw, "storage", "root")
    ecs = _require(raw, "ecs", "root")
    secrets = raw.get("secrets", {})
    tasks_raw = _require(raw, "tasks", "root")
    workflow = _require(raw, "workflow", "root")

    if not isinstance(project, dict):
        raise ConfigError("project must be a mapping")
    if not isinstance(image, dict):
        raise ConfigError("image must be a mapping")
    if not isinstance(network, dict):
        raise ConfigError("network must be a mapping")
    if not isinstance(storage, dict):
        raise ConfigError("storage must be a mapping")
    if not isinstance(ecs, dict):
        raise ConfigError("ecs must be a mapping")
    if not isinstance(secrets, dict):
        raise ConfigError("secrets must be a mapping")
    if not isinstance(tasks_raw, dict) or not tasks_raw:
        raise ConfigError("tasks must be a non-empty mapping")
    if not isinstance(workflow, dict):
        raise ConfigError("workflow must be a mapping")

    tags = project.get("tags") or {}
    if not isinstance(tags, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in tags.items()
    ):
        raise ConfigError("project.tags must be a string-to-string mapping")

    tasks = {name: _parse_task(name, body) for name, body in tasks_raw.items()}

    parallel = _as_str_list(
        _require(workflow, "parallel_downloads", "workflow"),
        "workflow.parallel_downloads",
    )
    finalize_name = _as_str(
        _require(workflow, "finalize_task", "workflow"),
        "workflow.finalize_task",
    )
    for name in parallel:
        if name not in tasks:
            raise ConfigError(f"workflow.parallel_downloads references unknown task '{name}'")
    if finalize_name not in tasks:
        raise ConfigError(f"workflow.finalize_task references unknown task '{finalize_name}'")

    vpc_id = network.get("vpc_id")
    if vpc_id is not None:
        vpc_id = _as_str(vpc_id, "network.vpc_id")
    subnet_ids = network.get("subnet_ids") or []
    if not isinstance(subnet_ids, list) or not all(isinstance(x, str) for x in subnet_ids):
        raise ConfigError("network.subnet_ids must be a list of strings")

    cds = secrets.get("cdsapi_secret_arn")
    ncar = secrets.get("ncar_rda_secret_arn")
    if cds is not None:
        cds = _as_str(cds, "secrets.cdsapi_secret_arn")
    if ncar is not None:
        ncar = _as_str(ncar, "secrets.ncar_rda_secret_arn")

    return PipelineConfig(
        raw=raw,
        path=cfg_path,
        project_name=_as_str(_require(project, "name", "project"), "project.name"),
        version=_as_str(_require(project, "version", "project"), "project.version"),
        environment=_as_str(_require(project, "environment", "project"), "project.environment"),
        region=_as_str(_require(project, "region", "project"), "project.region"),
        tags=dict(tags),
        image_repository=_as_str(
            _require(image, "repository_name", "image"), "image.repository_name"
        ),
        image_tag=_as_str(_require(image, "tag", "image"), "image.tag"),
        vpc_id=vpc_id,
        subnet_ids=list(subnet_ids),
        assign_public_ip=_as_bool(
            network.get("assign_public_ip", True), "network.assign_public_ip"
        ),
        max_azs=_as_int(network.get("max_azs", 2), "network.max_azs"),
        efs_encrypted=_as_bool(storage.get("efs_encrypted", True), "storage.efs_encrypted"),
        data_mount=_as_str(_require(storage, "data_mount", "storage"), "storage.data_mount"),
        logs_mount=_as_str(_require(storage, "logs_mount", "storage"), "storage.logs_mount"),
        figures_mount=_as_str(
            _require(storage, "figures_mount", "storage"), "storage.figures_mount"
        ),
        cluster_name=_as_str(_require(ecs, "cluster_name", "ecs"), "ecs.cluster_name"),
        log_group=_as_str(_require(ecs, "log_group", "ecs"), "ecs.log_group"),
        log_retention_days=_as_int(
            ecs.get("log_retention_days", 30), "ecs.log_retention_days"
        ),
        cancel_siblings_on_failure=_as_bool(
            ecs.get("cancel_siblings_on_failure", True),
            "ecs.cancel_siblings_on_failure",
        ),
        cdsapi_secret_arn=cds,
        ncar_rda_secret_arn=ncar,
        tasks=tasks,
        parallel_downloads=parallel,
        finalize_task=finalize_name,
        poll_seconds=_as_int(workflow.get("poll_seconds", 60), "workflow.poll_seconds"),
        stop_timeout_seconds=_as_int(
            workflow.get("stop_timeout_seconds", 120), "workflow.stop_timeout_seconds"
        ),
    )


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "pipeline.yaml"
