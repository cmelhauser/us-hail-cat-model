"""LocalStack Community helpers for ECS Fargate workflow E2E tests.

Community LocalStack does not fully emulate Fargate + EFS mounts. These helpers
provision the minimum ECS/CFN surface the laptop orchestrator needs, then
optionally complete tasks (stop with exit 0) so the monitoring loop can finish.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import boto3

from hail_aws.config import PipelineConfig


@dataclass(frozen=True)
class LocalStackEnv:
    endpoint_url: str
    region: str
    stack_name: str
    outputs: dict[str, str]
    cluster: str


def _client(service: str, *, endpoint_url: str, region: str) -> Any:
    return boto3.client(
        service,
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def wait_for_localstack(endpoint_url: str, *, timeout_s: float = 90.0) -> None:
    """Block until LocalStack responds to STS GetCallerIdentity."""
    deadline = time.time() + timeout_s
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            sts = _client("sts", endpoint_url=endpoint_url, region="us-east-1")
            sts.get_caller_identity()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(1.0)
    raise RuntimeError(f"LocalStack not ready at {endpoint_url}: {last_exc}")


def provision_workflow_surface(
    config: PipelineConfig,
    *,
    endpoint_url: str,
    stack_name: str | None = None,
) -> LocalStackEnv:
    """Create cluster, task definitions, and a CFN stack with orchestrator outputs.

    Uses tiny Fargate-legal task defs with a public busybox image. Real MESH
    downloads are not executed; this exercises RunTask, DescribeTasks, StopTask,
    CloudFormation stack_outputs, and the laptop poll loop.
    """
    region = config.region
    name = stack_name or f"{config.project_name}-{config.environment}-ls"
    ecs = _client("ecs", endpoint_url=endpoint_url, region=region)
    ec2 = _client("ec2", endpoint_url=endpoint_url, region=region)
    cfn = _client("cloudformation", endpoint_url=endpoint_url, region=region)
    iam = _client("iam", endpoint_url=endpoint_url, region=region)

    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.1.0/24")["Subnet"]["SubnetId"]
    sg = ec2.create_security_group(
        GroupName=f"hail-ls-{int(time.time())}",
        Description="localstack hail tasks",
        VpcId=vpc,
    )["GroupId"]

    with contextlib.suppress(Exception):
        iam.create_role(
            RoleName="hailLocalstackEcsExecution",
            AssumeRolePolicyDocument=(
                '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
                '"Principal":{"Service":"ecs-tasks.amazonaws.com"},'
                '"Action":"sts:AssumeRole"}]}'
            ),
        )
    exec_role_arn = iam.get_role(RoleName="hailLocalstackEcsExecution")["Role"]["Arn"]

    cluster_name = f"{config.cluster_name}-ls"
    with contextlib.suppress(Exception):
        ecs.create_cluster(clusterName=cluster_name)

    outputs: dict[str, str] = {
        "ClusterName": cluster_name,
        "SubnetIds": subnet,
        "TaskSecurityGroupId": sg,
    }

    for _task_name, spec in config.tasks.items():
        family = spec.family
        td = ecs.register_task_definition(
            family=family,
            requiresCompatibilities=["FARGATE"],
            networkMode="awsvpc",
            cpu="256",
            memory="512",
            executionRoleArn=exec_role_arn,
            containerDefinitions=[
                {
                    "name": "hail",
                    "image": "public.ecr.aws/docker/library/busybox:1.36",
                    "essential": True,
                    "command": ["sh", "-c", "echo hail-localstack-ok; exit 0"],
                }
            ],
        )
        td_arn = td["taskDefinition"]["taskDefinitionArn"]
        outputs[f"TaskDef{family}"] = td_arn

    resources = {
        "DummyBucket": {
            "Type": "AWS::S3::Bucket",
            "Properties": {"BucketName": f"{name.lower().replace('_', '-')}-dummy"},
        }
    }
    cfn_outputs = {
        key: {"Value": value, "Description": key} for key, value in outputs.items()
    }
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Resources": resources,
        "Outputs": cfn_outputs,
    }

    with contextlib.suppress(Exception):
        cfn.delete_stack(StackName=name)
        time.sleep(1.0)
    cfn.create_stack(StackName=name, TemplateBody=json.dumps(template))
    for _ in range(40):
        st = cfn.describe_stacks(StackName=name)["Stacks"][0]["StackStatus"]
        if "COMPLETE" in st or "FAILED" in st:
            break
        time.sleep(0.5)

    with contextlib.suppress(Exception):
        stack_outs = {
            o["OutputKey"]: o["OutputValue"]
            for o in cfn.describe_stacks(StackName=name)["Stacks"][0].get("Outputs")
            or []
        }
        if stack_outs:
            outputs.update(stack_outs)

    return LocalStackEnv(
        endpoint_url=endpoint_url,
        region=region,
        stack_name=name,
        outputs=outputs,
        cluster=cluster_name,
    )


def start_task_completer(
    *,
    endpoint_url: str,
    region: str,
    cluster: str,
    poll_seconds: float = 0.4,
) -> tuple[threading.Event, threading.Thread]:
    """Background helper: stop non-terminal tasks so the laptop poll loop finishes.

    Community LocalStack often leaves Fargate tasks non-terminal. The orchestrator
    polls until STOPPED; this completer makes that loop finish.
    """
    stop = threading.Event()
    ecs = _client("ecs", endpoint_url=endpoint_url, region=region)

    def _loop() -> None:
        while not stop.is_set():
            try:
                listed = ecs.list_tasks(cluster=cluster)
                arns = listed.get("taskArns") or []
                if arns:
                    descs = ecs.describe_tasks(cluster=cluster, tasks=arns).get("tasks") or []
                    for t in descs:
                        status = t.get("lastStatus")
                        arn = t.get("taskArn")
                        if status in ("RUNNING", "PENDING", "PROVISIONING") and arn:
                            with contextlib.suppress(Exception):
                                ecs.stop_task(
                                    cluster=cluster,
                                    task=arn,
                                    reason="localstack-e2e-completer",
                                )
            except Exception:
                pass
            stop.wait(poll_seconds)

    thread = threading.Thread(target=_loop, name="ls-task-completer", daemon=True)
    thread.start()
    return stop, thread
