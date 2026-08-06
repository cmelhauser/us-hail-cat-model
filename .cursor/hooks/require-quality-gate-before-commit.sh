#!/usr/bin/env bash
# Cursor beforeShellExecution hook: block git commit unless quality gate is current.
set -euo pipefail

input="$(cat || true)"
# Prefer python3 for JSON parse; fall back to allowing if unavailable (fail open only
# when we cannot parse — failClosed on the hook definition still applies for crashes).
command="$(
  printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
print(data.get("command") or "")
' 2>/dev/null || true
)"

# Only gate explicit git commits (not commit-tree plumbing used by tools).
if ! printf '%s' "$command" | grep -Eq '(^|[;&|[:space:]])git[[:space:]]+commit([[:space:]]|$)'; then
  printf '%s\n' '{"permission":"allow"}'
  exit 0
fi

# Allow amend / empty-message tooling only when stamp is still valid.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
stamp="$ROOT/.git/quality-gate.stamp"
if [[ ! -f "$stamp" ]]; then
  cat <<'EOF'
{
  "permission": "deny",
  "user_message": "Commit blocked: run ./scripts/quality_gate.sh first (100% coverage + docs policy).",
  "agent_message": "Mandatory quality gate missing. Run ./scripts/quality_gate.sh, sync docs/AGENTS.md if needed, then commit."
}
EOF
  exit 0
fi

current="$(
  git ls-files -co --exclude-standard -z | sort -z | xargs -0 shasum -a 256 \
    | shasum -a 256 | awk '{print $1}'
)"
expected="$(tr -d '[:space:]' < "$stamp")"

if [[ "$current" != "$expected" ]]; then
  cat <<'EOF'
{
  "permission": "deny",
  "user_message": "Commit blocked: working tree changed since the last quality gate. Re-run ./scripts/quality_gate.sh.",
  "agent_message": "Quality-gate stamp is stale relative to the working tree. Re-run ./scripts/quality_gate.sh after finishing docs/tests updates."
}
EOF
  exit 0
fi

printf '%s\n' '{"permission":"allow"}'
exit 0
