---
name: Bug report
about: Report a code error, crash, or incorrect numerical output
title: "[BUG] "
labels: bug
assignees: ""
---

## Describe the bug

A clear description of what went wrong.

## Stage

Which pipeline stage failed? (e.g., Stage 05, Stage 13)

## To Reproduce

```bash
# Exact command that triggers the bug
python run_pipeline.py --only 05 --skip-ml
```

## Expected behavior

What did you expect to happen?

## Actual behavior

What happened instead? Paste the relevant log output or traceback:

```
[paste traceback here]
```

## Environment

- OS: [e.g., Ubuntu 22.04]
- Python version: [e.g., 3.11.4]
- Key package versions: `numpy`, `rasterio`, `scipy` (from `pip freeze`)
- Model version / git commit: [e.g., v2.2.0 / `git rev-parse --short HEAD`]

## Additional context

Any other relevant context (e.g., data source, disk state, memory available).
