#!/usr/bin/env bash
# Mandatory repository quality gate.
# Run before every git commit. Writes .git/quality-gate.stamp on success.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "ERROR: no Python interpreter found (.venv/bin/python or python3)" >&2
  exit 1
fi

stamp_payload() {
  # Content fingerprint of the working tree (staging alone must not invalidate).
  git ls-files -co --exclude-standard -z | sort -z | xargs -0 shasum -a 256
}

current_stamp() {
  stamp_payload | shasum -a 256 | awk '{print $1}'
}

STAMP_FILE="$ROOT/.git/quality-gate.stamp"
if [[ "${QUALITY_GATE_FORCE:-}" != "1" && -f "$STAMP_FILE" ]]; then
  expected="$(tr -d '[:space:]' < "$STAMP_FILE")"
  actual="$(current_stamp)"
  if [[ "$expected" == "$actual" ]]; then
    echo "Quality gate stamp is current — skipping full re-run."
    echo "Set QUALITY_GATE_FORCE=1 to force a full re-run."
    exit 0
  fi
fi

echo "════════════════════════════════════════════════════════════"
echo " Quality gate — 100% coverage, lint, dry-run, docs policy"
echo "════════════════════════════════════════════════════════════"

echo ""
echo "[1/6] Policy / documentation consistency"
"$PYTHON" scripts/check_policy_consistency.py

echo ""
echo "[2/6] Syntax check (py_compile)"
"$PYTHON" -m py_compile run_pipeline.py scripts/*.py scripts/diagnostics/*.py

echo ""
echo "[3/6] Ruff"
"$PYTHON" -m ruff check .

echo ""
echo "[4/6] Pipeline unit tests + 100% coverage (scripts + run_pipeline)"
OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  "$PYTHON" -m pytest -q tests -p pytest_cov \
  --cov=scripts --cov=run_pipeline \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=100

echo ""
echo "[5/6] AWS adapter tests + 100% coverage"
PYTHONPATH=aws OPENBLAS_NUM_THREADS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  "$PYTHON" -m pytest -q aws/tests -m 'not localstack' \
  --ignore=aws/tests/test_cdk_stack.py -p pytest_cov \
  --cov=hail_aws --cov=run_pipeline_aws \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=100

echo ""
echo "[6/6] Pipeline dry-run"
"$PYTHON" run_pipeline.py --dry-run

mkdir -p "$ROOT/.git"
current_stamp > "$STAMP_FILE"
echo ""
echo "Quality gate PASSED — stamp written to .git/quality-gate.stamp"
echo "Reminder: keep AGENTS.md / docs / CONTRIBUTING synchronized with any"
echo "behavior, schema, CLI, or coverage-policy changes in this commit."
