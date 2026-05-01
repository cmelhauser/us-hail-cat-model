## Summary

<!-- What does this PR do? One paragraph. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Methodology change (changes scientific assumptions; requires version bump)
- [ ] Breaking change (alters output schema, file paths, or API)
- [ ] Documentation only
- [ ] Engineering hygiene (logging, CI, typing, refactor — no behavior change)

## Checklist

### Code
- [ ] `python -m py_compile run_pipeline.py scripts/*.py` passes
- [ ] `OPENBLAS_NUM_THREADS=1 pytest -q tests` passes (all non-slow tests)
- [ ] `ruff check .` passes
- [ ] `python run_pipeline.py --dry-run` passes
- [ ] No dense `(n_events, 520, 1180)` arrays introduced
- [ ] No new `NROWS = 520` / `NCOLS = 1180` literals in stage scripts (use `_config`)
- [ ] Grid constants unchanged or version bump documented

### Tests
- [ ] Unit test added or updated for the changed behavior
- [ ] Integration test updated if stage boundary or output schema changed

### Documentation
- [ ] `README.md` updated (if user-facing behavior changed)
- [ ] `docs/methodology.md` updated (if scientific assumptions changed)
- [ ] `docs/technical_documentation.md` updated (if stage behavior changed)
- [ ] `docs/data_dictionary.md` updated (if new/renamed outputs)
- [ ] `docs/reproduce.md` updated (if run commands changed)
- [ ] `CHANGELOG.md` entry added

### Methodology changes only
- [ ] Literature citation or mathematical derivation provided
- [ ] Sensitivity comparison at benchmark cells documented
- [ ] `pyproject.toml` version bumped

## Related issues

Closes #<!-- issue number -->

## Notes for reviewers

<!-- Anything tricky, non-obvious, or that needs particular attention. -->
