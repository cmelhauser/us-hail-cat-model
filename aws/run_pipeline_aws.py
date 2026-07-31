#!/usr/bin/env python3
"""run_pipeline_aws.py — local orchestrator for ECS Fargate pipeline runs.

Does not modify stage scripts. Submits RunTask calls against infrastructure
deployed by aws/cdk, using aws/config/pipeline.yaml as the parameter source.

Usage:
    python aws/run_pipeline_aws.py --mode full
    python aws/run_pipeline_aws.py --mode downloads-only
    python aws/run_pipeline_aws.py --mode finalize
    python aws/run_pipeline_aws.py --dry-run
    python aws/run_pipeline_aws.py --dry-run --gridrad-from-date 2015-05-20 \\
        --gridrad-until-date 2015-05-21
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


def _ensure_aws_on_path(aws_root: Path | None = None) -> None:
    """Allow `python aws/run_pipeline_aws.py` without installing the package."""
    root = aws_root or Path(__file__).resolve().parent
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_ensure_aws_on_path()

from hail_aws.config import ConfigError, default_config_path, load_pipeline_config
from hail_aws.ecs_client import EcsWorkflowClient
from hail_aws.gridrad_fanout import parse_iso_date
from hail_aws.orchestrator import FanoutOverrides, Mode, build_plan, run_workflow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the CONUS hail pipeline on AWS ECS Fargate."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to pipeline.yaml (default: aws/config/pipeline.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "downloads-only", "finalize", "dry-run"],
        default="full",
        help="Workflow mode (default: full)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for --mode dry-run",
    )
    parser.add_argument(
        "--stack-name",
        default=None,
        help="CloudFormation stack name (default: {project}-{environment})",
    )
    parser.add_argument(
        "--endpoint-url",
        default=None,
        help="Optional AWS endpoint URL (e.g. LocalStack http://localhost:4566)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Override region from YAML",
    )
    parser.add_argument(
        "--gridrad-from-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Override GridRad fan-out start (inclusive convective day)",
    )
    parser.add_argument(
        "--gridrad-until-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Override GridRad fan-out end (inclusive convective day)",
    )
    parser.add_argument(
        "--gridrad-max-concurrent",
        type=int,
        default=None,
        metavar="N",
        help="Override max concurrent GridRad day tasks",
    )
    parser.add_argument(
        "--no-gridrad-fanout",
        action="store_true",
        help="Disable one-day-per-task fan-out (monolithic download_gridrad task)",
    )
    return parser.parse_args(argv)


def _fanout_overrides(args: argparse.Namespace) -> FanoutOverrides:
    from_d: date | None = None
    until_d: date | None = None
    if args.gridrad_from_date:
        from_d = parse_iso_date(args.gridrad_from_date)
    if args.gridrad_until_date:
        until_d = parse_iso_date(args.gridrad_until_date)
    enabled: bool | None = False if args.no_gridrad_fanout else None
    return FanoutOverrides(
        enabled=enabled,
        from_date=from_d,
        until_date=until_d,
        max_concurrent=args.gridrad_max_concurrent,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode: Mode = "dry-run" if args.dry_run else args.mode  # type: ignore[assignment]
    cfg_path = args.config or default_config_path()

    try:
        config = load_pipeline_config(cfg_path)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    region = args.region or config.region
    overrides = _fanout_overrides(args)

    try:
        plan = build_plan(config, mode, fanout_overrides=overrides)
    except ValueError as exc:
        print(f"Plan error: {exc}", file=sys.stderr)
        return 2

    print("Workflow plan:")
    for line in plan.summary_lines():
        print(f"  {line}")

    if mode == "dry-run":
        print("Dry run complete — no ECS tasks submitted.")
        return 0

    client = EcsWorkflowClient(region=region, endpoint_url=args.endpoint_url)
    result = run_workflow(
        config,
        mode,
        client=client,
        stack_name=args.stack_name,
        fanout_overrides=overrides,
    )

    print("\nOutcomes:")
    for o in result.outcomes:
        status = "OK" if o.succeeded else "FAIL"
        print(
            f"  [{status}] {o.task_name} exit={o.exit_code} "
            f"reason={o.stopped_reason or '-'}"
        )
    if result.cancelled:
        print(f"Cancelled: {', '.join(result.cancelled)}")

    if result.ok:
        print("\nWorkflow completed successfully.")
        return 0

    print("\nWorkflow failed.", file=sys.stderr)
    print("Resume tips:", file=sys.stderr)
    print(
        "  python aws/run_pipeline_aws.py --mode downloads-only "
        "# GridRad uses --missing-only by default",
        file=sys.stderr,
    )
    print("  python aws/run_pipeline_aws.py --mode finalize", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
