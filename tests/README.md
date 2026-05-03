# v2.1 Unit Test Suite

This directory contains pytest coverage for all 15 pipeline stages plus the pipeline runner.

## Run

From the repository root:

```bash
pip install -e ".[dev]"
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
```

If the scripts live outside `scripts/`, set:

```bash
export HAIL_MODEL_REPO=/path/to/repo
pytest tests -q
```

Most tests are unit-level: they validate pure helpers, sparse event handling,
threshold selection behavior, deterministic fallbacks, validation logic, and
monotonicity properties without downloading external datasets. The
`tests/integration/` directory contains the synthetic smoke path.

Stage 01 tests also cover MYRORSS archive format handling (`.netcdf` and
`.netcdf.gz`) and manifest classification so missing-source days remain distinct
from available-source days with no hail pixels.
