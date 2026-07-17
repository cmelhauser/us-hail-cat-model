# AWS Fargate Adapter Implementation Plan

> **For agentic workers:** Steps use checkbox syntax. AWS library coverage gate is 100%.

**Goal:** Ship a deployable `aws/` package (YAML + CDK + local orchestrator + LocalStack 4.14 tests) without modifying stage scripts.

**Architecture:** EFS-backed Fargate tasks; parallel downloads then finalize; local boto3 polling CLI.

**Tech Stack:** Python 3.10+, boto3, PyYAML, aws-cdk-lib, pytest, LocalStack Community `4.14.0`.

## Global Constraints

- No changes to stage scripts or `run_pipeline.py` behavior.
- LocalStack image pin: `localstack/localstack:4.14.0` (Community, not Pro/`latest`).
- `aws/hail_aws` + `run_pipeline_aws.py`: **100%** line coverage (`--cov-fail-under=100`).
- Whole-repo `scripts/` 100% is **out of scope** for this deliverable (~39% today / ~4,600 missing lines).

---

### Task 1: Config + orchestrator library — DONE

- [x] `aws/config/pipeline.yaml`
- [x] `aws/hail_aws/{config,ecs_client,orchestrator}.py`
- [x] `aws/run_pipeline_aws.py`
- [x] Unit tests at 100% coverage

### Task 2: CDK stack — DONE

- [x] `aws/cdk` app + `HailPipelineStack` (ECS, EFS, ECR, IAM, logs, 4 task defs)
- [x] Synth tests skip cleanly without Node.js

### Task 3: LocalStack harness — DONE

- [x] `docker-compose.localstack.yml` pinned to 4.14.0
- [x] `@pytest.mark.localstack` STS smoke test

### Task 4: Repo hygiene — DONE

- [x] Fix stale version/check-count unit tests
- [x] `pyproject.toml` optional `[aws]` extras + `localstack` marker
- [x] Design spec under `docs/superpowers/specs/`

### Follow-up (not this PR)

- [ ] Install Node.js and run CDK synth assertions in CI
- [ ] Real-account smoke: `cdk deploy` + short `--mode downloads-only` dry path
- [ ] Phased campaign to raise `scripts/` coverage toward 100% (separate plan)
