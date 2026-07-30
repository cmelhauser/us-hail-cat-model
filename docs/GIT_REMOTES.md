# Git remotes policy

This repository has a **single remote**: **`origin`**.

| Remote | URL | Fetch | Push | PRs |
|--------|-----|-------|------|-----|
| **`origin`** | `https://github.com/cmelhauser/us-hail-cat-model.git` | Yes | **Yes** | **Yes** — base `main` on this repo |

There is no second GitHub remote. Do not add another remote for day-to-day work.

## Required local setup (once per clone)

From the repo root:

```bash
./scripts/setup_git_remotes.sh
```

Or manually:

```bash
git config remote.pushDefault origin
# If a stale non-origin remote exists from an older clone:
# git remote remove <name>
```

## Commands to use

```bash
# Push current branch
git push -u origin HEAD

# Open a PR against this repository
gh pr create --repo cmelhauser/us-hail-cat-model --base main --head "$(git branch --show-current)"
```

## Do not

- Add a second remote for day-to-day work
- Open PRs against any repository other than `cmelhauser/us-hail-cat-model`
- Merge or commit directly on GitHub outside the normal PR workflow without maintainer agreement

AI agents and contributors must treat **`origin`** (`cmelhauser/us-hail-cat-model`) as the sole remote.
