# AWS Fargate adapter for the CONUS hail cat model

Optional cloud runner for the existing 14-stage pipeline. **Stage scripts and
`run_pipeline.py` are not modified.** This package deploys infrastructure with
CDK and submits ECS Fargate tasks from a laptop CLI.

Design: [`docs/superpowers/specs/2026-07-17-aws-fargate-adapter-design.md`](../docs/superpowers/specs/2026-07-17-aws-fargate-adapter-design.md).  
Reproduction notes: [`docs/reproduce.md`](../docs/reproduce.md) §14.

## Layout

| Path | Role |
|------|------|
| `config/pipeline.yaml` | Deploy + runtime parameters (single source of truth) |
| `cdk/` | Python CDK app (`HailPipelineStack`) |
| `hail_aws/` | Typed YAML loader, ECS client, workflow orchestrator |
| `run_pipeline_aws.py` | Local CLI (`full` / `downloads-only` / `finalize` / `dry-run`) |
| `docker-compose.localstack.yml` | LocalStack **Community `4.14.0`** (not `latest` / Pro) |
| `tests/` | Unit + optional LocalStack tests (**100%** coverage on `hail_aws` + CLI) |

## Workflow

```text
Laptop: run_pipeline_aws.py
    │  RunTask ×3 in parallel
    ▼
Fargate: 01 MYRORSS | 02 MRMS | 04c GridRad
    │  shared EFS → /app/data, /app/logs, /app/docs/figures
    ▼
Fargate: finalize (03, 04a, 05–14; skip standalone 04b)
```

Default Fargate sizes are in `pipeline.yaml` (tuned from production logs; GridRad
is the wall-clock critical path).

## Install

From the repository root:

```bash
pip install -e ".[aws]"
# or: pip install -r aws/cdk/requirements.txt
```

Extras include PyYAML, boto3, and aws-cdk-lib. CDK synth/deploy also needs
**Node.js** (jsii).

## Deploy

```bash
cd aws/cdk
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap   # once per account/region
cdk deploy
```

Then build and push the **repo root** `Dockerfile` to the ECR repository named in
stack outputs / `pipeline.yaml` (`image.repository_name` + `image.tag`).

Put CDS and NCAR credentials in AWS Secrets Manager; set
`secrets.cdsapi_secret_arn` and `secrets.ncar_rda_secret_arn` in
`pipeline.yaml` before production runs (never commit secret values).

## Run

```bash
python aws/run_pipeline_aws.py --dry-run
python aws/run_pipeline_aws.py --mode full
python aws/run_pipeline_aws.py --mode downloads-only
python aws/run_pipeline_aws.py --mode finalize
```

Useful flags: `--config`, `--stack-name`, `--region`, `--endpoint-url` (LocalStack).

The orchestrator is **local** (boto3 poll). Keep the process running for long
download stages, or resume with `--mode downloads-only` / `--mode finalize`.

## Test

```bash
# Unit tests + 100% coverage gate (no AWS account)
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 \
  pytest -q aws/tests -m 'not localstack' \
  --cov=hail_aws --cov=run_pipeline_aws --cov-fail-under=100

# Laptop orchestrator E2E (downloads-only + full) — stub ECS client, no AWS/Pro
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 \
  pytest -q aws/tests/test_laptop_orchestrator_e2e.py

# CDK synth (requires Node.js; skipped if node is missing)
PYTHONPATH=aws:aws/cdk pytest -q aws/tests/test_cdk_stack.py -m 'not localstack'

# Optional LocalStack Community 4.14.0 (STS/IAM/CFN smoke only — ECS is Pro-gated)
docker compose -f aws/docker-compose.localstack.yml up -d
AWS_ENDPOINT_URL=http://localhost:4566 PYTHONPATH=aws \
  pytest -q aws/tests -m localstack
```

```bash
ruff check aws
```

## Orchestration model (important)

v1 always uses a **laptop process** (`run_pipeline_aws.py`) that submits Fargate
`RunTask` calls and polls `DescribeTasks` until STOPPED. There is **no**
Step Functions / EventBridge “AWS-only” control plane yet (see below). Keep the
CLI process alive for long downloads, or resume with `--mode downloads-only` /
`--mode finalize`.

## Coverage policy

- **`aws/hail_aws` + `run_pipeline_aws.py`:** fail under **100%** line coverage
  (`localstack_support.py` omitted — LocalStack Pro–only helpers).
- **`scripts/`:** separate floor in `pyproject.toml` (I/O-heavy stages); not part of
  this adapter’s gate.

## What this does not do

- Step Functions / EventBridge orchestration (future option) — no AWS-only runner
- Fargate Spot in v1
- Full LocalStack Community emulation of Fargate + EFS (ECS is Pro-licensed in 4.x;
  use `test_laptop_orchestrator_e2e.py` for laptop-monitor workflow coverage)
- Changes to MESH methodology or stage CLI contracts
