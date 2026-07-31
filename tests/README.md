# Unit Test Suite (v2.3.0)

This directory contains pytest coverage for pipeline stages plus the pipeline runner.

AWS Fargate adapter tests live under **`aws/tests/`** (separate package; **100%**
coverage gate on `hail_aws` + `run_pipeline_aws.py`, enforced by the CI **`aws`**
job). See `aws/README.md` and `docs/reproduce.md` §14.

Pipeline `scripts/` coverage uses a modest floor (`fail_under = 35` in
`pyproject.toml`) because stages are I/O- and network-heavy; raising that floor
is a separate campaign from the AWS adapter gate.

## Run

From the repository root:

```bash
pip install -e ".[dev]"
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
```

AWS adapter:

```bash
pip install -e ".[aws,dev]"
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 \
  pytest -q aws/tests -m 'not localstack' \
  --ignore=aws/tests/test_cdk_stack.py \
  --cov=hail_aws --cov=run_pipeline_aws --cov-fail-under=100
```

If the scripts live outside `scripts/`, set:

```bash
export HAIL_MODEL_REPO=/path/to/repo
pytest tests -q
```

Most tests are unit-level: they validate pure helpers, sparse event handling,
threshold selection behavior, deterministic fallbacks, validation logic, and
monotonicity properties without downloading external datasets. The
`tests/integration/` directory contains the synthetic smoke path and GridRad
hourly fallback tests (`test_gridrad_hourly_fallback.py`: d841001 V4.2 through
04b → 04c without live THREDDS).

Stage 01 tests also cover MYRORSS archive format handling (`.netcdf` and
`.netcdf.gz`) and manifest classification so missing-source days remain distinct
from available-source days with no hail pixels.
