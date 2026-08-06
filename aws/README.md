# AWS Fargate adapter for the CONUS hail cat model

Optional cloud runner for the existing pipeline stages. **Stage scripts and
`run_pipeline.py` are not modified.** This package deploys infrastructure with
CDK and submits ECS Fargate tasks from a laptop CLI.

- Design: [`docs/superpowers/specs/2026-07-17-aws-fargate-adapter-design.md`](../docs/superpowers/specs/2026-07-17-aws-fargate-adapter-design.md)
- Reproduction: [`docs/reproduce.md`](../docs/reproduce.md) §14
- Agent notes: [`AGENTS.md`](../AGENTS.md) (AWS section)

## Layout

| Path | Role |
|------|------|
| `config/pipeline.yaml` | Deploy + runtime parameters (single source of truth) |
| `config/pipeline.localstack.yaml` | Tiny task sizes for LocalStack / stub E2E |
| `cdk/` | Python CDK app (`HailPipelineStack`) |
| `hail_aws/` | YAML loader, ECS client, orchestrator, LocalStack helpers |
| `run_pipeline_aws.py` | Laptop CLI (`full` / `downloads-only` / `finalize` / `dry-run`) |
| `docker-entrypoint.sh` | Writes `~/.cdsapirc` from `CDSAPI_*` env; execs `python` |
| `docker-compose.localstack.yml` | LocalStack **Community `4.14.0`** (not `latest` / Pro) |
| `tests/` | Unit + laptop E2E + CDK synth (**100%** on `hail_aws` + CLI) |

## Architecture

```text
Laptop: run_pipeline_aws.py          (poll DescribeTasks; no Step Functions)
    │  RunTask: 01 + 02 + GridRad day pool (bounded concurrency)
    ▼
Fargate: 01 MYRORSS | 02 MRMS | 04c × N days (2 vCPU / 16 GB each)
    │  shared EFS → /app/data, /app/logs, /app/docs/figures
    │  post-pass: 04c --manifest-only (rebuild manifest + gridrad_days.txt)
    ▼
Fargate: finalize (03, 04a, 05–14; skip standalone 04b)
```

Default Fargate sizes are in `pipeline.yaml`. **GridRad fan-out**
(`workflow.gridrad_fanout.enabled`) runs **one convective day per Fargate task**
(2012-01-01 → 2020-10-13) with `max_concurrent` (default **10**) for NCAR/GDEX
and EFS headroom. Staging (~8–12 GiB/day) lives on **EFS**, not ephemeral disk.
Day tasks use `scripts/04c_fill_gridrad_gap.py --from-date/--until-date` via ECS
`containerOverrides` (not `run_pipeline.py --only 04c`, which forces `--workers 4`).

**Orchestration model:** v1 always uses a **laptop process**. There is no
EventBridge / Step Functions control plane yet. Keep the CLI alive for long
downloads, or resume with `--mode downloads-only` / `--mode finalize`.
GridRad defaults to `--missing-only` so re-runs skip days that already have a
GeoTIFF.

## Prerequisites

| Requirement | Why |
|-------------|-----|
| Python 3.10+ | Adapter + CDK |
| Node.js 18+ | aws-cdk jsii runtime |
| Docker | Build/push the ECR image |
| AWS account + credentials | Deploy + RunTask |
| NCAR GDEX token | Stage 04b/04c GridRad |
| Copernicus CDS token + accepted ERA5 licences | Stage 04a |

Install adapter deps from the repository root:

```bash
pip install -e ".[aws]"
# CDK alone: pip install -r aws/cdk/requirements.txt
```

## 1. Create Secrets Manager secrets

Never commit secret values. Create two secrets (JSON), then paste the ARNs into
`aws/config/pipeline.yaml` under `secrets:`.

**CDS** (fields must be named `url` and `key` — injected as `CDSAPI_URL` /
`CDSAPI_KEY`; the container entrypoint writes `~/.cdsapirc`):

```bash
aws secretsmanager create-secret \
  --name hail-cdsapi \
  --secret-string '{"url":"https://cds.climate.copernicus.eu/api","key":"YOUR_CDS_TOKEN"}'
```

**NCAR / GDEX** (field must be named `token` — injected as `GDEX_TOKEN`):

```bash
aws secretsmanager create-secret \
  --name hail-ncar-rda \
  --secret-string '{"token":"YOUR_GDEX_TOKEN"}'
```

Copy the returned ARNs into `pipeline.yaml` (**must** include Secrets Manager’s
6-character suffix — CDK `from_secret_complete_arn` rejects partial ARNs):

```yaml
secrets:
  cdsapi_secret_arn: "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:hail-cdsapi-AbCdEf"
  ncar_rda_secret_arn: "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:hail-ncar-rda-XyZ123"
```

Leave both `null` only for CDK dry-run / infrastructure synth without credentials.

## 2. Deploy CDK stack

```bash
cd aws/cdk
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap          # once per account/region
cdk deploy
```

### Stack outputs (inventory)

| Output | Used for |
|--------|----------|
| `ClusterName` / `ClusterArn` | `run_pipeline_aws.py` target cluster |
| `RepositoryUri` | `docker push` destination |
| `SubnetIds` | Fargate `awsvpc` network config |
| `TaskSecurityGroupId` | Task ENI security group |
| `EfsId` | Shared data volume |
| `TaskDefhail-download-*` / `TaskDefhail-finalize` | Task definition ARNs |

The CLI resolves these via CloudFormation `describe_stacks` (or `--endpoint-url`
against LocalStack’s stub stack).

## 3. Build and push the image to ECR

From the **repository root** (not `aws/`):

