# AWS Fargate Pipeline Adapter — Design Spec

**Date:** 2026-07-17  
**Status:** Approved for implementation  
**Scope:** Add-only `aws/` package. No changes to stage scripts or `run_pipeline.py` behavior.

## Goal

Deploy the CONUS hail pipeline on ECS Fargate with a cost/speed balance: parallel download tasks (MYRORSS, MRMS, GridRad), then one finalize task for remaining stages. Orchestration is a **local** Python CLI (`run_pipeline_aws.py`) that submits and polls ECS tasks via boto3.

## Non-goals

- Step Functions / EventBridge orchestration (future option)
- Modifying stage scripts for S3-native I/O
- Fargate Spot in v1 (resume/retry not yet durable enough for ~158 h GridRad)
- Claiming LocalStack Community fully emulates Fargate + EFS mounts

## Layout

```text
aws/
├── config/pipeline.yaml
├── cdk/                     # deployable infrastructure
├── hail_aws/                # library: config, ECS client, orchestrator
├── run_pipeline_aws.py      # CLI entry
├── docker-compose.localstack.yml
└── tests/
```

## Architecture

```text
Laptop CLI (run_pipeline_aws.py)
    │  RunTask ×3 (parallel)
    ▼
ECS Fargate ──► EFS (/app/data, /app/logs, /app/docs/figures)
  01 | 02 | 04c
    │  then RunTask ×1
    ▼
ECS Fargate finalize (03, 04a, 05–14)
```

Shared state lives on EFS so existing path assumptions (`data/`, `logs/`) work unchanged. Image is the existing root `Dockerfile`, pushed to ECR.

## Task sizing (from production logs)

| Task | vCPU | Memory | Ephemeral | Est. wall | Notes |
|------|-----:|-------:|----------:|-----------|-------|
| 01 MYRORSS | 4 | 16 GB | 100 GiB | ~8–20 h | S3 I/O; `--workers` tunable |
| 02 MRMS | 4–8 | 16–32 GB | 100 GiB | ~86 h local | Long but finishes inside GridRad wall |
| 04c GridRad (fan-out) | 2 | 16 GB | 50 GiB | ~hours–1 day wall @ concurrency 10 | One convective day per task; staging on EFS (~8–12 GiB/day) |
| finalize | 8 | 32 GB | 200 GiB | ~21 h | 05~8h + 10~5h + 13~7h + misc |

YAML is the single source of truth for sizing, commands, and workflow order.
`workflow.gridrad_fanout` expands Stage 04c into per-day RunTask overrides.

## AWS best practices (v1)

1. **Least-privilege IAM:** separate execution role (ECR pull, logs) and task role (EFS, Secrets Manager read).
2. **Secrets:** CDS / NCAR credentials in Secrets Manager; never in YAML or image.
3. **Encryption:** EFS encrypted at rest; CloudWatch logs encrypted with account default CMK.
4. **Network:** task SG → EFS SG on TCP 2049 only; outbound HTTPS for S3/NCAR/CDS. Public IP allowed in YAML for cost (no NAT); private+NAT optional later.
5. **Observability:** one log group, stream prefix per task family; container `awslogs` driver.
6. **Cost tags:** `Project`, `Component`, `Environment` on all resources.
7. **ECR:** repository with image-scan-on-push; pin tag from YAML.
8. **Ephemeral storage:** per-task GiB from YAML (Fargate 20–200).
9. **Idempotent CDK:** stack synthesizes from YAML; no secrets in CDK context.
10. **Stop on failure:** orchestrator cancels sibling download tasks if one fails (optional flag; default on).

## Config contract

`aws/config/pipeline.yaml` drives CDK *and* the orchestrator. Validated by a typed loader (required keys, CPU/memory pairs legal for Fargate, command non-empty).

## Orchestrator modes

- `full` — parallel downloads, then finalize
- `downloads-only`
- `finalize`
- `dry-run` — print planned RunTask payloads; no API calls

Exit non-zero on any failed task; print resume: `--mode finalize` or re-run failed download family.

## Testing strategy

| Layer | Tool | Coverage target |
|-------|------|-----------------|
| Unit | pytest + mocks | **100%** of `aws/hail_aws/` and `run_pipeline_aws.py` |
| CDK synth | `aws_cdk.assertions` | stack resource shapes |
| LocalStack | `localstack/localstack:4.14.0` Community | IAM/STS/logs stubs + orchestrator client wiring |
| Real AWS | manual smoke | documented; not CI-gated |

LocalStack Community does **not** fully run Fargate containers against EFS. Integration tests assert API orchestration against LocalStack endpoints, not end-to-end MESH downloads.

## Coverage policy

- **`aws/` package:** `fail_under = 100` for unit tests of `hail_aws` + CLI.
- **Repository `scripts/`:** currently ~39% (CI floor 35%). Whole-repo 100% is a separate phased campaign (~4,600 uncovered statements in I/O-heavy stages) and is **out of scope** for this adapter deliverable.

## Deploy flow

```bash
cd aws/cdk && pip install -r requirements.txt
cdk bootstrap   # once per account/region
cdk deploy

# build/push existing Dockerfile to ECR (tag from YAML)
python aws/run_pipeline_aws.py --config aws/config/pipeline.yaml --mode full
```

## Success criteria

- [ ] CDK deploy creates cluster, task defs, EFS, ECR, roles, log group
- [ ] `run_pipeline_aws.py --dry-run` plans 3 parallel + 1 finalize tasks
- [ ] Unit + LocalStack tests green; `aws/hail_aws` at 100% line coverage
- [ ] `ruff check aws`
- [ ] No modifications required to stage scripts for the happy path
