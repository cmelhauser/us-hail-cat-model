"""AWS Fargate adapter library for the CONUS hail cat model pipeline."""

from __future__ import annotations

from hail_aws.config import ConfigError, PipelineConfig, default_config_path, load_pipeline_config
from hail_aws.orchestrator import WorkflowPlan, WorkflowResult, build_plan, run_workflow

__all__ = [
    "ConfigError",
    "PipelineConfig",
    "WorkflowPlan",
    "WorkflowResult",
    "build_plan",
    "default_config_path",
    "load_pipeline_config",
    "run_workflow",
]

__version__ = "0.1.0"
