#!/usr/bin/env bash
# Configure this clone for origin-only (cmelhauser/us-hail-cat-model).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: not a git repository" >&2
  exit 1
fi

EXPECTED_ORIGIN="https://github.com/cmelhauser/us-hail-cat-model.git"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "error: origin remote is missing; add it first:" >&2
  echo "  git remote add origin ${EXPECTED_ORIGIN}" >&2
  exit 1
fi

git config remote.pushDefault origin

# Remove any non-origin remotes left from older multi-remote clones.
while IFS= read -r remote; do
  [[ -z "${remote}" ]] && continue
  if [[ "${remote}" != "origin" ]]; then
    git remote remove "${remote}"
    echo "removed stale remote: ${remote}"
  fi
done < <(git remote)

echo "remote.pushDefault = $(git config --get remote.pushDefault)"
echo "origin: $(git remote get-url origin)"
echo "remotes: $(git remote | tr '\n' ' ')"
echo "Done. Push with: git push -u origin HEAD"
echo "PRs: gh pr create --repo cmelhauser/us-hail-cat-model --base main"
