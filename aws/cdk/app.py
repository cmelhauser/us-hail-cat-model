"""CDK app entry for the hail pipeline Fargate stack."""

from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk

# Make hail_aws importable when running `cdk` from aws/cdk.
_AWS_ROOT = Path(__file__).resolve().parents[1]
if str(_AWS_ROOT) not in sys.path:
    sys.path.insert(0, str(_AWS_ROOT))

from hail_aws.config import default_config_path, load_pipeline_config
from stacks.hail_pipeline_stack import HailPipelineStack


def main() -> None:
    config_path = Path(
        sys.argv[sys.argv.index("--config") + 1]
        if "--config" in sys.argv
        else default_config_path()
    )
    # Strip custom arg so CDK CLI does not see it.
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        del sys.argv[idx : idx + 2]

    config = load_pipeline_config(config_path)
    app = cdk.App()
    HailPipelineStack(
        app,
        f"{config.project_name}-{config.environment}",
        config=config,
        env=cdk.Environment(region=config.region),
    )
    app.synth()


if __name__ == "__main__":
    main()
