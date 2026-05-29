#!/usr/bin/env bash
# Configure this clone so pushes and PRs use origin (cmelhauser) only, not upstream.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: not a git repository" >&2
  exit 1
fi

git config remote.pushDefault origin

if git remote get-url upstream >/dev/null 2>&1; then
  git remote set-url --push upstream no_push
  echo "upstream: fetch only (push disabled via pushurl no_push)"
fi

echo "remote.pushDefault = $(git config --get remote.pushDefault)"
echo "origin push: $(git remote get-url --push origin 2>/dev/null || git remote get-url origin)"
if git remote get-url upstream >/dev/null 2>&1; then
  echo "upstream fetch: $(git remote get-url upstream)"
  echo "upstream push: $(git remote get-url --push upstream)"
fi
echo "Done. Push with: git push -u origin HEAD"
echo "PRs: gh pr create --repo cmelhauser/us-hail-cat-model --base main"
