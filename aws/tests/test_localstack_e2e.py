"""LocalStack E2E: laptop-orchestrated downloads-only and full workflows.

Requires LocalStack Community 4.14 on localhost:4566 (see
aws/docker-compose.localstack.yml). These tests do **not** run real MESH
downloads; they exercise RunTask + laptop polling against a provisioned ECS
surface. Community LocalStack does not fully emulate Fargate + EFS.

There is no AWS-only (Step Functions) orchestrator in v1 — the supported path
is always the laptop CLI monitoring Fargate tasks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

AWS_ROOT = Path(__file__).resolve().parents[1]
if str(AWS_ROOT) not in sys.path:
    sys.path.insert(0, str(AWS_ROOT))

boto3 = pytest.importorskip("boto3")

from hail_aws.config import load_pipeline_config
from hail_aws.ecs_client import EcsWorkflowClient
from hail_aws.localstack_support import (
    provision_workflow_surface,
    start_task_completer,
    wait_for_localstack,
)
from hail_aws.orchestrator import build_plan, run_workflow
import run_pipeline_aws as cli

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
LS_CONFIG = AWS_ROOT / "config" / "pipeline.localstack.yaml"


@pytest.fixture(scope="module")
def localstack_env():
    try:
        wait_for_localstack(ENDPOINT, timeout_s=30.0)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"LocalStack not reachable at {ENDPOINT}: {exc}")

    # ECS is Pro-licensed on LocalStack Community 4.x — probe early.
    ecs = boto3.client(
        "ecs",
        endpoint_url=ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    try:
        ecs.list_clusters()
    except Exception as exc:  # pragma: no cover
        pytest.skip(
            "LocalStack Community does not include ECS (Pro license required). "
            f"Use aws/tests/test_laptop_orchestrator_e2e.py for laptop orchestrator E2E. ({exc})"
        )

    cfg = load_pipeline_config(LS_CONFIG)
    env = provision_workflow_surface(cfg, endpoint_url=ENDPOINT)
    stop_evt, thread = start_task_completer(
        endpoint_url=ENDPOINT,
        region=cfg.region,
        cluster=env.cluster,
    )
    yield cfg, env
    stop_evt.set()
    thread.join(timeout=5.0)


@pytest.mark.localstack
def test_localstack_downloads_only_laptop_monitor(localstack_env) -> None:
    cfg, env = localstack_env
    plan = build_plan(cfg, "downloads-only")
    assert len(plan.parallel) == 2
    assert plan.gridrad_fanout is not None
    assert plan.gridrad_fanout.day_count == 2
    assert plan.finalize is None

    client = EcsWorkflowClient(
        region=cfg.region,
        endpoint_url=ENDPOINT,
        session=boto3.session.Session(
            region_name=cfg.region,
            aws_access_key_id="test",
            aws_secret_access_key="test",
        ),
    )
    # Prefer explicit outputs; also verify CFN path works.
    cfn_outs = client.stack_outputs(env.stack_name)
    assert "SubnetIds" in cfn_outs
    assert "TaskSecurityGroupId" in cfn_outs

    result = run_workflow(
        cfg,
        "downloads-only",
        client=client,
        stack_name=env.stack_name,
        sleep_fn=lambda _s: __import__("time").sleep(0.2),
    )
    assert result.ok, [(o.task_name, o.exit_code, o.stopped_reason) for o in result.outcomes]
    names = {o.task_name for o in result.outcomes}
    assert "download_myrorss" in names
    assert "download_mrms" in names
    assert "download_gridrad_manifest" in names
    assert any(n.startswith("download_gridrad_20") for n in names)
    assert all(o.succeeded for o in result.outcomes)


@pytest.mark.localstack
def test_localstack_full_laptop_monitor(localstack_env) -> None:
    cfg, env = localstack_env
    plan = build_plan(cfg, "full")
    assert len(plan.parallel) == 2
    assert plan.gridrad_fanout is not None
    assert plan.finalize is not None

    client = EcsWorkflowClient(
        region=cfg.region,
        endpoint_url=ENDPOINT,
        session=boto3.session.Session(
            region_name=cfg.region,
            aws_access_key_id="test",
            aws_secret_access_key="test",
        ),
    )
    result = run_workflow(
        cfg,
        "full",
        client=client,
        stack_name=env.stack_name,
        sleep_fn=lambda _s: __import__("time").sleep(0.2),
    )
    assert result.ok, [(o.task_name, o.exit_code, o.stopped_reason) for o in result.outcomes]
    names = [o.task_name for o in result.outcomes]
    assert "download_myrorss" in names
    assert "download_mrms" in names
    assert names[-1] == "finalize"
    assert len(result.outcomes) == 6


@pytest.mark.localstack
def test_localstack_cli_downloads_only(localstack_env, capsys) -> None:
    """Laptop CLI path: run_pipeline_aws.py --mode downloads-only --endpoint-url."""
    _cfg, env = localstack_env
    code = cli.main(
        [
            "--config",
            str(LS_CONFIG),
            "--mode",
            "downloads-only",
            "--endpoint-url",
            ENDPOINT,
            "--stack-name",
            env.stack_name,
            "--region",
            "us-east-1",
        ]
    )
    out = capsys.readouterr().out
    assert "Workflow plan:" in out
    assert "parallel downloads" in out
    assert code == 0, out
    assert "Workflow completed successfully" in out


@pytest.mark.localstack
def test_localstack_cli_full(localstack_env, capsys) -> None:
    _cfg, env = localstack_env
    code = cli.main(
        [
            "--config",
            str(LS_CONFIG),
            "--mode",
            "full",
            "--endpoint-url",
            ENDPOINT,
            "--stack-name",
            env.stack_name,
            "--region",
            "us-east-1",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert "finalize:" in out
    assert "Workflow completed successfully" in out


@pytest.mark.localstack
def test_aws_only_orchestration_not_implemented() -> None:
    """Documented gap: v1 has no Step Functions / EventBridge 'AWS-only' runner.

    Speedup still uses Fargate tasks, but the control plane is the laptop CLI
    (poll DescribeTasks). This test locks that contract so we do not pretend
    LocalStack covers an AWS-only orchestrator that does not exist yet.
    """
    src = (AWS_ROOT / "run_pipeline_aws.py").read_text(encoding="utf-8")
    assert "Step Functions" not in src
    assert "--endpoint-url" in src
    readme = (AWS_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Step Functions" in readme  # listed under "What this does not do"
