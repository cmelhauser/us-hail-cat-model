"""CDK stack unit tests (synth) and LocalStack-marked stubs.

Requires Node.js for aws-cdk jsii. Skips cleanly when node is absent.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

if shutil.which("node") is None:
    pytest.skip("Node.js required for aws-cdk jsii runtime", allow_module_level=True)

AWS_ROOT = Path(__file__).resolve().parents[1]
CDK_ROOT = AWS_ROOT / "cdk"
for p in (AWS_ROOT, CDK_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

aws_cdk = pytest.importorskip("aws_cdk")
cdk = aws_cdk
from aws_cdk.assertions import Template
from hail_aws.config import load_pipeline_config
from stacks.hail_pipeline_stack import HailPipelineStack


def test_stack_synth_creates_core_resources(config_path: Path) -> None:
    cfg = load_pipeline_config(config_path)
    app = cdk.App()
    stack = HailPipelineStack(
        app,
        "TestHailStack",
        config=cfg,
        env=cdk.Environment(account="123456789012", region=cfg.region),
    )
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::ECS::Cluster", 1)
    template.resource_count_is("AWS::ECR::Repository", 1)
    template.resource_count_is("AWS::EFS::FileSystem", 1)
    template.resource_count_is("AWS::ECS::TaskDefinition", 4)
    template.has_output("ClusterName", {})
    template.has_output("SubnetIds", {})
    template.has_output("TaskSecurityGroupId", {})


def test_stack_with_secret_arns(minimal_yaml: Path) -> None:
    import yaml

    data = yaml.safe_load(minimal_yaml.read_text(encoding="utf-8"))
    data["secrets"]["cdsapi_secret_arn"] = (
        "arn:aws:secretsmanager:us-east-1:123456789012:secret:cds"
    )
    data["secrets"]["ncar_rda_secret_arn"] = (
        "arn:aws:secretsmanager:us-east-1:123456789012:secret:ncar"
    )
    minimal_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_pipeline_config(minimal_yaml)
    app = cdk.App()
    stack = HailPipelineStack(app, "TestSecrets", config=cfg)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::ECS::TaskDefinition", 4)
    # Secrets Manager fields must be injected as container secrets (not IAM-only).
    resources = template.to_json()["Resources"]
    task_defs = [
        r for r in resources.values() if r["Type"] == "AWS::ECS::TaskDefinition"
    ]
    secrets_keys: set[str] = set()
    for td in task_defs:
        for container in td["Properties"]["ContainerDefinitions"]:
            for secret in container.get("Secrets") or []:
                secrets_keys.add(secret["Name"])
    assert {"CDSAPI_URL", "CDSAPI_KEY", "GDEX_TOKEN"} <= secrets_keys


@pytest.mark.localstack
def test_localstack_sts_caller_identity() -> None:
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    boto3 = pytest.importorskip("boto3")
    try:
        sts = boto3.client("sts", endpoint_url=endpoint, region_name="us-east-1")
        ident = sts.get_caller_identity()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"LocalStack not reachable at {endpoint}: {exc}")
    assert "Account" in ident
