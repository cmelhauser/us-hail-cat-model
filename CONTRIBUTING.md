# Contributing to the CONUS Hail Catastrophe Model

Thank you for your interest in contributing. This document explains how to set
up a development environment, how to submit changes, and what standards the
project holds contributors to.

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
```

The `[dev]` extra installs `pytest`, `pytest-cov`, `ruff`, `mypy`, and
`pre-commit`. Activate the pre-commit hooks:

```bash
pre-commit install
```

---

## Branch Workflow

| Branch | Purpose |
|--------|---------|
| `main` | Stable, always passes CI |
| `codex/<name>` | AI-assisted or local work branches |
| `feature/<name>` | New features or methodology changes |
| `fix/<name>` | Bug fixes |
| `docs/<name>` | Documentation-only changes |

Base all new branches off `main` unless explicitly coordinating with the
maintainer. Keep branches focused; one concern per PR. The historical `v2.1`
branch has been merged and is no longer the active development branch.

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

The project uses `pytest`. Run the full suite from the repo root:

```bash
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests
```

Run with coverage:

```bash
pytest --cov=scripts --cov-report=term-missing tests
```

**All PRs must pass the full test suite.** If you add a new stage feature or
fix a bug, add a test that covers the new/changed behaviour.

Test categories:

- **Unit** — helper functions on synthetic data (`tests/test_*.py`)
- **Integration** — end-to-end smoke on synthetic tiny grid
  (`tests/integration/`)
- **Regression** — golden-output hashes, populated after first full run

Deterministic tests: any test that imports a stage script must pass with a
fixed `numpy` seed and produce the same output byte-for-byte.

---

## Documentation

When changing code, update the relevant documentation **in the same PR**:

| What changed | Update |
|---|---|
| User-facing behaviour | `README.md` |
| Scientific assumptions | `docs/methodology.md` |
| Per-stage implementation | `docs/technical_documentation.md` |
| Output files or schemas | `docs/data_dictionary.md` |
| Run commands or environment | `docs/reproduce.md` |
| Run readiness | `docs/REVIEW_PRE_RUN.md` |

New documents should be indexed in `docs/README.md`.

---

## Submitting a Pull Request

1. Fork the repository and create your branch.
2. Make your changes, add tests, update documentation.
3. Run `pre-commit run --all-files` and fix any lint issues.
4. Run the full test suite locally.
5. Open a PR against `main`. Use the PR template.
6. Describe *what* changed and *why*. Link any relevant issues.

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
