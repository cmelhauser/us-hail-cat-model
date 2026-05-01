# v2.1 Repo Update Notes

This package contains full replacement files, not diff patches.

## Copy into repo

```bash
cp README.md /path/to/repo/README.md
cp run_pipeline.py /path/to/repo/run_pipeline.py
cp scripts/*.py /path/to/repo/scripts/
cp -r tests /path/to/repo/tests
```

## Validate

```bash
python -m py_compile run_pipeline.py scripts/*.py
pytest tests -q
python run_pipeline.py --dry-run
```

## Important behavior

- Stage 05 supports optional model artifacts but falls back to deterministic logic.
- Stage 13 is sparse-safe and does not reconstruct all event templates as dense grids.
- `run_pipeline.py` passes `--skip-ml` and `--retrain-models` through to Stage 05.