```bash
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1
REPO=hail-cat-model
TAG=2.3.0

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker build -t "${REPO}:${TAG}" .
docker tag "${REPO}:${TAG}" \
  "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO}:${TAG}"
docker push \
  "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO}:${TAG}"
```

`image.repository_name` and `image.tag` in `pipeline.yaml` must match.

The image `ENTRYPOINT` is `aws/docker-entrypoint.sh`: it materializes CDS
credentials from env, then runs `python` (preserving the historical
`ENTRYPOINT ["python"]` contract for task `command` arrays).

## 4. Smoke ladder (spend control)

Do **not** start a full production download until each rung passes:

1. **Unit / laptop E2E (free):** see [Test](#test) below — no AWS spend.
2. **CDK deploy + empty dry-run:** `python aws/run_pipeline_aws.py --dry-run`
3. **One tiny task (optional):** temporarily point a task `command` at
   `run_pipeline.py --help` or `--dry-run`, redeploy task defs, RunTask once,
   confirm CloudWatch logs and EFS mounts.
4. **Downloads-only** on a date-bounded / resume-friendly window if you have
   stage flags for it; otherwise expect multi-day Fargate + EFS cost.
5. **Full** only after downloads succeed.

LocalStack Community **does not** prove Fargate/ECR/EFS spend paths (ECS is
Pro-licensed in 4.x). Use the laptop stub E2E for orchestration logic only.

## 5. Run

```bash
python aws/run_pipeline_aws.py --dry-run
python aws/run_pipeline_aws.py --mode full
python aws/run_pipeline_aws.py --mode downloads-only
python aws/run_pipeline_aws.py --mode finalize
```

Useful flags: `--config`, `--stack-name`, `--region`, `--endpoint-url` (LocalStack),
`--gridrad-from-date` / `--gridrad-until-date` / `--gridrad-max-concurrent`,
`--no-gridrad-fanout` (monolithic single 04c task).

Smoke a two-day GridRad window before the full gap:

```bash
python aws/run_pipeline_aws.py --mode downloads-only \
  --gridrad-from-date 2015-05-20 --gridrad-until-date 2015-05-21
```

## Cost and teardown

- **Ongoing cost drivers:** Fargate vCPU/memory-hours (defaults are large), EFS
  storage, CloudWatch Logs, ECR storage, public IPv4 on task ENIs.
- **Not Free-tier friendly** at default sizes. Shrink `tasks.*.cpu` /
  `memory` / `ephemeral_storage_gib` in `pipeline.yaml` for experiments, then
  `cdk deploy` again.
- **Teardown (keeps EFS + ECR by default — RemovalPolicy.RETAIN):**

```bash
cd aws/cdk && cdk destroy
# Then manually delete retained EFS / ECR / Secrets if you no longer need them.
```

## Test

```bash
# Unit tests + 100% coverage gate (no AWS account)
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 \
  pytest -q aws/tests -m 'not localstack' \
  --ignore=aws/tests/test_cdk_stack.py \
  --cov=hail_aws --cov=run_pipeline_aws --cov-fail-under=100

# Laptop orchestrator E2E (downloads-only + full) — stub ECS, no AWS/Pro
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 \
  pytest -q aws/tests/test_laptop_orchestrator_e2e.py

# Entrypoint CDS materialization (bash; no Docker daemon)
PYTHONPATH=aws pytest -q aws/tests/test_docker_entrypoint.py

# CDK synth (requires Node.js)
PYTHONPATH=aws:aws/cdk pytest -q aws/tests/test_cdk_stack.py -m 'not localstack'

# Optional LocalStack Community 4.14.0 (STS/IAM/CFN smoke — ECS is Pro-gated)
docker compose -f aws/docker-compose.localstack.yml up -d
AWS_ENDPOINT_URL=http://localhost:4566 PYTHONPATH=aws \
  pytest -q aws/tests -m localstack
```

```bash
ruff check aws
```

CI job **`aws`** in `.github/workflows/tests.yml` enforces the 100% `hail_aws` +
CLI gate and CDK synth (with Node).

## Coverage policy

| Package | Gate |
|---------|------|
| `aws/hail_aws` + `run_pipeline_aws.py` | **100%** line coverage in CI |
| `aws/cdk` | Synth tests (not line-covered; jsii-generated) |
| `scripts/` + `run_pipeline.py` | **100%** statement coverage (`fail_under = 100` in `pyproject.toml`; same floor in CI and `./scripts/quality_gate.sh`) |

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|-------------------|
| Stage 04a `403` / licences | Accept ERA5 monthly licences on the CDS account that owns the token |
| Missing `~/.cdsapirc` in task | Secret ARN not set, wrong JSON field names (`url`/`key`), or image without entrypoint |
| GridRad auth failures | `GDEX_TOKEN` missing; secret field must be `token` |
| `RunTask` networking errors | Public subnets + `assign_public_ip: true` required without NAT |
| Orchestrator hangs | Laptop process killed; resume with `--mode downloads-only` or `--mode finalize` |
| LocalStack `RunTask` never STOPPED | Expected on Community; use stub E2E or Pro |
| Huge bill | Default task sizes / high `max_concurrent`; shrink YAML, destroy stack, delete retained EFS |
| Incomplete `gridrad_days.txt` | Fan-out post-pass runs `--manifest-only`; or re-run `scripts/04c_fill_gridrad_gap.py --manifest-only` on EFS |
| NCAR 429 / throttling | Lower `workflow.gridrad_fanout.max_concurrent` (start at 10) |

## What this does not do

- Step Functions / EventBridge orchestration (future option)
- Fargate Spot in v1
- Full LocalStack Community emulation of Fargate + EFS
- Changes to MESH methodology or stage CLI contracts
- Proof that a real AWS deploy will be cheap — only the laptop stub proves orchestration logic without spend
