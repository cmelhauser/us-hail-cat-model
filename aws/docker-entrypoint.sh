#!/usr/bin/env bash
# Container entrypoint for local Docker and AWS Fargate.
# Materializes CDS credentials from env (injected via ECS Secrets Manager).
set -euo pipefail

if [[ -n "${CDSAPI_URL:-}" && -n "${CDSAPI_KEY:-}" ]]; then
  umask 077
  printf 'url: %s\nkey: %s\n' "${CDSAPI_URL}" "${CDSAPI_KEY}" > "${HOME}/.cdsapirc"
fi

# Preserve historical image contract: ENTRYPOINT was ["python"].
# Task commands are typically: run_pipeline.py --only 01
if [[ $# -eq 0 ]]; then
  exec python run_pipeline.py --help
fi
if [[ "$1" == "python" ]]; then
  shift
  exec python "$@"
fi
if [[ "$1" == "bash" || "$1" == "sh" ]]; then
  exec "$@"
fi
exec python "$@"
