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

### Pre-commit mandate
- [ ] `./scripts/quality_gate.sh` passed on this branch tip
- [ ] Documentation and agent files (`AGENTS.md`, `docs/ai_instructions.md`, and any touched operator/methodology docs) are synchronized in this PR
- [ ] Did **not** use `--no-verify` / skip hooks

### Code
- [ ] `python -m py_compile run_pipeline.py scripts/*.py` passes
- [ ] `OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests -p pytest_cov -m "not integration and not regression and not slow" --cov=scripts --cov=run_pipeline --cov-fail-under=100` passes
- [ ] `ruff check .` passes
- [ ] `python run_pipeline.py --dry-run` passes
- [ ] No dense `(n_events, 520, 1180)` arrays introduced
- [ ] No new `NROWS = 520` / `NCOLS = 1180` literals in stage scripts (use `_config`)
- [ ] Grid constants unchanged or version bump documented

### Tests / coverage
- [ ] Unit test added or updated for the changed behavior
- [ ] Integration test updated if stage boundary or output schema changed
- [ ] Pipeline coverage remains **100%** (`scripts` + `run_pipeline`)
- [ ] AWS coverage remains **100%**: `PYTHONPATH=aws pytest -q aws/tests -m 'not localstack' --ignore=aws/tests/test_cdk_stack.py -p pytest_cov --cov=hail_aws --cov=run_pipeline_aws --cov-fail-under=100`

### Documentation
- [ ] `README.md` updated (if user-facing behavior changed)
- [ ] `AGENTS.md` / `docs/ai_instructions.md` / `CONTRIBUTING.md` updated (if agent or contributor rules changed)
- [ ] `docs/methodology.md` updated (if scientific assumptions changed)
- [ ] `docs/technical_documentation.md` updated (if stage behavior changed)
- [ ] `docs/data_dictionary.md` updated (if new/renamed outputs)
- [ ] `docs/reproduce.md` updated (if run commands changed)
- [ ] `aws/README.md` / `docs/reproduce.md` §14 updated (if AWS adapter changed)
- [ ] `CHANGELOG.md` entry added

### Methodology changes only
- [ ] Literature citation or mathematical derivation provided
- [ ] Sensitivity comparison at benchmark cells documented
- [ ] `pyproject.toml` version bumped

## Related issues

Closes #<!-- issue number -->

## Notes for reviewers

<!-- Anything tricky, non-obvious, or that needs particular attention. -->
