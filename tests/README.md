# v2.1 Unit Test Suite

This directory contains pytest coverage for all 15 pipeline stages plus the pipeline runner.

## Run

From the repository root after applying the v2.1 patches:

```bash
pip install pytest
pytest tests -q
```

If the scripts live outside `scripts/`, set:

```bash
export HAIL_MODEL_REPO=/path/to/repo
pytest tests -q
```

The tests are intentionally unit-level: they validate pure helpers, sparse event handling,
threshold selection behavior, deterministic fallbacks, validation logic, and monotonicity
properties without downloading external datasets.

Stage 01 tests also cover MYRORSS archive format handling (`.netcdf` and
`.netcdf.gz`) and manifest classification so missing-source days remain distinct
from available-source days with no hail pixels.
