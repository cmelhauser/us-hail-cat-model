# Contributing to the CONUS Hail Catastrophe Model

Thank you for your interest in contributing. This document explains how to set
up a development environment, how to submit changes, and what standards the
project holds contributors to.

**Credits.** Author / scientific lead: Christopher Melhauser. AI collaborator
(project pseudonym for all AI work): **theonlymuffinbot**. That name is not a
separate GitHub repository; the sole code remote is
`cmelhauser/us-hail-cat-model`.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Development Setup](#development-setup)
3. [Branch Workflow](#branch-workflow)
4. [Making Changes](#making-changes)
5. [Tests](#tests)
6. [Documentation](#documentation)
7. [Submitting a Pull Request](#submitting-a-pull-request)
8. [Methodology Change Policy](#methodology-change-policy)
9. [Data Files](#data-files)

---

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be
respectful, constructive, and assume good faith.

---

## Development Setup

**Prerequisites:** Python 3.10+, Git, and the system libraries for
`cartopy`, `eccodes`, and `rasterio` (GEOS, PROJ, ecCodes). The easiest
reproducible environment is Docker:

```bash
docker build -t hail-cat-model .
docker run --rm -it hail-cat-model bash
```

For a local venv:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# Optional cloud runner:
# pip install -e ".[aws]"
```

The `[dev]` extra installs `pytest`, `pytest-cov`, `ruff`, `mypy`, and
`pre-commit`. The `[aws]` extra adds PyYAML, boto3, and aws-cdk-lib for the
Fargate adapter under `aws/`. Activate the pre-commit hooks:

```bash
pre-commit install
```

**Before every commit**, run the mandatory quality gate (also installed as a
local pre-commit hook):

```bash
./scripts/quality_gate.sh
```

That script enforces documentation/policy consistency, `ruff`, **100%**
coverage on `scripts` + `run_pipeline`, **100%** coverage on the AWS adapter,
and `run_pipeline.py --dry-run`. Do not use `git commit --no-verify` to bypass
it unless the maintainer explicitly requests an emergency override.

---

## Git remotes

**This repository uses a single remote: `origin`** (`cmelhauser/us-hail-cat-model`).
Push, branch tracking, and pull requests all target that repository.

After cloning, run once:

```bash
./scripts/setup_git_remotes.sh
```

That script sets `remote.pushDefault` to `origin` and removes any stale non-origin
remotes from older clones. See `docs/GIT_REMOTES.md` for details.

---

## Branch Workflow

| Branch | Purpose |
|--------|---------|
| `main` | Stable tip; always should pass CI |
| `v2.3.0` | **Active development branch** for model 2.3.0 (preferred checkout) |
| `v*` | Version branches; CI runs on pushes and PRs targeting them |
| `codex/<name>` | AI-assisted or local work branches |
| `feature/<name>` | New features or methodology changes |
| `fix/<name>` | Bug fixes |
| `docs/<name>` | Documentation-only changes |

Base day-to-day work on **`v2.3.0`** unless coordinating a hotfix to `main`.
Keep branches focused; one concern per PR. Open PRs against `main` on
**`origin`** (`cmelhauser/us-hail-cat-model`). Retired historical branches
(`v2.1`, `v2.2.2`, `v2.2.3`) are not active development.

---

## Making Changes

Before touching pipeline scripts or methodology:

1. Read `docs/ai_instructions.md` for non-negotiable constraints.
2. Read `docs/methodology.md` for scientific assumptions.
3. Check `docs/REVIEW_PRE_RUN.md` for known-good configuration.

**Grid constants:** Never define `NROWS`, `NCOLS`, `DX`, `LAT_MAX`, or
`LON_MIN` in a stage script. Import from `scripts/_config.py`. Any change to
grid geometry requires a model-version bump and full pipeline rerun.

**Output schemas:** Any new output file must be added to
`docs/data_dictionary.md`.

**Methodology changes:** See [Methodology Change Policy](#methodology-change-policy).

---

## Tests

**Mandate:** every commit must keep **100%** statement coverage on
`scripts/` + `run_pipeline.py` and on `aws/hail_aws` + `aws/run_pipeline_aws.py`.
CI fails otherwise (`fail_under = 100` / `--cov-fail-under=100`).

Preferred single entry point:

```bash
./scripts/quality_gate.sh
```

Or run pieces manually:

```bash
python scripts/check_policy_consistency.py
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  pytest -q tests -p pytest_cov \
  --cov=scripts --cov=run_pipeline --cov-fail-under=100
```

AWS adapter tests (100% coverage gate on `hail_aws` + CLI):

```bash
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  pytest -q aws/tests -m 'not localstack' \
  --ignore=aws/tests/test_cdk_stack.py \
  -p pytest_cov \
  --cov=hail_aws --cov=run_pipeline_aws --cov-fail-under=100
```

Optional LocalStack Community **4.14.0** (Docker daemon required):

```bash
docker compose -f aws/docker-compose.localstack.yml up -d
AWS_ENDPOINT_URL=http://localhost:4566 PYTHONPATH=aws pytest -q aws/tests -m localstack
```

Lint (from repo root; `scripts/archive/` is excluded in `pyproject.toml`):

```bash
ruff check .
```

**All commits and PRs must pass the full quality gate and GitHub Actions CI.**
If you add a new stage feature or fix a bug, add a test that covers the
new/changed behaviour. Never lower the coverage floors without an explicit
maintainer decision and docs update.

Test categories:

- **Unit** — helper functions on synthetic data (`tests/test_*.py`)
- **Integration** — end-to-end smoke on synthetic tiny grid
  (`tests/integration/`)
- **AWS adapter** — config/orchestrator/CDK (`aws/tests/`); LocalStack optional
- **Regression** — golden-output hashes, populated after first full run

Deterministic tests: any test that imports a stage script must pass with a
fixed `numpy` seed and produce the same output byte-for-byte.

---

## Documentation

When changing code, update the relevant documentation **in the same commit**
(enforced by review + `scripts/check_policy_consistency.py` for coverage/CI
policy drift):

| What changed | Update |
|---|---|
| User-facing behaviour | `README.md` |
| Agent / contributor operating rules | `AGENTS.md`, `docs/ai_instructions.md`, `CONTRIBUTING.md` |
| Scientific assumptions | `docs/methodology.md` |
| Per-stage implementation | `docs/technical_documentation.md` |
| Output files or schemas | `docs/data_dictionary.md` |
| Run commands or environment | `docs/reproduce.md` (and `aws/README.md` if cloud runner changed) |
| Run readiness | `docs/REVIEW_PRE_RUN.md` |
| AWS adapter / CDK / orchestrator | `aws/README.md`, `docs/reproduce.md` §14, `CHANGELOG.md` |
| Coverage / CI policy | `AGENTS.md`, `CONTRIBUTING.md`, `.github/workflows/tests.yml`, `pyproject.toml` |

New documents should be indexed in `docs/README.md`. Commits that change
behavior without updating the matching docs above will be rejected.

---

## Submitting a Pull Request

1. Fork the repository and create your branch.
2. Make your changes, add tests, update documentation and agent files.
3. Run `./scripts/quality_gate.sh` (or `pre-commit run --all-files`) and fix
   any failures. Coverage must remain at 100%.
4. Open a PR against `main` on **`origin`**:

   ```bash
   gh pr create --repo cmelhauser/us-hail-cat-model --base main
   ```

   Use the PR template.
5. Describe *what* changed and *why*. Link any relevant issues.
6. Do not merge while GitHub Actions is red on the PR.

PRs are merged by the maintainer after review. Expect comments on scientific
defensibility as well as code quality.

---

## Methodology Change Policy

This model is a scientific artifact. Changes to methodology (EVT fitting,
MESH formula, stochastic perturbation, event grouping logic) require:

1. A literature citation or mathematical derivation supporting the change.
2. An update to `docs/methodology.md` with the new assumption.
3. A sensitivity comparison showing how the change affects RP maps at the
   benchmark cells in `docs/benchmarks.md`.
4. A version bump in `pyproject.toml` and a `CHANGELOG.md` entry.

Changes that relax critical implementation rules (sparse storage, deterministic
fallback, SPC validation-only) will not be accepted.

---

## Data Files

Do not commit data files. `.gitignore` excludes:

```
*.tif  *.npy  *.npz  *.nc  *.grib2  *.parquet  *.pkl  *.csv (outputs)
data/
logs/
```

If you need to share a synthetic test dataset, place it in `tests/data/` (kept
small, under 1 MB, committed to the repo). Anything larger belongs on an
external store (S3, Zenodo).
